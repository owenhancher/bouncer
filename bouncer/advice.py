"""Affordable-first ranking layer on top of engine output (no engine changes).

Sorts/filters ValuationResults and invents concrete transfer advice using the
Outlook transfer-partners CSV.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from datetime import date
from typing import List, Optional, Sequence

from .models import TravelOption, TravelType, ValuationResult
from .tracker import BalanceTracker
from .transfers import active_bonus, format_ratio, transfer_ratio
from .valuations import get_value


METHOD_LABELS = {
    "cash": "Cash",
    "points_direct": "Points you already have",
    "transfer": "Transfer & book",
    "buy_points": "Buy points",
}

CABIN_LABELS = {
    "economy": "Economy",
    "premium_economy": "Premium economy",
    "business": "Business",
    "first": "First",
}


@dataclass
class AdviceItem:
    result: ValuationResult
    affordability: str  # "now" | "transfer" | "unaffordable" | "cash"
    advice: str
    label: str  # short badge


def method_label(method: str) -> str:
    return METHOD_LABELS.get(method, method.replace("_", " ").title())


def cabin_label(cabin: str) -> str:
    return CABIN_LABELS.get(cabin, cabin.replace("_", " ").title())


def money(n: float) -> str:
    return f"${n:,.0f}"


def _booking_hint(option: TravelOption) -> str:
    if option.booking_url:
        # keep host only for the sentence
        host = option.booking_url.split("//")[-1].split("/")[0]
        return f"then book on {host}"
    prog = option.points_program or "the program"
    return f"then book with {prog}"


def _transfer_advice(card: str, partner: str, pts: int, ratio: float, bonus: float, option: TravelOption) -> str:
    ratio_txt = format_ratio(ratio)
    bonus_bit = f" with a {bonus:g}% transfer bonus" if bonus else ""
    return (
        f"Transfer {pts:,} {card} → {partner} ({ratio_txt}{bonus_bit}), "
        f"{_booking_hint(option)}."
    )


def _plan_for_option(option: TravelOption, tracker: BalanceTracker, today: Optional[date] = None) -> AdviceItem:
    """Pick the best affordable payment path for one option."""
    today = today or date.today()
    cash = ValuationResult(
        option=option,
        payment_method="cash",
        effective_cost=option.cash_price,
        reasoning=f"Pay full cash price of {money(option.cash_price)}.",
        is_better_than_cash=False,
    )

    if (
        not option.points_required
        or not option.points_program
        or option.blackout
        or not option.is_award_available
    ):
        reason = cash.reasoning
        if option.blackout:
            reason += " Award blacked out on this date."
        return AdviceItem(replace(cash, reasoning=reason), "cash", reason, "Cash")

    program = option.points_program
    need = option.points_required
    fees = option.taxes_fees
    bal = tracker.get_balance(program)
    cpp = get_value(program)
    direct_cost = (need * cpp) / 100.0 + fees

    # Affordable now with points already in the program
    if bal >= need:
        r = ValuationResult(
            option=option,
            payment_method="points_direct",
            effective_cost=direct_cost,
            cents_per_point=cpp,
            points_used=need,
            source_program=program,
            reasoning=f"Redeem {need:,} {program} you already have. Taxes/fees {money(fees)}.",
            is_better_than_cash=direct_cost < option.cash_price,
            gap_to_close=0,
        )
        advice = f"Book with your {program} balance ({need:,} pts)" + (
            f" on {option.booking_url.split('//')[-1].split('/')[0]}" if option.booking_url else ""
        ) + "."
        return AdviceItem(r, "now", advice, "You can book now")

    # Transfers that fully cover the gap
    transfer_candidates: List[AdviceItem] = []
    for b in tracker.get_all():
        if not b.transferable or b.balance <= 0:
            continue
        ratio = transfer_ratio(b.program, program)
        if ratio <= 0:
            continue
        bonus, _ = active_bonus(b.program, program, today)
        effective_ratio = ratio * (1 + bonus / 100.0)
        source_need = math.ceil(need / effective_ratio) if effective_ratio else 0
        if source_need <= 0 or b.balance < source_need:
            continue
        tv = get_value(b.program)
        cost = (source_need * tv) / 100.0 + fees
        r = ValuationResult(
            option=option,
            payment_method="transfer",
            effective_cost=cost,
            cents_per_point=tv,
            points_used=source_need,
            source_program=b.program,
            transfer_bonus=bonus,
            reasoning=_transfer_advice(b.program, program, source_need, ratio, bonus, option),
            is_better_than_cash=cost < option.cash_price,
            gap_to_close=0,
        )
        transfer_candidates.append(
            AdviceItem(r, "transfer", r.reasoning, "Transfer & book")
        )

    # Surface an affordable transfer path when one exists so the UI can show
    # concrete "Transfer X → Y" advice. Global sort by effective cost still lets
    # cheaper cash win the overall "Best" slot.
    if transfer_candidates:
        transfer_candidates.sort(key=lambda a: a.result.effective_cost)
        return transfer_candidates[0]

    # Unaffordable award — label clearly (not as Cash)
    gap = need - bal
    r = ValuationResult(
        option=option,
        payment_method="points_direct",
        effective_cost=direct_cost,
        cents_per_point=cpp,
        points_used=bal,
        source_program=program,
        reasoning=(
            f"Needs {need:,} {program}; you have {bal:,} (short {gap:,}). "
            f"Effective value {money(direct_cost)} vs cash {money(option.cash_price)}."
        ),
        is_better_than_cash=direct_cost < option.cash_price,
        gap_to_close=gap,
    )
    return AdviceItem(
        r, "unaffordable",
        f"Not enough points yet — need {gap:,} more {program} (or a transfer partner).",
        "Need more points",
    )


_AFFORD_RANK = {"now": 0, "transfer": 1, "cash": 2, "unaffordable": 3}


def rank_with_advice(
    options: Sequence[TravelOption],
    tracker: BalanceTracker,
    today: Optional[date] = None,
) -> List[AdviceItem]:
    """Affordable-first ranking across options.

    Completable paths (points you have, transfer that covers the gap, or cash)
    rank above unaffordable awards; within that, lowest effective cost wins.
    Transfers that cover the gap are preferred over cash on equal cost.
    """
    items = [_plan_for_option(o, tracker, today) for o in options]
    items.sort(
        key=lambda a: (
            0 if a.affordability != "unaffordable" else 1,
            1 if a.result.option.blackout else 0,
            a.result.effective_cost,
            0 if a.affordability in ("now", "transfer") else 1,
        )
    )
    return items


def split_flights_hotels(items: Sequence[AdviceItem]):
    flights = [a for a in items if a.result.option.type == TravelType.FLIGHT]
    hotels = [a for a in items if a.result.option.type == TravelType.HOTEL]
    return flights, hotels


def best_summary(items: Sequence[AdviceItem]) -> str:
    if not items:
        return "No options found. Try different dates or airports."
    flights, _hotels = split_flights_hotels(items)
    top = (flights or list(items))[0]
    o = top.result.option
    beat = " — beats cash" if top.result.is_better_than_cash else ""
    return f"Best: {o.description} ({money(top.result.effective_cost)}{beat}) — {top.advice}"
