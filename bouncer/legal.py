"""Load Bouncer's legal pages (Markdown drafts in /legal)."""
from __future__ import annotations

from pathlib import Path

LEGAL_DIR = Path(__file__).resolve().parent.parent / "legal"

PAGES = {
    "Privacy": "privacy.md",
    "Terms": "terms.md",
    "Disclaimer": "disclaimer.md",
    "Affiliate disclosure": "affiliate-disclosure.md",
}


def load_page(filename: str) -> str:
    return (LEGAL_DIR / filename).read_text(encoding="utf-8")


def savings_note() -> str:
    return load_page("savings-note.md").strip()
