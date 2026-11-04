"""Abstract providers and mock implementations for travel data.

In production, swap MockFlightProvider / MockHotelProvider for real API clients
(Amadeus, Duffel, AwardTool, Seats.aero, Booking.com, etc.).
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional

from .models import TravelOption, TravelType, CabinClass


class FlightProvider(ABC):
    @abstractmethod
    def search(
        self,
        origin: str,
        destination: str,
        depart: date,
        return_date: Optional[date] = None,
        travelers: int = 1,
        cabin: CabinClass = CabinClass.ECONOMY,
    ) -> List[TravelOption]:
        ...


class HotelProvider(ABC):
    @abstractmethod
    def search(
        self,
        destination: str,
        check_in: date,
        check_out: date,
        travelers: int = 1,
    ) -> List[TravelOption]:
        ...


class MockFlightProvider(FlightProvider):
    """Clearly labeled mock data for development. Replace with real provider."""

    def search(
        self,
        origin: str,
        destination: str,
        depart: date,
        return_date: Optional[date] = None,
        travelers: int = 1,
        cabin: CabinClass = CabinClass.ECONOMY,
    ) -> List[TravelOption]:
        # Mock options for common routes
        base_cash = 550.0 if cabin == CabinClass.ECONOMY else 2200.0
        options = [
            TravelOption(
                id="mock-ua-cash",
                type=TravelType.FLIGHT,
                description=f"United nonstop {origin}-{destination} ({cabin.value})",
                cash_price=base_cash * travelers,
                points_required=None,
                taxes_fees=0,
                cabin_or_class=cabin.value,
                booking_url="https://united.com",
                is_award_available=False,
            ),
            TravelOption(
                id="mock-ua-award",
                type=TravelType.FLIGHT,
                description=f"United award {origin}-{destination} ({cabin.value})",
                cash_price=base_cash * travelers,  # cash equivalent for comparison
                points_required=35000 * travelers if cabin == CabinClass.ECONOMY else 70000 * travelers,
                points_program="United MileagePlus",
                taxes_fees=55.0 * travelers,
                cabin_or_class=cabin.value,
                booking_url="https://united.com/award",
                is_award_available=True,
                blackout=False,
            ),
            TravelOption(
                id="mock-aa-award",
                type=TravelType.FLIGHT,
                description=f"American award via partner ({cabin.value})",
                cash_price=base_cash * 0.9 * travelers,
                points_required=30000 * travelers if cabin == CabinClass.ECONOMY else 65000 * travelers,
                points_program="American AAdvantage",
                taxes_fees=45.0 * travelers,
                cabin_or_class=cabin.value,
                is_award_available=True,
                blackout=depart.month in (7, 8, 12),  # mock blackout in peak
            ),
        ]
        return options


class MockHotelProvider(HotelProvider):
    def search(
        self,
        destination: str,
        check_in: date,
        check_out: date,
        travelers: int = 1,
    ) -> List[TravelOption]:
        nights = (check_out - check_in).days or 1
        return [
            TravelOption(
                id="mock-hyatt-cash",
                type=TravelType.HOTEL,
                description=f"Hyatt hotel in {destination} ({nights} nights)",
                cash_price=220.0 * nights * travelers,
                cabin_or_class="standard",
                booking_url="https://hyatt.com",
            ),
            TravelOption(
                id="mock-hyatt-award",
                type=TravelType.HOTEL,
                description=f"Hyatt award night in {destination}",
                cash_price=220.0 * nights * travelers,
                points_required=15000 * nights * travelers,
                points_program="World of Hyatt",
                taxes_fees=0,
                is_award_available=True,
                blackout=False,
            ),
            TravelOption(
                id="mock-marriott-award",
                type=TravelType.HOTEL,
                description=f"Marriott award in {destination}",
                cash_price=180.0 * nights * travelers,
                points_required=35000 * nights * travelers,
                points_program="Marriott Bonvoy",
                taxes_fees=0,
                is_award_available=True,
            ),
        ]
