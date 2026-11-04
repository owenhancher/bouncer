"""Static loyalty program valuations (cents per point) and transfer data.

Updated from public sources like The Points Guy, NerdWallet (as of late 2026).
These are estimates; real value depends on redemption.
"""

from typing import Dict, List, Tuple

# Cents per point / mile. Higher is better for the traveler.
# Source: approximate from TPG / NerdWallet Oct/Nov 2026
PROGRAM_VALUES: Dict[str, float] = {
    # Transferable currencies
    "Amex Membership Rewards": 2.0,
    "Chase Ultimate Rewards": 2.0,
    "Citi ThankYou Points": 1.8,
    "Capital One Miles": 1.8,
    "Bilt Rewards": 2.1,
    "Wells Fargo Rewards": 1.6,
    # Airlines
    "United MileagePlus": 1.2,
    "American AAdvantage": 1.45,
    "Delta SkyMiles": 1.2,
    "Air Canada Aeroplan": 1.45,
    "Air France-KLM Flying Blue": 1.3,
    "British Airways Avios": 1.2,
    "Alaska Atmos Rewards": 1.55,
    "Avianca LifeMiles": 1.5,
    "Emirates Skywards": 1.2,
    "JetBlue TrueBlue": 1.35,
    "Southwest Rapid Rewards": 1.25,
    "Virgin Atlantic Flying Club": 1.5,
    "Singapore KrisFlyer": 1.3,
    "ANA Mileage Club": 1.4,
    # Hotels
    "World of Hyatt": 1.65,
    "Marriott Bonvoy": 0.75,
    "Hilton Honors": 0.4,
    "IHG One Rewards": 0.6,
    "Choice Privileges": 0.8,
    "Wyndham Rewards": 0.55,
    "Accor Live Limitless": 2.2,
}

# Transfer partners: from_program -> list of (to_program, base_ratio as float, e.g. 1.0 for 1:1)
# Ratio means: points_from * ratio = points_to
TRANSFER_PARTNERS: Dict[str, List[Tuple[str, float]]] = {
    "Chase Ultimate Rewards": [
        ("United MileagePlus", 1.0),
        ("Southwest Rapid Rewards", 1.0),
        ("British Airways Avios", 1.0),
        ("Air France-KLM Flying Blue", 1.0),
        ("Air Canada Aeroplan", 1.0),
        ("World of Hyatt", 1.0),  # note: sometimes 4:3 on certain cards
        ("IHG One Rewards", 1.0),
        ("Marriott Bonvoy", 1.0),
    ],
    "Amex Membership Rewards": [
        ("Delta SkyMiles", 1.0),
        ("Air France-KLM Flying Blue", 1.0),
        ("British Airways Avios", 1.0),
        ("Air Canada Aeroplan", 1.0),
        ("Hilton Honors", 2.0),  # 1:2
        ("Marriott Bonvoy", 1.0),
        ("Avianca LifeMiles", 1.0),
        ("ANA Mileage Club", 1.0),
    ],
    "Citi ThankYou Points": [
        ("American AAdvantage", 1.0),
        ("Air France-KLM Flying Blue", 1.0),
        ("Avianca LifeMiles", 1.0),
        ("Choice Privileges", 1.5),
        ("Turkish Airlines Miles&Smiles", 1.0),  # often with bonuses
    ],
    "Capital One Miles": [
        ("Air France-KLM Flying Blue", 1.0),
        ("Air Canada Aeroplan", 1.0),
        ("Avianca LifeMiles", 1.0),
        ("British Airways Avios", 1.0),
        ("Virgin Atlantic Flying Club", 1.0),
    ],
    "Bilt Rewards": [
        ("United MileagePlus", 1.0),
        ("American AAdvantage", 1.0),
        ("Air France-KLM Flying Blue", 1.0),
        ("World of Hyatt", 1.0),
        ("Alaska Atmos Rewards", 1.0),
    ],
}

# Current promotional transfer bonuses: (from, to, bonus_percent, expires)
# bonus_percent is extra, e.g. 30 means 30% more points
ACTIVE_TRANSFER_BONUSES: List[Tuple[str, str, float, str]] = [
    ("Chase Ultimate Rewards", "IHG One Rewards", 80.0, "2026-12-03"),
    ("Chase Ultimate Rewards", "British Airways Avios", 30.0, "2026-12-01"),
    ("Amex Membership Rewards", "Marriott Bonvoy", 35.0, "2026-12-10"),
    ("Amex Membership Rewards", "Virgin Atlantic Flying Club", 30.0, "2026-11-30"),
    ("Citi ThankYou Points", "Turkish Airlines Miles&Smiles", 40.0, "2026-11-30"),
    ("Capital One Miles", "Virgin Atlantic Flying Club", 30.0, "2026-11-20"),
]


def get_value(program: str) -> float:
    """Return cents-per-point for a program. Default 1.0 if unknown."""
    return PROGRAM_VALUES.get(program, 1.0)


def get_transfer_ratio(from_program: str, to_program: str) -> float:
    """Base transfer ratio (points_to / points_from). 0 if not partners."""
    partners = TRANSFER_PARTNERS.get(from_program, [])
    for partner, ratio in partners:
        if partner == to_program:
            return ratio
    return 0.0


def get_active_bonus(from_program: str, to_program: str) -> float:
    """Return current bonus percent if any, else 0."""
    for f, t, bonus, _ in ACTIVE_TRANSFER_BONUSES:
        if f == from_program and t == to_program:
            return bonus
    return 0.0
