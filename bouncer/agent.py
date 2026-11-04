"""Main agent interface for Bouncer."""

from datetime import date, timedelta
from typing import List, Optional

from .models import TripRequest, Recommendation, TravelOption
from .providers import FlightProvider, HotelProvider, MockFlightProvider, MockHotelProvider
from .tracker import BalanceTracker
from .engine import ValuationEngine


class Bouncer:
    """Travel-deal agent: trip request in, ranked cash-vs-points recommendations out."""

    def __init__(
        self,
        flight_provider: Optional[FlightProvider] = None,
        hotel_provider: Optional[HotelProvider] = None,
        tracker: Optional[BalanceTracker] = None,
    ):
        self.flight_provider = flight_provider or MockFlightProvider()
        self.hotel_provider = hotel_provider or MockHotelProvider()
        self.tracker = tracker or BalanceTracker()
        self.engine = ValuationEngine(self.tracker)

    def plan_trip(self, request: TripRequest) -> Recommendation:
        questions = []
        alternatives = []

        if not request.destination:
            questions.append("Destination is open-ended. Any region or vibe preference (beach, city, nature)?")
            # For demo, pick a default
            request.destination = "LHR"

        if not request.depart_date:
            questions.append("When do you want to travel? Flexible on dates?")
            request.depart_date = date.today() + timedelta(days=30)

        # Search flights
        options: List[TravelOption] = []
        if request.origin and request.destination:
            flight_opts = self.flight_provider.search(
                origin=request.origin,
                destination=request.destination,
                depart=request.depart_date,
                return_date=request.return_date,
                travelers=request.travelers,
                cabin=request.cabin,
            )
            options.extend(flight_opts)

        # Hotels if dates span
        if request.depart_date and request.return_date and request.destination:
            hotel_opts = self.hotel_provider.search(
                destination=request.destination,
                check_in=request.depart_date,
                check_out=request.return_date,
                travelers=request.travelers,
            )
            options.extend(hotel_opts)

        ranked = self.engine.rank_options(options)

        # Build summary
        if not ranked:
            summary = "No options found. Try different dates or airports."
        else:
            top = ranked[0]
            summary = (
                f"Top recommendation: {top.option.description} via {top.payment_method} "
                f"at effective ${top.effective_cost:.0f}."
            )
            if top.is_better_than_cash:
                summary += " This beats paying cash."
            if top.gap_to_close > 0:
                summary += f" You need {top.gap_to_close:,} more points (transfer or buy)."

        # Proactive alternatives
        if request.flexible_days == 0:
            alternatives.append("Consider flexible dates (±3 days) for better award space.")
        alternatives.append("Nearby airports or positioning flights can unlock cheaper awards.")
        alternatives.append("Split stays or different hotels if points balances are uneven.")

        return Recommendation(
            ranked_options=ranked,
            summary=summary,
            clarifying_questions=questions,
            alternatives=alternatives,
        )

    def update_balance(self, program: str, balance: int, transferable: bool = False) -> None:
        self.tracker.set_balance(program, balance, transferable=transferable)
