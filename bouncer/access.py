"""Demo mode + live-search access code and per-session cap."""
from __future__ import annotations

import os
from typing import Optional, Tuple


def live_code(env: Optional[dict] = None) -> str:
    env = env or os.environ
    return (env.get("BOUNCER_LIVE_CODE") or "").strip()


def live_cap(env: Optional[dict] = None) -> int:
    env = env or os.environ
    try:
        return max(0, int(env.get("BOUNCER_LIVE_SEARCH_CAP") or "3"))
    except ValueError:
        return 3


def live_unlocked(entered_code: str, env: Optional[dict] = None) -> bool:
    code = live_code(env)
    if not code:
        return False
    return (entered_code or "").strip() == code


def can_run_live(entered_code: str, searches_used: int, env: Optional[dict] = None) -> Tuple[bool, str]:
    if not live_unlocked(entered_code, env):
        return False, "Live search needs an access code. You're in demo mode with sample prices."
    cap = live_cap(env)
    if searches_used >= cap:
        return False, f"Live search limit reached ({cap} per session). Back to sample data for now."
    return True, ""
