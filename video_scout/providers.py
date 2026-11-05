"""Discovery providers. Each returns a list of Video. Add a new one by subclassing VideoProvider
and registering it in PROVIDERS (see docs/VIDEO_SCOUT.md, "Adding a provider")."""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Type
from urllib.parse import quote_plus

import requests

from . import config, licenses
from .guess import guess
from .models import Video

UA = "BouncerVideoScout/0.1 (+https://web-production-704d0c.up.railway.app; bouncertravel@gmail.com)"
TIMEOUT = 25


def _ytdlp_cmd() -> List[str]:
    exe = Path(sys.executable).with_name("yt-dlp")
    if exe.exists():
        return [str(exe)]
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def ytdlp_base_args() -> List[str]:
    args = _ytdlp_cmd() + ["--no-warnings", "--ignore-errors"]
    if shutil.which("node"):
        args += ["--js-runtimes", "node", "--remote-components", "ejs:github"]
    return args


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _ymd(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = str(s)
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


class VideoProvider:
    name = "base"
    needs = ()           # env vars required
    licensed_only = False  # True if every result is free-reuse licensed

    def available(self) -> bool:
        return config.has(*self.needs)

    def search(self, query: str, limit: int = 25, licensed: bool = False) -> List[Video]:
        raise NotImplementedError

    def _finish(self, v: Video, description: str = "") -> Video:
        if not v.hotel_guess and not v.location_guess:
            v.hotel_guess, v.location_guess = guess(v.title, description)
        v.source = self.name
        return v


# ---------------------------------------------------------------- YouTube via yt-dlp (free, no key)
class YtDlpYouTube(VideoProvider):
    """YouTube search sorted by view count. `licensed=True` adds YouTube's Creative Commons filter
    and confirms each video's license on its watch page (YouTube CC == CC BY 3.0)."""
    name = "youtube"
    SP_VIEWS = "CAM%253D"         # sort: view count
    SP_VIEWS_CC = "CAMSAjAB"       # sort: view count + filter: Creative Commons

    def available(self) -> bool:
        try:
            subprocess.run(_ytdlp_cmd() + ["--version"], capture_output=True, timeout=20, check=True)
            return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 25, licensed: bool = False, enrich: Optional[int] = None) -> List[Video]:
        sp = self.SP_VIEWS_CC if licensed else self.SP_VIEWS
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={sp}"
        out = subprocess.run(ytdlp_base_args() + ["--flat-playlist", "-J", "--playlist-end", str(limit), url],
                             capture_output=True, text=True, timeout=180)
        if out.returncode != 0 and not out.stdout:
            raise RuntimeError(f"yt-dlp search failed: {out.stderr.strip()[-300:]}")
        entries = [e for e in (json.loads(out.stdout).get("entries") or []) if e and e.get("id")]
        vids = [self._from_entry(e, query) for e in entries[:limit]]
        # Enrich (date, likes, license) for the top N by views. Licensed searches enrich all so the license is verified.
        n = len(vids) if licensed else (8 if enrich is None else enrich)
        vids.sort(key=lambda v: v.views or 0, reverse=True)
        for v in vids[:n]:
            try:
                self.enrich(v)
            except Exception:
                pass
        if licensed:
            vids = [v for v in vids if v.reusable]
        return vids

    def _from_entry(self, e: Dict, query: str) -> Video:
        vid = e["id"]
        thumbs = e.get("thumbnails") or []
        is_short = "/shorts/" in (e.get("url") or "")
        v = Video(id=f"youtube:{vid}", platform="youtube",
                  url=f"https://www.youtube.com/{'shorts/' + vid if is_short else 'watch?v=' + vid}",
                  title=e.get("title") or "", creator=e.get("channel") or e.get("uploader") or "",
                  creator_url=e.get("channel_url") or e.get("uploader_url") or "",
                  views=e.get("view_count"), duration=e.get("duration"),
                  thumbnail=(thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
                  published=_ymd(datetime.utcfromtimestamp(e["timestamp"]).strftime("%Y%m%d")) if e.get("timestamp") else None,
                  query=query)
        return self._finish(v, e.get("description") or "")

    def enrich(self, v: Video) -> Video:
        out = subprocess.run(ytdlp_base_args() + ["-J", "--skip-download", v.url],
                             capture_output=True, text=True, timeout=90)
        d = json.loads(out.stdout)
        v.published = _ymd(d.get("upload_date")) or v.published
        v.likes = d.get("like_count", v.likes)
        v.views = d.get("view_count", v.views)
        v.duration = d.get("duration", v.duration)
        lic = d.get("license") or ""
        code, ok = licenses.classify(lic)
        v.license_code = code if ok else ("YOUTUBE-STANDARD" if not lic else code)
        v.license_name = "CC BY 3.0 (YouTube Creative Commons)" if code == "CC-BY" else (lic or "Standard YouTube License")
        v.license_url = "https://creativecommons.org/licenses/by/3.0/" if code == "CC-BY" else ""
        v.hotel_guess, v.location_guess = guess(v.title, d.get("description") or "")
        return v


# ---------------------------------------------------------------- YouTube Data API v3 (optional key)
class YouTubeDataAPI(VideoProvider):
    """Needs YOUTUBE_API_KEY. search.list costs 100 quota units (10,000/day default)."""
    name = "youtube_api"
    needs = ("YOUTUBE_API_KEY",)

    def search(self, query: str, limit: int = 25, licensed: bool = False) -> List[Video]:
        key = config.env("YOUTUBE_API_KEY")
        p = {"part": "snippet", "q": query, "type": "video", "order": "viewCount",
             "maxResults": min(50, limit), "key": key}
        if licensed:
            p["videoLicense"] = "creativeCommon"
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=p, timeout=TIMEOUT)
        r.raise_for_status()
        ids = [i["id"]["videoId"] for i in r.json().get("items", [])]
        if not ids:
            return []
        r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=TIMEOUT,
                         params={"part": "snippet,statistics,status,contentDetails", "id": ",".join(ids), "key": key})
        r.raise_for_status()
        vids = []
        for it in r.json().get("items", []):
            sn, st = it["snippet"], it.get("statistics", {})
            cc = it.get("status", {}).get("license") == "creativeCommon"
            v = Video(id=f"youtube:{it['id']}", platform="youtube", url=f"https://www.youtube.com/watch?v={it['id']}",
                      title=sn.get("title", ""), creator=sn.get("channelTitle", ""),
                      creator_url=f"https://www.youtube.com/channel/{sn.get('channelId', '')}",
                      views=int(st["viewCount"]) if "viewCount" in st else None,
                      likes=int(st["likeCount"]) if "likeCount" in st else None,
                      published=_ymd(sn.get("publishedAt")),
                      thumbnail=(sn.get("thumbnails", {}).get("high") or {}).get("url", ""),
                      license_code="CC-BY" if cc else "YOUTUBE-STANDARD",
                      license_name="CC BY 3.0 (YouTube Creative Commons)" if cc else "Standard YouTube License",
                      license_url="https://creativecommons.org/licenses/by/3.0/" if cc else "", query=query)
            vids.append(self._finish(v, sn.get("description", "")))
        return [v for v in vids if v.reusable] if licensed else vids


