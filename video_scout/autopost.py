"""Autopost: discover licensed -> pick top -> clip 9:16 with watermark + attribution -> post. No human click.
Owen authorized auto-posting to Bouncer's own IG / FB Page / X. Guard rails: license gate, posted-log de-dupe,
daily cap per platform (VIDEO_SCOUT_DAILY_CAP, default 3), hotel-keyword sanity filter, approved videos first."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from . import config, posting
from .clipper import clip_video
from .discover import discover
from .guess import HOTEL_WORDS, is_safe_for_autopost
from .models import Video
from .store import Store

AUTO_QUERIES = ["hotel room tour", "luxury hotel", "resort pool", "hotel suite tour", "overwater villa"]


def pick(store: Store, platforms: List[str]) -> Optional[Video]:
    def fresh(v: Video) -> bool:
        return (v.reusable and v.status != "rejected" and HOTEL_WORDS.search(f"{v.title} {v.hotel_guess}") is not None
                and (v.status == "approved" or is_safe_for_autopost(f"{v.title} {v.creator}"))
                and (v.duration is None or v.duration >= 6)
                and any(not store.already_posted(v.id, p) for p in platforms))
    approved = [v for v in store.list(limit=500, status="approved", reusable=True) if fresh(v)]
    if approved:
        return approved[0]
    rest = [v for v in store.list(limit=500, reusable=True) if fresh(v)]
    return rest[0] if rest else None


def run(platforms: Optional[List[str]] = None, queries: Optional[List[str]] = None, discover_first: bool = True,
        seconds: Optional[float] = None, start: Optional[float] = None, provider_names: Optional[List[str]] = None,
        dry_run: bool = False, store: Optional[Store] = None, clip_fn=clip_video, session=None) -> Dict:
    store = store or Store()
    platforms = platforms or (config.env("VIDEO_SCOUT_AUTOPOST_PLATFORMS") or "ig,fb,x").split(",")
    cap = config.daily_cap()
    open_plats = [p for p in platforms if store.posted_today(p) < cap]
    if not open_plats:
        return {"status": "capped", "detail": f"all platforms at daily cap ({cap})"}
    log: Dict = {"discovered": []}
    if discover_first:
        for q in queries or AUTO_QUERIES:
            res = discover(q, limit=15, licensed=True, provider_names=provider_names, store=store)
            log["discovered"].append({"query": q, "count": res["count"], "errors": res["errors"]})
    v = pick(store, open_plats)
    if not v:
        return {**log, "status": "nothing", "detail": "no licensed, unposted hotel video found"}
    secs = seconds or float(config.env("VIDEO_SCOUT_AUTOPOST_SECONDS") or 20)
    if start is None:  # skip intros on long videos: start 15% in
        start = round(float(v.duration) * 0.15, 1) if v.duration and v.duration > 120 else 0.0
    end = start + secs
    if v.duration:
        end = min(end, float(v.duration))
    s = max(0.0, min(start, end - 3))
    out = clip_fn(v, s, end, vertical=True, watermark=True, caption=(v.hotel_guess or v.location_guess or "")[:40])
    cid = store.add_clip(video_id=v.id, path=out["path"], thumb=out.get("thumbnail"), start=s, end=end, vertical=1,
                         watermark=1, caption="", attribution="auto", probe=out.get("probe"))
    kw = {"session": session} if session is not None else {}
    res = posting.publish(store, cid, open_plats, mode="auto", dry_run=dry_run, **kw)
    return {**log, "status": "ok", "picked": {"id": v.id, "title": v.title, "license": v.license_code, "url": v.url},
            "clip": out, "post": res}
