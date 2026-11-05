"""Official-embed HTML for showing videos on the site (no download, no reupload -> no license needed)."""
from __future__ import annotations

import html
import re
from typing import Optional, Tuple

import requests

from .guess import guess
from .models import Video

OEMBED = {
    "youtube": "https://www.youtube.com/oembed",
    "tiktok": "https://www.tiktok.com/oembed",
    "x": "https://publish.twitter.com/oembed",
}


def detect(url: str) -> Tuple[str, str]:
    """(platform, native id) from a public URL."""
    u = url.strip()
    if m := re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})", u):
        return "youtube", m.group(1)
    if m := re.search(r"tiktok\.com/@[\w.-]+/video/(\d+)", u):
        return "tiktok", m.group(1)
    if m := re.search(r"instagram\.com/(?:reel|reels|p|tv)/([\w-]+)", u):
        return "instagram", m.group(1)
    if m := re.search(r"(?:twitter|x)\.com/\w+/status/(\d+)", u):
        return "x", m.group(1)
    if "commons.wikimedia.org" in u:
        return "commons", u.rsplit("/", 1)[-1]
    if m := re.search(r"archive\.org/details/([^/?#]+)", u):
        return "archive", m.group(1)
    raise ValueError(f"unsupported URL: {url}")


def from_url(url: str, timeout: int = 15) -> Video:
    """Build an embed-only Video record from a public post URL, using free oEmbed where it exists."""
    platform, nid = detect(url)
    v = Video(id=f"{platform}:{nid}", platform=platform, url=url.strip(), source="url")
    endpoint = OEMBED.get(platform)
    if endpoint:
        try:
            r = requests.get(endpoint, params={"url": v.url, "format": "json", "omit_script": "1"}, timeout=timeout)
            if r.ok and r.text.strip():
                d = r.json()
                v.title = d.get("title") or ""
                v.creator = d.get("author_name") or ""
                v.creator_url = d.get("author_url") or ""
                v.thumbnail = d.get("thumbnail_url") or ""
                if platform != "youtube":
                    v.embed_html = d.get("html") or ""
        except Exception:
            pass
    if platform == "youtube" and not v.thumbnail:
        v.thumbnail = f"https://i.ytimg.com/vi/{nid}/hqdefault.jpg"
    v.hotel_guess, v.location_guess = guess(v.title)
    return v


PLATFORM_NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "x": "X",
                  "commons": "Wikimedia Commons", "archive": "Internet Archive", "pexels": "Pexels", "pixabay": "Pixabay"}


def embed_html(v: Video, width: int = 340, media_height: int = 200) -> Tuple[str, int]:
    """Return (html, height) for the official embed of a video, with creator credit + link back.
    The markup is responsive (fills its column) and every value is HTML-escaped."""
    e = html.escape
    try:
        platform, nid = detect(v.url)
    except ValueError:
        platform, nid = v.platform, ""
    mh = media_height
    frame = 'style="display:block;width:100%;border:0;border-radius:10px;background:#14161B"'
    if platform == "youtube":
        if "/shorts/" in v.url:
            mh = 560
        body = (f'<iframe {frame} height="{mh}" src="https://www.youtube-nocookie.com/embed/{e(nid)}" '
                f'title="{e(v.title)}" allow="accelerometer; encrypted-media; gyroscope; '
                f'picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
    elif platform == "tiktok":
        mh = 580
        body = (f'<iframe {frame} height="{mh}" src="https://www.tiktok.com/player/v1/{e(nid)}?description=1" '
                'allow="encrypted-media; fullscreen; picture-in-picture" allowfullscreen></iframe>')
    elif platform == "instagram":
        mh = 640
        body = (f'<blockquote class="instagram-media" data-instgrm-permalink="{e(v.url)}" data-instgrm-version="14" '
                f'style="min-width:260px;width:100%;margin:0"><a href="{e(v.url)}">View on Instagram</a></blockquote>'
                '<script async src="https://www.instagram.com/embed.js"></script>')
    elif platform == "x":
        mh = 620
        body = (f'<blockquote class="twitter-tweet" data-dnt="true"><a href="{e(v.url.replace("x.com", "twitter.com"))}">'
                f'View post on X</a></blockquote><script async src="https://platform.twitter.com/widgets.js"></script>')
    elif v.download_url and v.reusable:  # Commons / Pexels / Pixabay / Archive: licensed, direct player is fine
        body = (f'<video controls preload="metadata" playsinline poster="{e(v.thumbnail)}" '
                f'style="display:block;width:100%;height:{mh}px;object-fit:cover;border-radius:10px;background:#14161B">'
                f'<source src="{e(v.download_url)}"></video>')
    else:
        body = (f'<a href="{e(v.url)}" target="_blank" rel="noopener"><img src="{e(v.thumbnail)}" '
                f'style="display:block;width:100%;height:{mh}px;object-fit:cover;border-radius:10px"></a>')
    name = PLATFORM_NAMES.get(platform, platform.title())
    credit = f'<a href="{e(v.creator_url or v.url)}" target="_blank" rel="noopener" style="color:#14161B">{e(v.creator or "the creator")}</a>'
    lic = f' · {e(v.license_name.split(" (")[0])}' if v.reusable and v.license_name else ""
    foot = ('<div style="font:13px/1.35 system-ui,-apple-system,sans-serif;color:#14161B;margin-top:8px">'
            '<div style="font-weight:700;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">'
            f'{e(v.title)}</div>'
            '<div style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:#444">'
            f'Video by {credit} on {e(name)}{lic} · '
            f'<a href="{e(v.url)}" target="_blank" rel="noopener" style="color:#B3243A;font-weight:600">Watch original ↗</a>'
            '</div></div>')
    doc = (f'<div style="max-width:{max(width, 260)}px;margin:0 auto">'
           f'<style>html,body{{margin:0;padding:0;overflow:hidden;background:transparent}}</style>{body}{foot}</div>')
    return doc, mh + 84
