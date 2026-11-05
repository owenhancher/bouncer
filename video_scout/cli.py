"""Non-interactive JSON CLI (built for the chat-bot teammate and for Mark).

  python -m video_scout <command> [options]      # every command prints one JSON object to stdout
Exit code 0 = ok, 1 = error (JSON has "error"), 2 = refused by the rights gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import clipper, config, embeds, licenses, posting
from .discover import discover, summary
from .models import Video
from .rights import RightsError, assert_reusable
from .store import Store


def _out(obj, code: int = 0) -> int:
    print(json.dumps(obj, indent=2, default=str))
    return code


def _resolve_clip_source(st: Store, a) -> tuple:
    if a.id:
        v = st.get(a.id)
        if not v:
            raise KeyError(f"no video {a.id!r}")
        return v, None
    # Local/uploaded file: must declare an allowed license + creator + source.
    p = Path(a.file)
    if not p.exists():
        raise FileNotFoundError(str(p))
    code, ok = licenses.classify(a.license or "")
    v = Video(id=f"upload:{p.stem}", platform="upload", url=a.source_url or "", title=a.title or p.stem,
              creator=a.creator or ("Bouncer Travel" if code == "OWN" else ""), license_code=code,
              license_name=licenses.label(code), source="upload")
    return v, p


def cmd_discover(a, st):
    provs = a.providers.split(",") if a.providers else None
    return _out(discover(a.query, limit=a.limit, licensed=a.licensed, provider_names=provs, store=st,
                         hotel_only=not a.any_topic))


def cmd_list(a, st):
    vids = st.list(limit=a.limit, status=a.status, reusable=True if a.licensed else None,
                   on_site=True if a.on_site else None, platform=a.platform)
    return _out({"count": len(vids), "videos": [summary(v) for v in vids]})


def cmd_show(a, st):
    v = st.get(a.id)
    return _out(v.to_dict()) if v else _out({"error": f"no video {a.id!r}"}, 1)


def cmd_add_url(a, st):
    v = embeds.from_url(a.url)
    if a.license:
        v.license_code, _ = licenses.classify(a.license)
        v.license_name = licenses.label(v.license_code)
    if a.creator:
        v.creator = a.creator
    st.upsert(v)
    return _out(summary(v))


def cmd_status(a, st):
    v = st.set_status(a.id, a.status)
    return _out(summary(v))


def cmd_embed_approve(a, st):
    v = st.set_on_site(a.id, not a.remove)
    path = st.export_site_json()
    return _out({"video": summary(v), "site_json": str(path),
                 "note": "commit video_scout/site_videos.json and set BOUNCER_SHOW_VIDEOS=1 for the live site to show it"})


def cmd_download(a, st):
    v = st.get(a.id)
    if not v:
        return _out({"error": f"no video {a.id!r}"}, 1)
    return _out({"id": v.id, "path": str(clipper.download(v))})


def cmd_clip(a, st):
    v, local = _resolve_clip_source(st, a)
    assert_reusable(v)
    attr = licenses.attribution(v.creator, v.license_code, None, v.license_name)
    if local is not None:
        st.upsert(v)
        out = clipper.clip(local, a.start, a.end, vertical=a.vertical, watermark=a.watermark, caption=a.caption or "",
                           attribution=attr if v.license_code != "OWN" else "")
    else:
        out = clipper.clip_video(v, a.start, a.end, vertical=a.vertical, watermark=a.watermark, caption=a.caption or "")
    cid = st.add_clip(video_id=v.id, path=out["path"], thumb=out["thumbnail"], start=clipper._parse_time(a.start),
                      end=clipper._parse_time(a.end), vertical=int(a.vertical), watermark=int(a.watermark),
                      caption=a.caption or "", attribution=attr, probe=out["probe"])
    return _out({"clip_id": cid, "video_id": v.id, **out, "attribution": attr})


def cmd_preview(a, st):
    c = st.get_clip(a.clip_id)
    if not c:
        return _out({"error": f"no clip {a.clip_id}"}, 1)
    thumb = c.get("thumb") or str(clipper.thumbnail(Path(c["path"])))
    if not Path(thumb).exists():
        thumb = str(clipper.thumbnail(Path(c["path"])))
    return _out({"clip_id": c["id"], "video_id": c["video_id"], "path": c["path"], "thumbnail": thumb,
                 "probe": clipper.probe(Path(c["path"]))})


def cmd_clips(a, st):
    return _out({"clips": st.clips(a.limit)})


def cmd_post(a, st):
    res = posting.publish(st, a.clip_id, a.platforms.split(","), caption=a.caption or "",
                          hashtags=a.hashtags, mode="manual", dry_run=a.dry_run)
    return _out(res)


def cmd_autopost(a, st):
    from . import autopost
    res = autopost.run(platforms=a.platforms.split(",") if a.platforms else None,
                       queries=a.query or None, discover_first=not a.no_discover, seconds=a.seconds, start=a.start,
                       provider_names=a.providers.split(",") if a.providers else None, dry_run=a.dry_run, store=st)
    return _out(res)


def cmd_posts(a, st):
    return _out({"posts": st.posts(a.limit), "daily_cap": config.daily_cap(),
                 "today": {p: st.posted_today(p) for p in posting.PLATFORMS}})


def cmd_creds(a, st):
    return _out({"posting": posting.creds_status(),
                 "discovery": {"YOUTUBE_API_KEY": config.has("YOUTUBE_API_KEY"), "PEXELS_API_KEY": config.has("PEXELS_API_KEY"),
                               "PIXABAY_API_KEY": config.has("PIXABAY_API_KEY"),
                               "rapidapi_enabled": config.flag("VIDEO_SCOUT_ENABLE_RAPIDAPI")}})


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m video_scout", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("discover", help="search providers, rank by virality, store results")
    p.add_argument("--query", "-q", default="hotel room tour"); p.add_argument("--limit", "-n", type=int, default=25)
    p.add_argument("--licensed", action="store_true", help="only free-reuse licensed results (clippable)")
    p.add_argument("--any-topic", action="store_true", help="keep results without hotel keywords in the title")
    p.add_argument("--providers", help="comma list: youtube,youtube_api,commons,archive,pexels,pixabay,rapidapi,mock")
    p.set_defaults(fn=cmd_discover)
    p = sub.add_parser("list", help="ranked videos in the store")
    p.add_argument("--limit", "-n", type=int, default=25); p.add_argument("--status", choices=["new", "approved", "rejected"])
    p.add_argument("--licensed", action="store_true"); p.add_argument("--on-site", action="store_true")
    p.add_argument("--platform"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("add-url", help="add a known TikTok/IG/X/YouTube URL (embed-only unless --license given)")
    p.add_argument("url"); p.add_argument("--license"); p.add_argument("--creator"); p.set_defaults(fn=cmd_add_url)
    for name, status in (("approve", "approved"), ("reject", "rejected")):
        p = sub.add_parser(name); p.add_argument("id"); p.set_defaults(fn=cmd_status, status=status)
    p = sub.add_parser("embed-approve", help="show this video on the site (official embed) and export site_videos.json")
    p.add_argument("id"); p.add_argument("--remove", action="store_true"); p.set_defaults(fn=cmd_embed_approve)
    p = sub.add_parser("download", help="download a LICENSED video's source"); p.add_argument("id"); p.set_defaults(fn=cmd_download)
    p = sub.add_parser("clip", help="trim (and optionally 9:16 crop / watermark / caption) a licensed video or local file")
    g = p.add_mutually_exclusive_group(required=True); g.add_argument("--id"); g.add_argument("--file")
    p.add_argument("--start", required=True, help="seconds or mm:ss"); p.add_argument("--end", required=True)
    p.add_argument("--vertical", action="store_true"); p.add_argument("--watermark", action="store_true")
    p.add_argument("--caption", default="")
    p.add_argument("--license", help="for --file: CC0, PD, CC-BY, CC-BY-SA, PEXELS, PIXABAY or OWN")
    p.add_argument("--creator"); p.add_argument("--source-url"); p.add_argument("--title")
    p.set_defaults(fn=cmd_clip)
    p = sub.add_parser("preview", help="clip file path + thumbnail frame + ffprobe"); p.add_argument("clip_id", type=int)
    p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("clips"); p.add_argument("--limit", type=int, default=20); p.set_defaults(fn=cmd_clips)
    p = sub.add_parser("post", help="post a clip now (live if creds, else ready-to-post package + X intent link)")
    p.add_argument("clip_id", type=int); p.add_argument("--platforms", default="ig,fb,x")
    p.add_argument("--caption", default=""); p.add_argument("--hashtags", default=posting.DEFAULT_TAGS)
    p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_post)
    p = sub.add_parser("autopost", help="discover licensed -> pick top -> clip vertical -> post (no click)")
    p.add_argument("--platforms"); p.add_argument("--query", action="append", help="repeatable")
    p.add_argument("--no-discover", action="store_true", help="pick from the existing library only")
    p.add_argument("--seconds", type=float); p.add_argument("--start", type=float, help="default: 0, or 15%% in for videos > 2 min")
    p.add_argument("--providers"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_autopost)
    p = sub.add_parser("posts", help="posted-log + today's counts vs cap"); p.add_argument("--limit", type=int, default=30)
    p.set_defaults(fn=cmd_posts)
    p = sub.add_parser("creds", help="which credentials are present (never prints values)"); p.set_defaults(fn=cmd_creds)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.fn(a, Store())
    except RightsError as e:
        return _out({"error": str(e), "refused": "license"}, 2)
    except Exception as e:
        return _out({"error": f"{type(e).__name__}: {posting._redact(str(e))}"}, 1)


if __name__ == "__main__":
    sys.exit(main())
