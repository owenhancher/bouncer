"""Transfer partner matrix loaded from Outlook's CSV (advice layer).

Does not change engine.py / valuations.py. Maps CSV names onto the program
names Bouncer already uses, and reports any that don't match.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DATA_PATH = Path(__file__).parent / "data" / "transfer_partners.csv"

# CSV card_program / partner -> name used in valuations.PROGRAM_VALUES / balances
CARD_ALIASES: Dict[str, str] = {
    "Citi ThankYou Rewards": "Citi ThankYou Points",
    "Chase Ultimate Rewards": "Chase Ultimate Rewards",
    "Amex Membership Rewards": "Amex Membership Rewards",
    "Capital One Miles": "Capital One Miles",
    "Bilt Rewards": "Bilt Rewards",
    "Wells Fargo Rewards": "Wells Fargo Rewards",
}

PARTNER_ALIASES: Dict[str, str] = {
    "United MileagePlus": "United MileagePlus",
    "Southwest Rapid Rewards": "Southwest Rapid Rewards",
    "British Airways Executive Club (Avios)": "British Airways Avios",
    "Aer Lingus AerClub (Avios)": "British Airways Avios",  # Avios pool; engine has no Aer Lingus
    "Iberia Plus (Avios)": "British Airways Avios",
    "Finnair Plus (Avios)": "British Airways Avios",
    "Qatar Privilege Club (Avios)": "British Airways Avios",
    "Air France-KLM Flying Blue": "Air France-KLM Flying Blue",
    "Air Canada Aeroplan": "Air Canada Aeroplan",
    "World of Hyatt": "World of Hyatt",
    "IHG One Rewards": "IHG One Rewards",
    "Marriott Bonvoy": "Marriott Bonvoy",
    "Wyndham Rewards": "Wyndham Rewards",
    "Delta SkyMiles": "Delta SkyMiles",
    "Hilton Honors": "Hilton Honors",
    "Avianca LifeMiles": "Avianca LifeMiles",
    "ANA Mileage Club": "ANA Mileage Club",
    "Emirates Skywards": "Emirates Skywards",
    "Virgin Atlantic Flying Club": "Virgin Atlantic Flying Club",
    "Virgin Red (Virgin Atlantic Flying Club)": "Virgin Atlantic Flying Club",
    "Virgin Red": "Virgin Atlantic Flying Club",
    "American Airlines AAdvantage": "American AAdvantage",
    "Choice Privileges": "Choice Privileges",
    "Turkish Airlines Miles&Smiles": "Turkish Airlines Miles&Smiles",
    "JetBlue TrueBlue": "JetBlue TrueBlue",
    "Atmos Rewards (Alaska/Hawaiian)": "Alaska Atmos Rewards",
    "Singapore Airlines KrisFlyer": "Singapore KrisFlyer",
    "ALL Accor Live Limitless": "Accor Live Limitless",
    "Etihad Guest": "Etihad Guest",
    "Cathay Pacific Asia Miles": "Cathay Pacific Asia Miles",
    "Qantas Frequent Flyer": "Qantas Frequent Flyer",
    "JAL Mileage Bank": "JAL Mileage Bank",
    "Aeromexico Rewards": "Aeromexico Rewards",
    "Copa ConnectMiles": "Copa ConnectMiles",
    "TAP Air Portugal Miles&Go": "TAP Air Portugal Miles&Go",
    "Thai Royal Orchid Plus": "Thai Royal Orchid Plus",
    "EVA Air Infinity MileageLands": "EVA Air Infinity MileageLands",
    "Preferred Hotels I Prefer": "Preferred Hotels I Prefer",
    "Leading Hotels of the World Leaders Club": "Leading Hotels of the World",
    "Amtrak Guest Rewards (rail)": "Amtrak Guest Rewards",
}

CAVEATS: List[str] = [
    "Chase → Hyatt is 1:1 on Sapphire Reserve but 4:3 on Sapphire Preferred / Ink Preferred (since 2026-10-01).",
    "Citi transfer ratios are for premium cards (Strata Premier/Elite, Prestige); no-fee cards get about 70% of those.",
    "Bilt → Hyatt drops from 1:1 to 4:3 on 2027-01-01.",
]


@dataclass(frozen=True)
class TransferPartner:
    card_program: str          # canonical Bouncer name
    partner: str               # canonical Bouncer name
    ratio: float               # points_to / points_from
    ratio_label: str           # raw CSV ratio text
    bonus_pct: float           # 0 if none / expired
    bonus_end: Optional[date]
    caveat: Optional[str] = None
    raw_card: str = ""
    raw_partner: str = ""


def _parse_ratio(text: str) -> Tuple[float, Optional[str]]:
    """Parse '1:1', '4:3', '1:2', or card-dependent strings. Returns (ratio, caveat)."""
    t = (text or "").strip()
    if not t:
        return 0.0, None
    if "Sapphire" in t or "Preferred" in t:
        # Prefer Reserve 1:1 for advice; surface caveat separately.
        return 1.0, "Chase→Hyatt: 1:1 Sapphire Reserve; 4:3 Preferred/Ink Preferred"
    if "4:3 from 2027" in t or "2027-01-01" in t:
        return 1.0, "Bilt→Hyatt becomes 4:3 on 2027-01-01"
    # take the first a:b pattern
    import re
    m = re.search(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", t)
    if not m:
        return 0.0, f"Unparsed ratio: {t}"
    a, b = float(m.group(1)), float(m.group(2))
    if a <= 0:
        return 0.0, None
    return b / a, None


def _parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def load_partners(path: str = "") -> List[TransferPartner]:
    p = Path(path) if path else DATA_PATH
    out: List[TransferPartner] = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw_card = row["card_program"].strip()
            raw_partner = row["partner"].strip()
            card = CARD_ALIASES.get(raw_card, raw_card)
            partner = PARTNER_ALIASES.get(raw_partner, raw_partner)
            ratio, caveat = _parse_ratio(row["ratio"])
            bonus_raw = (row.get("current_bonus_pct") or "").strip()
            bonus_pct = float(bonus_raw) if bonus_raw else 0.0
            ends = _parse_date(row.get("bonus_end_date") or "")
            out.append(TransferPartner(
                card_program=card, partner=partner, ratio=ratio, ratio_label=row["ratio"].strip(),
                bonus_pct=bonus_pct, bonus_end=ends, caveat=caveat,
                raw_card=raw_card, raw_partner=raw_partner,
            ))
    return out


def name_mismatches(known_programs: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """Return CSV names that don't map onto a known Bouncer program."""
    from .valuations import PROGRAM_VALUES, TRANSFER_PARTNERS
    known = set(known_programs or []) | set(PROGRAM_VALUES) | set(TRANSFER_PARTNERS)
    for partners in TRANSFER_PARTNERS.values():
        known |= {p for p, _ in partners}
    unknown_cards, unknown_partners = [], []
    seen_c, seen_p = set(), set()
    for t in load_partners():
        if t.card_program not in known and t.raw_card not in seen_c:
            unknown_cards.append(f"{t.raw_card} → {t.card_program}")
            seen_c.add(t.raw_card)
        if t.partner not in known and t.raw_partner not in seen_p:
            unknown_partners.append(f"{t.raw_partner} → {t.partner}")
            seen_p.add(t.raw_partner)
    return {"cards": unknown_cards, "partners": unknown_partners}