# ---------------------------------------------------------------- Wikimedia Commons (free, no key, licensed)
class WikimediaCommons(VideoProvider):
    name = "commons"
    licensed_only = True

    def search(self, query: str, limit: int = 25, licensed: bool = True) -> List[Video]:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=TIMEOUT, params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:video",
            "gsrnamespace": 6, "gsrlimit": min(50, limit), "prop": "imageinfo",
            "iiprop": "url|extmetadata|size|timestamp", "iiurlwidth": 640,
            "iiextmetadatafilter": "LicenseShortName|Artist|LicenseUrl|ImageDescription|DateTimeOriginal"})
        r.raise_for_status()
        vids = []
        for p in (r.json().get("query", {}).get("pages") or {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata", {})
            g = lambda k: (md.get(k) or {}).get("value", "")
            code, ok = licenses.classify(g("LicenseShortName"), g("LicenseUrl"))
            if not ok:
                continue
            title = p["title"].removeprefix("File:")
            v = Video(id=f"commons:{p['pageid']}", platform="commons", url=ii.get("descriptionurl", ""),
                      title=_strip_html(g("ImageDescription"))[:140] or title, creator=_strip_html(g("Artist"))[:80],
                      published=_ymd(_strip_html(g("DateTimeOriginal"))) or _ymd(ii.get("timestamp")),
                      duration=ii.get("duration"), thumbnail=ii.get("thumburl", ""),
                      license_code=code, license_name=g("LicenseShortName"), license_url=g("LicenseUrl"),
                      download_url=(ii.get("url") or "").split("?")[0], query=query)
            vids.append(self._finish(v))
        return vids[:limit]


# ---------------------------------------------------------------- Internet Archive (free, no key, licensed)
class InternetArchive(VideoProvider):
    name = "archive"
    licensed_only = True

    def search(self, query: str, limit: int = 25, licensed: bool = True) -> List[Video]:
        q = f"title:({query}) AND mediatype:movies AND (licenseurl:*creativecommons* OR licenseurl:*publicdomain*)"
        r = requests.get("https://archive.org/advancedsearch.php", headers={"User-Agent": UA}, timeout=TIMEOUT, params={
            "q": q, "fl[]": ["identifier", "title", "creator", "downloads", "licenseurl", "date", "publicdate"],
            "sort[]": "downloads desc", "rows": min(100, limit), "output": "json"})
        r.raise_for_status()
        vids = []
        for d in r.json().get("response", {}).get("docs", []):
            code, ok = licenses.classify(d.get("licenseurl"))
            if not ok:
                continue
            ident = d["identifier"]
            creator = d.get("creator") or ""
            v = Video(id=f"archive:{ident}", platform="archive", url=f"https://archive.org/details/{ident}",
                      title=d.get("title") if isinstance(d.get("title"), str) else str(d.get("title")),
                      creator=creator if isinstance(creator, str) else ", ".join(creator),
                      views=d.get("downloads"), published=_ymd(d.get("publicdate") or d.get("date")),
                      thumbnail=f"https://archive.org/services/img/{ident}", license_code=code,
                      license_name=label_from_url(d.get("licenseurl", ""), code), license_url=d.get("licenseurl", ""),
                      query=query)
            vids.append(self._finish(v))
        return vids

    @staticmethod
    def resolve_download(ident: str) -> str:
        r = requests.get(f"https://archive.org/metadata/{ident}", headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        files = r.json().get("files", [])
        pref = [f for f in files if f.get("name", "").endswith(".mp4")] or \
               [f for f in files if re.search(r"\.(webm|ogv|mov|mpeg|avi)$", f.get("name", ""))]
        if not pref:
            raise RuntimeError("no downloadable video file in this Internet Archive item")
        pref.sort(key=lambda f: int(f.get("size", 0) or 0))
        f = next((f for f in pref if 2e6 < int(f.get("size", 0) or 0) < 400e6), pref[-1])
        return f"https://archive.org/download/{ident}/{quote_plus(f['name'], safe='/')}"


def label_from_url(url: str, code: str) -> str:
    m = re.search(r"licenses/([a-z-]+)/(\d\.\d)", url or "")
    if m:
        return f"CC {m.group(1).upper().replace('-', ' ')} {m.group(2)}"
    return licenses.label(code)


# ---------------------------------------------------------------- Pexels / Pixabay (free keys, licensed)
class Pexels(VideoProvider):
    """Needs PEXELS_API_KEY (free: https://www.pexels.com/api/). Default 200 req/hour, 20,000/month."""
    name = "pexels"
    needs = ("PEXELS_API_KEY",)
    licensed_only = True

    def search(self, query: str, limit: int = 25, licensed: bool = True) -> List[Video]:
        r = requests.get("https://api.pexels.com/videos/search", timeout=TIMEOUT,
                         headers={"Authorization": config.env("PEXELS_API_KEY")},
                         params={"query": query, "per_page": min(80, limit), "orientation": "portrait"})
        r.raise_for_status()
        vids = []
        for it in r.json().get("videos", []):
            files = sorted([f for f in it.get("video_files", []) if f.get("file_type") == "video/mp4"],
                           key=lambda f: (f.get("height") or 0))
            best = next((f for f in files if (f.get("height") or 0) >= 1280), files[-1] if files else {})
            slug = it.get("url", "").rstrip("/").split("/")[-1].replace("-", " ")
            v = Video(id=f"pexels:{it['id']}", platform="pexels", url=it.get("url", ""),
                      title=re.sub(r"\s\d+$", "", slug).title() or f"Pexels video {it['id']}",
                      creator=(it.get("user") or {}).get("name", ""), creator_url=(it.get("user") or {}).get("url", ""),
                      duration=it.get("duration"), thumbnail=it.get("image", ""), license_code="PEXELS",
                      license_name="Pexels License", license_url="https://www.pexels.com/license/",
                      download_url=best.get("link", ""), query=query)
            vids.append(self._finish(v))
        return vids


class Pixabay(VideoProvider):
    """Needs PIXABAY_API_KEY (free: https://pixabay.com/api/docs/). 100 req/60s; cache results 24h per their terms."""
    name = "pixabay"
    needs = ("PIXABAY_API_KEY",)
    licensed_only = True

    def search(self, query: str, limit: int = 25, licensed: bool = True) -> List[Video]:
        r = requests.get("https://pixabay.com/api/videos/", timeout=TIMEOUT, params={
            "key": config.env("PIXABAY_API_KEY"), "q": query, "per_page": max(3, min(200, limit)), "order": "popular"})
        r.raise_for_status()
        vids = []
        for it in r.json().get("hits", []):
            vs = it.get("videos", {})
            best = vs.get("large") if (vs.get("large") or {}).get("url") else vs.get("medium", {})
            v = Video(id=f"pixabay:{it['id']}", platform="pixabay", url=it.get("pageURL", ""),
                      title=(it.get("tags") or "").title(), creator=it.get("user", ""),
                      creator_url=f"https://pixabay.com/users/{it.get('user', '')}-{it.get('user_id', '')}/",
                      views=it.get("views"), likes=it.get("likes"), duration=it.get("duration"),
                      thumbnail=(vs.get("medium") or {}).get("thumbnail", ""), license_code="PIXABAY",
                      license_name="Pixabay Content License", license_url="https://pixabay.com/service/license-summary/",
                      download_url=(best or {}).get("url", ""), query=query)
            vids.append(self._finish(v))
        return vids


# ---------------------------------------------------------------- RapidAPI social search (optional, OFF by default)
class RapidAPISocial(VideoProvider):
    """Optional paid/freemium social-video search on RapidAPI (TikTok/Instagram search APIs).
    OFF unless VIDEO_SCOUT_ENABLE_RAPIDAPI=1 and VIDEO_SCOUT_RAPIDAPI_HOST + _PATH are set. Uses RAPIDAPI_KEY.
    Subscribing to a listing is a manual step (not done by this code). Response mapping is best-effort:
    adjust `_map` to the listing you subscribe to. NOT exercised live (quota is reserved for flights/hotels).
    Results are embed-only (no reuse license)."""
    name = "rapidapi"
    needs = ("RAPIDAPI_KEY", "VIDEO_SCOUT_RAPIDAPI_HOST", "VIDEO_SCOUT_RAPIDAPI_PATH")

    def available(self) -> bool:
        return config.flag("VIDEO_SCOUT_ENABLE_RAPIDAPI") and super().available()

    def search(self, query: str, limit: int = 25, licensed: bool = False) -> List[Video]:
        if licensed:
            return []
        host = config.env("VIDEO_SCOUT_RAPIDAPI_HOST")
        r = requests.get(f"https://{host}{config.env('VIDEO_SCOUT_RAPIDAPI_PATH')}", timeout=TIMEOUT,
                         headers={"X-RapidAPI-Key": config.env("RAPIDAPI_KEY"), "X-RapidAPI-Host": host},
                         params={config.env("VIDEO_SCOUT_RAPIDAPI_QUERY_PARAM", "keywords"): query, "count": limit})
        r.raise_for_status()
        return [self._finish(v) for v in self._map(r.json(), query)][:limit]

    def _map(self, data, query) -> List[Video]:
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, dict):
            items = items.get("videos") or items.get("items") or []
        out = []
        for it in items or []:
            vid = str(it.get("video_id") or it.get("aweme_id") or it.get("id") or "")
            author = it.get("author") or {}
            handle = author.get("unique_id") if isinstance(author, dict) else str(author)
            if not vid:
                continue
            out.append(Video(id=f"tiktok:{vid}", platform="tiktok",
                             url=it.get("share_url") or f"https://www.tiktok.com/@{handle}/video/{vid}",
                             title=it.get("title") or it.get("desc") or "", creator=handle or "",
                             views=it.get("play_count"), likes=it.get("digg_count"),
                             published=_ymd(datetime.utcfromtimestamp(it["create_time"]).strftime("%Y%m%d")) if it.get("create_time") else None,
                             thumbnail=it.get("cover") or "", query=query))
        return out


# ---------------------------------------------------------------- Mock (tests / offline)
class MockProvider(VideoProvider):
    name = "mock"

    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 25, licensed: bool = False) -> List[Video]:
        rows = [
            ("youtube:mock1", "youtube", "I Stayed in the World's Most Expensive Hotel Room in Dubai", 25_000_000, "2025-06-01", "CC-BY"),
            ("youtube:mock2", "youtube", "Tokyo Capsule Hotel Tour", 9_000_000, "2024-01-10", "YOUTUBE-STANDARD"),
            ("commons:mock3", "commons", "Marina Bay Sands infinity pool, Singapore", 120_000, "2022-03-03", "CC-BY-SA"),
            ("pexels:mock4", "pexels", "Luxury Resort Pool Maldives", None, None, "PEXELS"),
            ("archive:mock5", "archive", "Grand Hotel travelogue 1952", 40_000, "2010-05-05", "PD"),
            ("youtube:mock6", "youtube", "Overwater villa tour Bora Bora (NC clip)", 3_000_000, "2025-09-09", "NC-OR-ND"),
        ]
        out = []
        for i, (vid, plat, title, views, pub, lic) in enumerate(rows):
            v = Video(id=vid, platform=plat, url=f"https://example.com/{vid.replace(':', '/')}", title=title,
                      creator=f"Creator {i + 1}", views=views, likes=(views // 40 if views else None), published=pub,
                      duration=45.0, license_code=lic, license_name=licenses.label(lic),
                      download_url=f"https://example.com/{vid}.mp4", query=query)
            out.append(self._finish(v))
        if licensed:
            out = [v for v in out if v.reusable]
        return out[:limit]


PROVIDERS: Dict[str, Type[VideoProvider]] = {
    "youtube": YtDlpYouTube, "youtube_api": YouTubeDataAPI, "commons": WikimediaCommons, "archive": InternetArchive,
    "pexels": Pexels, "pixabay": Pixabay, "rapidapi": RapidAPISocial, "mock": MockProvider,
}
DEFAULT_ORDER = ["youtube", "youtube_api", "commons", "archive", "pexels", "pixabay", "rapidapi"]


def build(names: Optional[List[str]] = None) -> List[VideoProvider]:
    """Providers to use: explicit names, else VIDEO_SCOUT_PROVIDERS env (comma list), else every available default."""
    if not names:
        env_names = config.env("VIDEO_SCOUT_PROVIDERS")
        names = [n.strip() for n in env_names.split(",") if n.strip()] if env_names else DEFAULT_ORDER
    out = []
    for n in names:
        cls = PROVIDERS.get(n)
        if not cls:
            raise ValueError(f"unknown provider {n!r}; choose from {sorted(PROVIDERS)}")
        p = cls()
        if n == "mock" or p.available():
            out.append(p)
    return out
