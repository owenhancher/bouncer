"""Load current points deals (transfer bonuses, buy-points sales) from deals.json.

Advice-only reference data. Update deals.json in daily batches; expired deals
are filtered out at load time.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

DEALS_PATH = Path(__file__).with_name("deals.json")


def _parse(d: Optional[str]) -> Optional[date]:
    return date.fromisoformat(d) if d else None


def days_left(ends: Optional[str], today: date) -> Optional[int]:
    end = _parse(ends)
    return None if end is None else (end - today).days


def is_active(deal: Dict[str, Any], today: date) -> bool:
    end = _parse(deal.get("ends"))
    return end is None or end >= today  # ends date is inclusive; None = ongoing


def _sort_key(deal: Dict[str, Any]):
    end = _parse(deal.get("ends"))
    return (end is None, end or date.max)


def load_deals(today: Optional[date] = None, path: Path = DEALS_PATH) -> Dict[str, Any]:
    """Return {as_of, transfer_bonuses, buy_points_sales} with expired deals removed, sorted by end date."""
    today = today or date.today()
    raw = json.loads(Path(path).read_text())
    out: Dict[str, Any] = {"as_of": raw.get("as_of")}
    for key in ("transfer_bonuses", "buy_points_sales"):
        deals = [d for d in raw.get(key, []) if is_active(d, today)]
        out[key] = sorted(deals, key=_sort_key)
    # Hotel lists use free-text dates, so they're passed through in file order.
    for key in ("trending_hotels", "hotel_promos"):
        out[key] = list(raw.get(key, []))
    return out
