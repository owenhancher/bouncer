"""Env-driven configuration. Nothing here prints or logs secret values."""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional, mirrors the main app
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except Exception:  # pragma: no cover
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOGO = REPO_ROOT / "assets" / "bouncer-mark.png"
SITE_VIDEOS_JSON = Path(__file__).resolve().parent / "site_videos.json"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def flag(name: str) -> bool:
    return env(name).lower() in {"1", "true", "yes", "on"}


def data_dir() -> Path:
    p = Path(env("VIDEO_SCOUT_DATA_DIR") or (REPO_ROOT / "data" / "video_scout"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return Path(env("VIDEO_SCOUT_DB") or (data_dir() / "scout.db"))


def downloads_dir() -> Path:
    p = data_dir() / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exports_dir() -> Path:
    p = Path(env("VIDEO_SCOUT_EXPORTS_DIR") or (data_dir() / "exports"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def daily_cap() -> int:
    try:
        return max(0, int(env("VIDEO_SCOUT_DAILY_CAP", "3")))
    except ValueError:
        return 3


def has(*names: str) -> bool:
    return all(bool(env(n)) for n in names)
