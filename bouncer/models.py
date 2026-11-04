"""Data models for trips, options, balances, and recommendations."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, List, Dict


class CabinClass(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


class TravelType(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    CAR = "car"
    ACTIVITY = "activity"


@dataclass
class TripRequest:
    origin: str  # airport code or city
    destination: Optional[str] = None  # None for "anywhere"
    depart_date: Optional[date] = None
    return_date: Optional[date] = None
    flexible_days: int = 0
    travelers: int = 1
    cabin: CabinClass = CabinClass.ECONOMY
    max_cash_budget: Optional[float] = None
    preferences: Dict = field(default_factory=dict)


@dataclass
class LoyaltyBalance:
    program: str  # e.g. "Chase Ultimate Rewards", "United MileagePlus"
    balance: int
    expires_on: Optional[date] = None
    transferable: bool = False  # True for credit card programs


@dataclass
class TravelOption:
    """A single bookable option (flight, hotel, etc.)."""
    id: str
    type: TravelType
    description: str
    cash_price: float  # total USD
    points_required: Optional[int] = None
    points_program: Optional[str] = None  # loyalty program for award
    taxes_fees: float = 0.0  # cash taxes/fees on award
    cabin_or_class: str = "standard"
    details: Dict = field(default_factory=dict)
    booking_url: Optional[str] = None
    is_award_available: bool = True
    blackout: bool = False


@dataclass
class ValuationResult:
    option: TravelOption
    payment_method: str  # "cash", "points_direct", "transfer", "buy_points"
    effective_cost: float  # in USD equivalent
    cents_per_point: Optional[float] = None
    points_used: int = 0
    source_program: Optional[str] = None
    transfer_bonus: float = 0.0
    reasoning: str = ""
    is_better_than_cash: bool = False
    gap_to_close: int = 0  # points still needed


@dataclass
class Recommendation:
    ranked_options: List[ValuationResult]
    summary: str
    clarifying_questions: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
