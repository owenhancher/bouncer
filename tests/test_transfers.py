from datetime import date

from bouncer.transfers import (
    CAVEATS,
    active_bonus,
    load_partners,
    name_mismatches,
    transfer_ratio,
)
from bouncer.valuations import PROGRAM_VALUES


def test_csv_loads():
    rows = load_partners()
    assert len(rows) >= 100
    assert any(r.card_program == "Chase Ultimate Rewards" for r in rows)


def test_chase_united_ratio():
    assert transfer_ratio("Chase Ultimate Rewards", "United MileagePlus") == 1.0


def test_active_bonus_ignores_expired():
    # BA Avios 30% ends 2026-12-01
    pct, end = active_bonus("Chase Ultimate Rewards", "British Airways Avios", date(2026, 11, 5))
    assert pct == 30
    pct2, _ = active_bonus("Chase Ultimate Rewards", "British Airways Avios", date(2027, 1, 1))
    assert pct2 == 0


def test_citi_alias_and_caveats():
    assert transfer_ratio("Citi ThankYou Points", "American AAdvantage") == 1.0
    assert any("Hyatt" in c for c in CAVEATS)


def test_name_mismatches_report():
    mm = name_mismatches()
    # Known gaps: partners not in PROGRAM_VALUES are reported
    assert "cards" in mm and "partners" in mm
    # Chase itself must not be a mismatch
    assert not any("Chase Ultimate Rewards →" in x for x in mm["cards"])
