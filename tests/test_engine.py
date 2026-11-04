"""Tests for valuation math and edge cases."""

import pytest
from datetime import date, timedelta

from bouncer.models import TravelOption, TravelType, LoyaltyBalance
from bouncer.valuations import get_value, get_transfer_ratio, get_active_bonus
from bouncer.tracker import BalanceTracker
from bouncer.engine import ValuationEngine


@pytest.fixture
def tracker():
    t = BalanceTracker(storage_path="/tmp/test_balances.json")
    t.set_balance("Chase Ultimate Rewards", 100000, transferable=True)
    t.set_balance("United MileagePlus", 20000)
    t.set_balance("World of Hyatt", 5000)
    return t


@pytest.fixture
def engine(tracker):
    return ValuationEngine(tracker)


def test_program_values():
    assert get_value("Chase Ultimate Rewards") == 2.0
    assert get_value("World of Hyatt") == 1.65
    assert get_value("Unknown Program") == 1.0


def test_transfer_ratio_and_bonus():
    assert get_transfer_ratio("Chase Ultimate Rewards", "United MileagePlus") == 1.0
    assert get_transfer_ratio("Amex Membership Rewards", "Hilton Honors") == 2.0
    assert get_active_bonus("Chase Ultimate Rewards", "IHG One Rewards") == 80.0


def test_cash_vs_points_direct(engine):
    opt = TravelOption(
        id="test",
        type=TravelType.FLIGHT,
        description="Test flight",
        cash_price=500.0,
        points_required=35000,
        points_program="United MileagePlus",
        taxes_fees=50.0,
    )
    results = engine.evaluate_option(opt)
    cash = next(r for r in results if r.payment_method == "cash")
    points = next(r for r in results if r.payment_method == "points_direct")
    assert cash.effective_cost == 500.0
    # 35k * 1.2¢ = $420 + $50 = $470 < 500
    assert points.is_better_than_cash
    assert points.gap_to_close > 0  # only 20k held


def test_transfer_with_bonus(engine):
    opt = TravelOption(
        id="test-ihg",
        type=TravelType.HOTEL,
        description="IHG stay",
        cash_price=300.0,
        points_required=20000,
        points_program="IHG One Rewards",
        taxes_fees=0,
    )
    results = engine.evaluate_option(opt)
    transfer = next((r for r in results if r.payment_method == "transfer" and r.source_program == "Chase Ultimate Rewards"), None)
    assert transfer is not None
    assert transfer.transfer_bonus == 80.0
    # With 80% bonus, fewer Chase points needed


def test_blackout_date(engine):
    opt = TravelOption(
        id="blackout",
        type=TravelType.FLIGHT,
        description="Blacked out",
        cash_price=400.0,
        points_required=30000,
        points_program="United MileagePlus",
        blackout=True,
    )
    results = engine.evaluate_option(opt)
    assert len(results) == 1
    assert results[0].payment_method == "cash"


def test_expiring_points(tracker):
    tracker.set_balance("United MileagePlus", 10000, expires_on=date.today() + timedelta(days=30))
    assert tracker.is_expiring_soon("United MileagePlus")


def test_buy_points_promo(engine):
    opt = TravelOption(
        id="buy",
        type=TravelType.FLIGHT,
        description="High cash",
        cash_price=800.0,
        points_required=40000,
        points_program="United MileagePlus",
        taxes_fees=40.0,
    )
    results = engine.evaluate_option(opt)
    buy = next((r for r in results if r.payment_method == "buy_points"), None)
    assert buy is not None
    assert buy.is_better_than_cash
