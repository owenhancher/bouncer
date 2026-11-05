"""Posting to Bouncer's own accounts: X (API v2), Instagram Reels + Facebook Page video (Meta Graph API).
Falls back to a ready-to-post package (clip + caption + credit + hashtags + X intent link) when creds are missing.
Every post goes through rights.assert_reusable first."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import time
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from . import config, licenses
from .models import Video
from .rights import assert_reusable

GRAPH = "https://graph.facebook.com/" + (config.env("META_GRAPH_VERSION") or "v21.0")
GRAPH_VIDEO = "https://graph-video.facebook.com/" + (config.env("META_GRAPH_VERSION") or "v21.0")
RUPLOAD = "https://rupload.facebook.com/ig-api-upload/" + (config.env("META_GRAPH_VERSION") or "v21.0")
PLATFORMS = ("ig", "fb", "x")
DEFAULT_TAGS = "#hotels #travel #hoteltour #travelhacks #pointsandmiles"


@dataclass
class PostResult:
    platform: str
    status: str            # posted | package | failed | skipped
    url: str = ""
    detail: str = ""
    extra: Dict = field(default_factory=dict)


def creds_status() -> Dict[str, Dict]:
    return {
        "x": {"ready": x_ready(), "mode": "oauth2" if config.has("X_USER_ACCESS_TOKEN") else
              ("oauth1" if config.has("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET") else None),
              "needs": "X_USER_ACCESS_TOKEN (OAuth2 user token, scopes tweet.write media.write users.read offline.access) "
                       "OR X_API_KEY + X_API_SECRET + X_ACCESS_TOKEN + X_ACCESS_TOKEN_SECRET (OAuth 1.0a, Read+Write app)"},
        "ig": {"ready": config.has("META_PAGE_ACCESS_TOKEN", "IG_USER_ID"),
               "needs": "META_PAGE_ACCESS_TOKEN + IG_USER_ID (instagram_basic, instagram_content_publish, pages_show_list, pages_read_engagement)"},
        "fb": {"ready": config.has("META_PAGE_ACCESS_TOKEN", "FB_PAGE_ID"),
               "needs": "META_PAGE_ACCESS_TOKEN + FB_PAGE_ID (pages_manage_posts, pages_read_engagement, publish_video)"},
    }


def x_ready() -> bool:
    return config.has("X_USER_ACCESS_TOKEN") or config.has("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


# ------------------------------------------------------------------ captions
def build_caption(v: Video, caption: str = "", hashtags: str = DEFAULT_TAGS, platform: str = "ig") -> str:
    attr = licenses.attribution(v.creator, v.license_code, v.url, v.license_name)
    parts = [caption.strip() or (v.title.strip() + (f" · {v.location_guess}" if v.location_guess else ""))]
    if platform == "x":
        # 280 chars, URLs count 23. Keep attribution intact; trim the user text first.
        tags = " ".join(hashtags.split()[:2])
        fixed = f"\n\n{attr}\n{tags}"
        url_adj = len(v.url) - 23 if v.url and v.url in attr else 0
        room = 280 - (len(fixed) - url_adj)
        body = parts[0] if len(parts[0]) <= room else parts[0][: max(0, room - 1)].rstrip() + "…"
        return body + fixed
    return f"{parts[0]}\n\n{attr}\n\nOnly real deals get in. Follow @bouncertravel\n{hashtags}".strip()


def x_intent_link(text: str) -> str:
    return "https://x.com/intent/post?text=" + urllib.parse.quote(text, safe="")


def make_package(v: Video, clip_path: str, captions: Dict[str, str], clip_id: Optional[int] = None) -> Path:
    d = config.exports_dir() / "packages" / f"{datetime.now():%Y%m%d-%H%M%S}_{(v.id.replace(':', '_'))[:40]}"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / Path(clip_path).name
    if Path(clip_path).exists():
        shutil.copy2(clip_path, dst)
    meta = {"video_id": v.id, "clip_id": clip_id, "source_url": v.url, "creator": v.creator, "creator_url": v.creator_url,
            "license": v.license_code, "license_name": v.license_name, "license_url": v.license_url,
            "attribution": licenses.attribution(v.creator, v.license_code, v.url, v.license_name),
            "captions": captions, "x_intent": x_intent_link(captions.get("x", "")), "clip_file": str(dst)}
    (d / "post.json").write_text(json.dumps(meta, indent=2))
    for p, c in captions.items():
        (d / f"caption_{p}.txt").write_text(c)
    return d


# ------------------------------------------------------------------ X
def _oauth1_header(method: str, url: str, params: Optional[Dict[str, str]] = None) -> str:
    ck, cs = config.env("X_API_KEY"), config.env("X_API_SECRET")
    tk, ts = config.env("X_ACCESS_TOKEN"), config.env("X_ACCESS_TOKEN_SECRET")
    oauth = {"oauth_consumer_key": ck, "oauth_nonce": secrets.token_hex(16), "oauth_signature_method": "HMAC-SHA1",
             "oauth_timestamp": str(int(time.time())), "oauth_token": tk, "oauth_version": "1.0"}
    q = lambda s: urllib.parse.quote(str(s), safe="~")
    allp = {**(params or {}), **oauth}
    base_params = "&".join(f"{q(k)}={q(allp[k])}" for k in sorted(allp))
    base = "&".join([method.upper(), q(url.split("?")[0]), q(base_params)])
    sig = base64.b64encode(hmac.new(f"{q(cs)}&{q(ts)}".encode(), base.encode(), hashlib.sha1).digest()).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{q(k)}="{q(v)}"' for k, v in sorted(oauth.items()))


def _x_auth(method: str, url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    if config.has("X_USER_ACCESS_TOKEN"):
        return {"Authorization": f"Bearer {config.env('X_USER_ACCESS_TOKEN')}"}
    return {"Authorization": _oauth1_header(method, url, params)}


def post_x(path: str, text: str, session=requests) -> PostResult:
    size = os.path.getsize(path)
    u = "https://api.x.com/2/media/upload/initialize"
    r = session.post(u, headers=_x_auth("POST", u), timeout=60,
                     json={"media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"})
    r.raise_for_status()
    mid = r.json()["data"]["id"]
    with open(path, "rb") as f:
        i = 0
        while chunk := f.read(4 * 1024 * 1024):
            u = f"https://api.x.com/2/media/upload/{mid}/append"
            rr = session.post(u, headers=_x_auth("POST", u), files={"media": ("chunk", chunk, "application/octet-stream")},
                              data={"segment_index": str(i)}, timeout=120)
            rr.raise_for_status()
            i += 1
    u = f"https://api.x.com/2/media/upload/{mid}/finalize"
    r = session.post(u, headers=_x_auth("POST", u), timeout=60)
    r.raise_for_status()
    info = (r.json().get("data") or {}).get("processing_info")
    deadline = time.time() + 300
    while info and info.get("state") in ("pending", "in_progress") and time.time() < deadline:
        time.sleep(max(1, int(info.get("check_after_secs", 3))))
        u = "https://api.x.com/2/media/upload"
        p = {"command": "STATUS", "media_id": mid}
        r = session.get(u, params=p, headers=_x_auth("GET", u, p), timeout=60)
        r.raise_for_status()
        info = (r.json().get("data") or {}).get("processing_info")
    if info and info.get("state") == "failed":
        return PostResult("x", "failed", detail=f"X media processing failed: {info}")
    u = "https://api.x.com/2/tweets"
    r = session.post(u, headers=_x_auth("POST", u), json={"text": text, "media": {"media_ids": [str(mid)]}}, timeout=60)
    r.raise_for_status()
    tid = r.json()["data"]["id"]
    return PostResult("x", "posted", url=f"https://x.com/i/status/{tid}", extra={"tweet_id": tid, "media_id": mid})


# ------------------------------------------------------------------ Instagram Reels (resumable upload of local file)
def post_ig(path: str, caption: str, session=requests) -> PostResult:
    tok, ig = config.env("META_PAGE_ACCESS_TOKEN"), config.env("IG_USER_ID")
    r = session.post(f"{GRAPH}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true", "access_token": tok})
    r.raise_for_status()
    cid = r.json()["id"]
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = session.post(f"{RUPLOAD}/{cid}", data=f, timeout=600,
                         headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    r.raise_for_status()
    deadline = time.time() + 600
    status = ""
    while time.time() < deadline:
        s = session.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": tok}, timeout=60).json()
        status = s.get("status_code", "")
        if status in ("FINISHED", "ERROR", "EXPIRED"):
            break
        time.sleep(5)
    if status != "FINISHED":
        return PostResult("ig", "failed", detail=f"IG container status {status or 'timeout'}")
    r = session.post(f"{GRAPH}/{ig}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
    r.raise_for_status()
    mid = r.json()["id"]
    link = session.get(f"{GRAPH}/{mid}", params={"fields": "permalink", "access_token": tok}, timeout=60).json()
    return PostResult("ig", "posted", url=link.get("permalink", ""), extra={"media_id": mid})


# ------------------------------------------------------------------ Facebook Page video
def post_fb(path: str, caption: str, session=requests) -> PostResult:
    tok, page = config.env("META_PAGE_ACCESS_TOKEN"), config.env("FB_PAGE_ID")
    with open(path, "rb") as f:
        r = session.post(f"{GRAPH_VIDEO}/{page}/videos", timeout=900,
                         data={"description": caption, "access_token": tok},
                         files={"source": (Path(path).name, f, "video/mp4")})
    r.raise_for_status()
    vid = r.json()["id"]
    return PostResult("fb", "posted", url=f"https://www.facebook.com/{page}/videos/{vid}", extra={"video_id": vid})


POSTERS = {"x": (x_ready, post_x), "ig": (lambda: creds_status()["ig"]["ready"], post_ig),
           "fb": (lambda: creds_status()["fb"]["ready"], post_fb)}


def publish(store, clip_id: int, platforms: List[str], caption: str = "", hashtags: str = DEFAULT_TAGS,
            mode: str = "manual", dry_run: bool = False, session=requests) -> Dict:
    """Post one clip. Enforces license gate, de-dupe (same video+platform never posted twice) and daily cap."""
    c = store.get_clip(clip_id)
    if not c:
        raise KeyError(f"no clip {clip_id}")
    v = store.get(c["video_id"])
    if not v:
        raise KeyError(f"clip {clip_id} points to unknown video {c['video_id']}")
    assert_reusable(v)
    plats = [p.strip().lower() for p in platforms if p.strip()]
    plats = ["ig" if p in ("instagram", "ix") else ("fb" if p == "facebook" else p) for p in plats]
    bad = [p for p in plats if p not in PLATFORMS]
    if bad:
        raise ValueError(f"unknown platform(s) {bad}; use ig, fb, x")
    captions = {p: build_caption(v, caption, hashtags, p) for p in plats}
    results: List[PostResult] = []
    cap = config.daily_cap()
    for p in plats:
        ready, fn = POSTERS[p]
        if store.already_posted(v.id, p):
            results.append(PostResult(p, "skipped", detail="already posted this video to this platform (posted-log)"))
            continue
        if not ready():
            results.append(PostResult(p, "package", detail=f"no credentials: {creds_status()[p]['needs']}"))
            continue
        if store.posted_today(p) >= cap:
            results.append(PostResult(p, "skipped", detail=f"daily cap reached ({cap}/day, VIDEO_SCOUT_DAILY_CAP)"))
            continue
        if dry_run:
            results.append(PostResult(p, "skipped", detail="dry run"))
            continue
        try:
            res = fn(c["path"], captions[p], session=session)
        except Exception as e:
            res = PostResult(p, "failed", detail=_redact(str(e))[:400])
        results.append(res)
    pkg = None
    if any(r.status in ("package", "failed") for r in results):
        pkg = make_package(v, c["path"], captions, clip_id)
    for r in results:
        if r.status != "skipped" or "already" not in r.detail:
            store.log_post(clip_id, v.id, r.platform, r.status, r.url, r.detail, mode)
    return {"clip_id": clip_id, "video_id": v.id, "mode": mode, "results": [asdict(r) for r in results],
            "package_dir": str(pkg) if pkg else None,
            "x_intent": x_intent_link(captions["x"]) if "x" in captions else None, "captions": captions}


def _redact(s: str) -> str:
    for n in ("META_PAGE_ACCESS_TOKEN", "X_USER_ACCESS_TOKEN", "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN",
              "X_ACCESS_TOKEN_SECRET", "RAPIDAPI_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "YOUTUBE_API_KEY"):
        val = config.env(n)
        if val:
            s = s.replace(val, "***")
    return s
