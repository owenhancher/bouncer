"""SQLite store for videos, clips and posts (local; data/video_scout/scout.db by default, git-ignored)."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import config
from .models import Video

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (id TEXT PRIMARY KEY, data TEXT NOT NULL, score REAL DEFAULT 0,
  status TEXT DEFAULT 'new', show_on_site INTEGER DEFAULT 0, reusable INTEGER DEFAULT 0, updated_at TEXT);
CREATE TABLE IF NOT EXISTS clips (id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT, path TEXT, thumb TEXT,
  start REAL, end REAL, vertical INTEGER, watermark INTEGER, caption TEXT, attribution TEXT, probe TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id INTEGER, video_id TEXT, platform TEXT,
  status TEXT, url TEXT, detail TEXT, mode TEXT, day TEXT, created_at TEXT);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or config.db_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---- videos ----
    def upsert(self, v: Video, keep_curation: bool = True) -> Video:
        old = self.get(v.id)
        if old:  # re-discovery refreshes metrics but keeps curation decisions
            if keep_curation:
                v.status, v.show_on_site = old.status, old.show_on_site
            for f in ("hotel_guess", "location_guess", "embed_html", "download_url"):
                if not getattr(v, f) and getattr(old, f):
                    setattr(v, f, getattr(old, f))
            if v.license_code == "UNKNOWN" and old.license_code != "UNKNOWN":
                v.license_code, v.license_name, v.license_url = old.license_code, old.license_name, old.license_url
        self.conn.execute(
            "INSERT OR REPLACE INTO videos (id, data, score, status, show_on_site, reusable, updated_at) VALUES (?,?,?,?,?,?,?)",
            (v.id, json.dumps(v.to_dict()), v.score, v.status, int(v.show_on_site), int(v.reusable), _now()))
        self.conn.commit()
        return v

    def get(self, vid: str) -> Optional[Video]:
        r = self.conn.execute("SELECT data FROM videos WHERE id=?", (vid,)).fetchone()
        return Video.from_dict(json.loads(r["data"])) if r else None

    def list(self, limit: int = 50, status: Optional[str] = None, reusable: Optional[bool] = None,
             on_site: Optional[bool] = None, platform: Optional[str] = None) -> List[Video]:
        q, a = "SELECT data FROM videos WHERE 1=1", []
        if status:
            q += " AND status=?"; a.append(status)
        if reusable is not None:
            q += " AND reusable=?"; a.append(int(reusable))
        if on_site is not None:
            q += " AND show_on_site=?"; a.append(int(on_site))
        q += " ORDER BY score DESC LIMIT ?"; a.append(limit)
        out = [Video.from_dict(json.loads(r["data"])) for r in self.conn.execute(q, a)]
        return [v for v in out if not platform or v.platform == platform]

    def set_status(self, vid: str, status: str) -> Video:
        v = self._must(vid); v.status = status
        if status == "rejected":
            v.show_on_site = False
        return self.upsert(v, keep_curation=False)

    def set_on_site(self, vid: str, on: bool) -> Video:
        v = self._must(vid); v.show_on_site = on
        if on and v.status == "new":
            v.status = "approved"
        return self.upsert(v, keep_curation=False)

    def _must(self, vid: str) -> Video:
        v = self.get(vid)
        if not v:
            raise KeyError(f"no video with id {vid!r} (run `list` to see ids)")
        return v

    # ---- clips ----
    def add_clip(self, **kw: Any) -> int:
        kw.setdefault("created_at", _now())
        if isinstance(kw.get("probe"), dict):
            kw["probe"] = json.dumps(kw["probe"])
        cols = ",".join(kw)
        cur = self.conn.execute(f"INSERT INTO clips ({cols}) VALUES ({','.join('?' * len(kw))})", list(kw.values()))
        self.conn.commit()
        return int(cur.lastrowid)

    def get_clip(self, cid: int) -> Optional[Dict[str, Any]]:
        r = self.conn.execute("SELECT * FROM clips WHERE id=?", (int(cid),)).fetchone()
        return dict(r) if r else None

    def clips(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM clips ORDER BY id DESC LIMIT ?", (limit,))]

    # ---- posts ----
    def log_post(self, clip_id: Optional[int], video_id: str, platform: str, status: str, url: str = "",
                 detail: str = "", mode: str = "manual") -> int:
        cur = self.conn.execute(
            "INSERT INTO posts (clip_id, video_id, platform, status, url, detail, mode, day, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (clip_id, video_id, platform, status, url, detail, mode, date.today().isoformat(), _now()))
        self.conn.commit()
        return int(cur.lastrowid)

    def posts(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,))]

    def posted_today(self, platform: str) -> int:
        r = self.conn.execute("SELECT COUNT(*) c FROM posts WHERE platform=? AND status='posted' AND day=?",
                              (platform, date.today().isoformat())).fetchone()
        return int(r["c"])

    def already_posted(self, video_id: str, platform: str) -> bool:
        r = self.conn.execute("SELECT 1 FROM posts WHERE video_id=? AND platform=? AND status='posted' LIMIT 1",
                              (video_id, platform)).fetchone()
        return bool(r)

    # ---- site export ----
    def export_site_json(self, path: Optional[Path] = None) -> Path:
        """Write the site-approved videos to video_scout/site_videos.json (committed; the live site reads it)."""
        path = Path(path or config.SITE_VIDEOS_JSON)
        keep = ("id", "platform", "url", "title", "creator", "creator_url", "views", "published", "thumbnail",
                "hotel_guess", "location_guess", "license_code", "license_name", "license_url", "download_url", "embed_html")
        items = [{k: v.to_dict().get(k) for k in keep} for v in self.list(limit=200, on_site=True)]
        path.write_text(json.dumps({"updated": _now(), "videos": items}, indent=2) + "\n")
        return path
