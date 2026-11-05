"""Waitlist store: email + optional home airport. Never logs or prints emails."""
from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
DEFAULT_PATH = "data/waitlist.csv"
FIELDS = ["email", "home_airport", "created_at"]


def waitlist_path(env: Optional[dict] = None) -> Path:
    env = env or os.environ
    return Path(env.get("BOUNCER_WAITLIST_PATH") or DEFAULT_PATH)


def validate_email(email: str) -> Tuple[bool, str]:
    e = (email or "").strip().lower()
    if not e:
        return False, "Enter an email address."
    if not EMAIL_RE.match(e):
        return False, "That doesn't look like a valid email."
    return True, e


def add_entry(email: str, home_airport: str = "", path: Optional[Path] = None) -> Tuple[bool, str]:
    """Validate and append. Returns (ok, message). Dedupes on email. Never prints the email."""
    ok, normalized_or_err = validate_email(email)
    if not ok:
        return False, normalized_or_err
    email_norm = normalized_or_err
    airport = (home_airport or "").strip().upper()[:8]
    p = path or waitlist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing.add((row.get("email") or "").strip().lower())
    if email_norm in existing:
        return True, "You're already on the list. We'll be in touch."
    write_header = not p.exists() or p.stat().st_size == 0
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({
            "email": email_norm,
            "home_airport": airport,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return True, "You're on the list. We'll email you when a spot opens."
