import json
from datetime import date

from bouncer.deals import days_left, load_deals


def test_real_file_loads():
    d = load_deals(date(2026, 11, 4))
    assert d["as_of"] == "2026-11-04"
    assert len(d["transfer_bonuses"]) == 10
    assert len(d["buy_points_sales"]) == 13
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
    assert {s["program"] for s in d["buy_points_sales"]} == {"American AAdvantage", "Virgin Atlantic Flying Club", "Wyndham Rewards"}


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


from bouncer.deals import verdict, where_to_buy  # noqa: E402


def test_verdict_thresholds():
    assert verdict(0.8, 1.0)["label"] == "Good buy"
    assert verdict(0.81, 1.0)["label"] == "Fair"
    assert verdict(1.0, 1.0)["label"] == "Fair"
    assert verdict(1.01, 1.0)["label"] == "Skip"
    assert verdict(None, 1.0)["level"] == "unknown"
    assert verdict(1.0, None)["level"] == "unknown"


def test_where_to_buy_sort_and_fallback():
    sales = [
        {"program": "A", "bonus_or_discount": "", "cents_per_point": 2.0, "ends": "2026-11-10", "source_url": "src-a"},
        {"program": "B", "bonus_or_discount": "", "cents_per_point": None, "ends": "2026-11-05", "source_url": "src-b"},
        {"program": "C", "bonus_or_discount": "", "cents_per_point": 0.5, "ends": None, "source_url": "src-c",
         "buy_url": "https://official.example/buy"},
    ]
    rows = where_to_buy(sales, {"A": 1.0, "B": 1.0, "C": 1.0}, date(2026, 11, 4))
    assert [r["program"] for r in rows] == ["C", "A", "B"]
    assert rows[0]["link"] == "https://official.example/buy" and rows[0]["link_is_official"]
    assert rows[1]["link"] == "src-a" and not rows[1]["link_is_official"]
    assert rows[1]["verdict"] == "Skip" and rows[0]["verdict"] == "Good buy"
    assert rows[0]["standard_cpp"] is None and rows[0]["max_purchase"] is None  # optional fields default


def test_where_to_buy_real_data():
    from bouncer.valuations import PROGRAM_VALUES
    rows = where_to_buy(load_deals(date(2026, 11, 4))["buy_points_sales"], PROGRAM_VALUES, date(2026, 11, 4))
    assert len(rows) == 13
    ratios = [r["ratio"] for r in rows if r["ratio"] is not None]
    assert ratios == sorted(ratios)
    for r in rows:
        assert r["link"].startswith("https://")


def test_conservative_figures_and_no_sale_list():
    d = load_deals(date(2026, 11, 4))
    by = {s["program"]: s for s in d["buy_points_sales"]}
    assert by["Alaska Atmos Rewards"]["cents_per_point"] == 1.98
    assert by["Finnair Plus Avios"]["cents_per_point"] == 1.45
    assert by["Choice Privileges"]["bonus_or_discount"] == "Up to 40% bonus"
    assert all(s.get("max_purchase") is None for s in d["buy_points_sales"])
    names = {n["program"] for n in d["buy_points_no_sale"]}
    assert "ANA Mileage Club" in names and len(names) == 10


def test_official_buy_urls():
    d = load_deals(date(2026, 11, 4))
    sales = [s for s in d["buy_points_sales"] if s.get("buy_url")]
    no_sale = {n["program"]: n for n in d["buy_points_no_sale"]}
    assert len(sales) == 13
    assert no_sale["Emirates Skywards"]["standard_cpp"] == 3.0
    for k in ("Singapore KrisFlyer", "Accor Live Limitless", "ANA Mileage Club"):
        assert no_sale[k]["buy_url"] is None
