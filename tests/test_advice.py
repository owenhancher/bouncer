from datetime import date

from bouncer.advice import best_summary, rank_with_advice, split_flights_hotels
from bouncer.models import CabinClass, TravelOption, TravelType
from bouncer.tracker import BalanceTracker


def _flight(pts=35000, prog="United MileagePlus", cash=550.0, award=True):
    return TravelOption(
        id="t1",
        type=TravelType.FLIGHT,
        description="United award JFK-LHR (economy)",
        cash_price=cash,
        points_required=pts if award else None,
        points_program=prog if award else None,
        taxes_fees=55.0,
        cabin_or_class="economy",
        booking_url="https://united.com/award",
        is_award_available=award,
    )


def test_affordable_now_direct():
    tr = BalanceTracker(persist=False)
    tr.set_balance("United MileagePlus", 40000)
    items = rank_with_advice([_flight()], tr)
    assert items[0].affordability == "now"
    assert "United" in items[0].advice


def test_affordable_via_transfer():
    tr = BalanceTracker(persist=False)
    tr.set_balance("Chase Ultimate Rewards", 80000, transferable=True)
    tr.set_balance("United MileagePlus", 0)
    items = rank_with_advice([_flight(cash=2000.0)], tr)
    top = items[0]
    assert top.affordability == "transfer"
    assert "Transfer" in top.advice and "Chase Ultimate Rewards" in top.advice
    assert "United MileagePlus" in top.advice
    assert top.result.gap_to_close == 0


def test_transfer_with_bonus_reduces_need(monkeypatch):
    # Capital One → Virgin has 30% bonus in CSV through 2026-11-20; use a synthetic pair
    # Chase → BA Avios has 30% through 2026-12-01
    from bouncer import transfers

    tr = BalanceTracker(persist=False)
    tr.set_balance("Chase Ultimate Rewards", 27000, transferable=True)
    opt = _flight(pts=35000, prog="British Airways Avios", cash=600)
    items = rank_with_advice([opt], tr, today=date(2026, 11, 5))
    assert items[0].affordability == "transfer"
    # 30% bonus => need ceil(35000/1.3)=26924 <= 27000
    assert items[0].result.points_used <= 27000


def test_unaffordable_labeled_last():
    tr = BalanceTracker(persist=False)
    tr.set_balance("Chase Ultimate Rewards", 1000, transferable=True)
    cash = TravelOption(
        id="c", type=TravelType.FLIGHT, description="Cash flight", cash_price=400,
        is_award_available=False,
    )
    award = _flight(pts=100000)
    items = rank_with_advice([award, cash], tr)
    assert items[-1].affordability == "unaffordable"
    assert "Need more points" in items[-1].label or "need" in items[-1].advice.lower()


def test_split_and_summary():
    tr = BalanceTracker(persist=False)
    tr.set_balance("United MileagePlus", 50000)
    flight = _flight()
    hotel = TravelOption(
        id="h", type=TravelType.HOTEL, description="Hyatt award", cash_price=1000,
        points_required=20000, points_program="World of Hyatt", is_award_available=True,
    )
    items = rank_with_advice([flight, hotel], tr)
    f, h = split_flights_hotels(items)
    assert len(f) == 1 and len(h) == 1
    assert best_summary(items).startswith("Best:")
