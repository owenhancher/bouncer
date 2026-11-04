import json
from datetime import date

from bouncer.deals import days_left, load_deals


def test_real_file_loads():
    d = load_deals(date(2026, 11, 4))
    assert d["as_of"] == "2026-11-04"
    assert len(d["transfer_bonuses"]) == 10
    assert len(d["buy_points_sales"]) == 10
    for t in d["transfer_bonuses"]:
        assert {"bank", "partner", "bonus_pct", "ends", "source_url"} <= t.keys()


def test_expired_filtered_and_sorted(tmp_path):
    p = tmp_path / "deals.json"
    p.write_text(json.dumps({
        "as_of": "2026-11-04",
        "transfer_bonuses": [
            {"bank": "A", "partner": "X", "bonus_pct": 10, "ends": "2026-11-01", "source_url": "u"},
            {"bank": "B", "partner": "Y", "bonus_pct": 20, "ends": "2026-12-01", "source_url": "u"},
            {"bank": "C", "partner": "Z", "bonus_pct": 30, "ends": "2026-11-10", "source_url": "u"},
        ],
        "buy_points_sales": [
            {"program": "P", "bonus_or_discount": "x", "cents_per_point": None, "ends": None, "note": "", "source_url": "u"},
            {"program": "Q", "bonus_or_discount": "y", "cents_per_point": 1.0, "ends": "2026-11-03", "note": "", "source_url": "u"},
            {"program": "R", "bonus_or_discount": "z", "cents_per_point": 1.0, "ends": "2026-11-04", "note": "", "source_url": "u"},
        ],
    }))
    d = load_deals(date(2026, 11, 4), path=p)
    assert [t["bank"] for t in d["transfer_bonuses"]] == ["C", "B"]
    assert [s["program"] for s in d["buy_points_sales"]] == ["R", "P"]  # ends-today kept, ongoing last


def test_all_real_deals_expire_eventually():
    d = load_deals(date(2027, 1, 1))
    assert d["transfer_bonuses"] == []
    assert [s["program"] for s in d["buy_points_sales"]] == ["American AAdvantage"]


def test_days_left():
    assert days_left("2026-11-14", date(2026, 11, 4)) == 10
    assert days_left(None, date(2026, 11, 4)) is None


HOTEL_FIELDS = {"name", "location", "program", "points_or_price", "date", "why", "source_url"}


def test_hotel_sections_load():
    d = load_deals(date(2026, 11, 4))
    assert len(d["trending_hotels"]) == 10
    assert len(d["hotel_promos"]) == 6
    for h in d["trending_hotels"] + d["hotel_promos"]:
        assert HOTEL_FIELDS <= h.keys()
        assert h["source_url"].startswith("https://")
    # Unknown rates stay null rather than invented
    red_sea = next(h for h in d["trending_hotels"] if "Red Sea" in h["name"])
    assert red_sea["points_or_price"] is None


def test_hotel_sections_default_empty(tmp_path):
    p = tmp_path / "deals.json"
    p.write_text(json.dumps({"as_of": "2026-11-04", "transfer_bonuses": [], "buy_points_sales": []}))
    d = load_deals(date(2026, 11, 4), path=p)
    assert d["trending_hotels"] == [] and d["hotel_promos"] == []
