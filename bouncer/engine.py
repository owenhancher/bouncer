"""Deal valuation engine: cash vs points, transfers, buying points."""

from datetime import date
from typing import List, Optional

from .models import TravelOption, ValuationResult, LoyaltyBalance
from .valuations import get_value, get_transfer_ratio, get_active_bonus
from .tracker import BalanceTracker


class ValuationEngine:
    def __init__(self, tracker: BalanceTracker):
        self.tracker = tracker

    def evaluate_option(self, option: TravelOption) -> List[ValuationResult]:
        """Return possible ways to pay for this option, ranked by effective cost."""
        results = []

        # 1. Cash always available
        cash_result = ValuationResult(
            option=option,
            payment_method="cash",
            effective_cost=option.cash_price,
            reasoning=f"Pay full cash price of ${option.cash_price:.0f}.",
            is_better_than_cash=False,
        )
        results.append(cash_result)

        if not option.points_required or not option.points_program or option.blackout or not option.is_award_available:
            if option.blackout:
                cash_result.reasoning += " Award blacked out on this date."
            return results

        # 2. Direct points in the award program
        program = option.points_program
        balance = self.tracker.get_balance(program)
        points_needed = option.points_required
        cpp = get_value(program)
        fees = option.taxes_fees
        points_value = (points_needed * cpp) / 100.0
        effective = points_value + fees

        gap = max(0, points_needed - balance)
        direct = ValuationResult(
            option=option,
            payment_method="points_direct",
            effective_cost=effective,
            cents_per_point=cpp,
            points_used=min(points_needed, balance),
            source_program=program,
            reasoning=(
                f"Redeem {points_needed:,} {program} at {cpp:.2f}¢/pt = ${points_value:.0f} value + ${fees:.0f} fees. "
                f"You have {balance:,}."
            ),
            is_better_than_cash=effective < option.cash_price,
            gap_to_close=gap,
        )
        results.append(direct)

        # 3. Transfer from credit card programs
        for bal in self.tracker.get_all():
            if not bal.transferable or bal.balance <= 0:
                continue
            ratio = get_transfer_ratio(bal.program, program)
            if ratio <= 0:
                continue
            bonus_pct = get_active_bonus(bal.program, program)
            effective_ratio = ratio * (1 + bonus_pct / 100.0)
            source_points_needed = int(points_needed / effective_ratio) if effective_ratio else 0
            if source_points_needed <= 0:
                continue

            source_balance = bal.balance
            transferable_value = get_value(bal.program)
            # Cost of using these transferable points
            transfer_cost = (source_points_needed * transferable_value) / 100.0 + fees
            gap_transfer = max(0, source_points_needed - source_balance)

            transfer_result = ValuationResult(
                option=option,
                payment_method="transfer",
                effective_cost=transfer_cost,
                cents_per_point=transferable_value,
                points_used=min(source_points_needed, source_balance),
                source_program=bal.program,
                transfer_bonus=bonus_pct,
                reasoning=(
                    f"Transfer from {bal.program} ({effective_ratio:.2f}x including {bonus_pct}% bonus) "
                    f"to {program}. Need ~{source_points_needed:,} {bal.program} "
                    f"(you have {source_balance:,}). Effective cost ${transfer_cost:.0f}."
                ),
                is_better_than_cash=transfer_cost < option.cash_price,
                gap_to_close=gap_transfer,
            )
            results.append(transfer_result)

        # 4. Buying points (mock promo: sometimes 1.5¢ or better)
        # Only if better than cash
        buy_rate_cpp = 1.5  # example promo
        buy_cost = (points_needed * buy_rate_cpp) / 100.0 + fees
        if buy_cost < option.cash_price:
            buy_result = ValuationResult(
                option=option,
                payment_method="buy_points",
                effective_cost=buy_cost,
                cents_per_point=buy_rate_cpp,
                points_used=points_needed,
                source_program=program,
                reasoning=(
                    f"Buy {points_needed:,} {program} at {buy_rate_cpp}¢ each during promo "
                    f"(${buy_cost:.0f} total including fees). Better than cash."
                ),
                is_better_than_cash=True,
                gap_to_close=points_needed,  # need to buy all
            )
            results.append(buy_result)

        # Sort by effective cost ascending
        results.sort(key=lambda r: r.effective_cost)
        return results

    def rank_options(self, options: List[TravelOption]) -> List[ValuationResult]:
        """Evaluate all options and return the best payment method per option, sorted by cost."""
        best_per_option = []
        for opt in options:
            evals = self.evaluate_option(opt)
            if evals:
                best_per_option.append(evals[0])  # cheapest way
        best_per_option.sort(key=lambda r: r.effective_cost)
        return best_per_option
