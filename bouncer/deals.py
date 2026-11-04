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
    for key in ("trending_hotels", "hotel_promos", "buy_points_no_sale"):
        out[key] = list(raw.get(key, []))
    return out


# ---------------------------------------------------------------------------
# Where to buy points: verdicts vs Bouncer's valuation (read-only)
# ---------------------------------------------------------------------------
GOOD_MAX_RATIO = 0.80  # price <= 80% of value -> Good buy
FAIR_MAX_RATIO = 1.00  # price <= 100% of value -> Fair; above -> Skip

OPTIONAL_BUY_FIELDS = ("buy_url", "standard_cpp", "max_purchase", "notes")


def verdict(price_cpp: Optional[float], value_cpp: Optional[float]) -> Dict[str, Any]:
    """Classify a points purchase price against a valuation (both in cents/point)."""
    if price_cpp is None or not value_cpp:
        return {"label": "No verdict", "level": "unknown", "ratio": None}
    ratio = price_cpp / value_cpp
    if ratio <= GOOD_MAX_RATIO:
        label, level = "Good buy", "good"
    elif ratio <= FAIR_MAX_RATIO:
        label, level = "Fair", "fair"
    else:
        label, level = "Skip", "skip"
    return {"label": label, "level": level, "ratio": ratio}


def where_to_buy(sales, values: Dict[str, float], today: date):
    """Rows for the 'Where to buy points' view, best value (lowest price/value ratio) first.

    Programs without a price or a valuation sort last (then by end date).
    Falls back to source_url when no verified buy_url exists.
    """
    rows = []
    for s in sales:
        value = values.get(s["program"])
        v = verdict(s.get("cents_per_point"), value)
        row = {f: s.get(f) for f in OPTIONAL_BUY_FIELDS}
        row.update(s)
        row.update(
            value_cpp=value,
            verdict=v["label"],
            verdict_level=v["level"],
            ratio=v["ratio"],
            days_left=days_left(s.get("ends"), today),
            link=s.get("buy_url") or s["source_url"],
            link_is_official=bool(s.get("buy_url")),
        )
        rows.append(row)
    rows.sort(key=lambda r: (r["ratio"] is None, r["ratio"] or 0, _sort_key(r)))
    return rows


def load_meta(path: Path = DEALS_PATH) -> Dict[str, Any]:
    """Free-text notes from the deals file (bank points note, valuation reference)."""
    raw = json.loads(Path(path).read_text())
    return {k: raw.get(k) for k in ("bank_points_note", "valuation_reference_url")}