def active_bonus(card: str, partner: str, today: Optional[date] = None) -> Tuple[float, Optional[date]]:
    today = today or date.today()
    best = 0.0
    end: Optional[date] = None
    for t in load_partners():
        if t.card_program != card or t.partner != partner:
            continue
        if t.bonus_pct <= 0:
            continue
        if t.bonus_end and t.bonus_end < today:
            continue
        if t.bonus_pct > best:
            best, end = t.bonus_pct, t.bonus_end
    return best, end


def transfer_ratio(card: str, partner: str) -> float:
    for t in load_partners():
        if t.card_program == card and t.partner == partner and t.ratio > 0:
            return t.ratio
    return 0.0


def partners_for(card: str) -> List[TransferPartner]:
    return [t for t in load_partners() if t.card_program == card]


def format_ratio(ratio: float) -> str:
    if abs(ratio - 1.0) < 1e-6:
        return "1:1"
    if abs(ratio - 2.0) < 1e-6:
        return "1:2"
    if abs(ratio - 0.75) < 1e-6:
        return "4:3"
    if abs(ratio - 1.25) < 1e-6:
        return "5:4"
    if abs(ratio - 1.5) < 1e-6:
        return "2:3" if False else "1:1.5"
    # prefer a:b with small ints
    for a in range(1, 11):
        b = round(ratio * a)
        if abs(b / a - ratio) < 1e-6:
            return f"{a}:{b}"
    return f"{ratio:.2f}x"
