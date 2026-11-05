"""Offline airport lookup for the city/airport picker.

Data: bouncer/data/airports.csv, a trimmed OurAirports extract (public domain,
https://ourairports.com/data/) of large and medium airports with scheduled
service and an IATA code. No network calls.
"""
from __future__ import annotations

import csv
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

DATA_PATH = Path(__file__).parent / "data" / "airports.csv"

PREFERRED_IATA = {
    "new york": "JFK", "nyc": "JFK", "london": "LHR", "lon": "LHR",
    "chicago": "ORD", "paris": "CDG", "miami": "MIA", "los angeles": "LAX",
    "la": "LAX", "tokyo": "HND", "orlando": "MCO", "san francisco": "SFO",
    "washington": "DCA", "boston": "BOS", "seattle": "SEA", "dallas": "DFW",
    "houston": "IAH", "atlanta": "ATL", "denver": "DEN", "cancun": "CUN",
    "cancún": "CUN",
}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


# Metro areas whose airports sit in a different municipality than the metro name
# (e.g. EWR is in Newark). Used only for searching and labels; searches still pass
# a single IATA code, because the flight providers expect airport codes.
METRO_AREAS: Dict[str, List[str]] = {
    "New York": ["JFK", "LGA", "EWR"],
    "London": ["LHR", "LGW", "STN", "LTN", "LCY", "SEN"],
    "Washington": ["DCA", "IAD", "BWI"],
    "Chicago": ["ORD", "MDW"],
    "San Francisco Bay Area": ["SFO", "OAK", "SJC"],
    "Los Angeles": ["LAX", "BUR", "LGB", "SNA", "ONT"],
    "Miami": ["MIA", "FLL", "PBI"],
    "Paris": ["CDG", "ORY", "BVA"],
    "Tokyo": ["HND", "NRT"],
    "Milan": ["MXP", "LIN", "BGY"],
    "Rome": ["FCO", "CIA"],
    "Moscow": ["SVO", "DME", "VKO"],
    "Seoul": ["ICN", "GMP"],
    "Shanghai": ["PVG", "SHA"],
    "Beijing": ["PEK", "PKX"],
    "Stockholm": ["ARN", "BMA"],
    "Osaka": ["KIX", "ITM"],
    "Sao Paulo": ["GRU", "CGH", "VCP"],
    "Buenos Aires": ["EZE", "AEP"],
    "Toronto": ["YYZ", "YTZ"],
    "Montreal": ["YUL"],
    "Dallas": ["DFW", "DAL"],
    "Houston": ["IAH", "HOU"],
    "Bangkok": ["BKK", "DMK"],
    "Istanbul": ["IST", "SAW"],
    "Dubai": ["DXB", "DWC"],
}
_METRO_BY_CODE = {code: metro for metro, codes in METRO_AREAS.items() for code in codes}


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    size: str  # "large" | "medium"

    @property
    def metro(self) -> Optional[str]:
        m = _METRO_BY_CODE.get(self.iata)
        return m if m and m.lower() != self.city.lower() else None

    @property
    def label(self) -> str:
        city = self.city or self.name
        if self.metro:
            city = f"{city} ({self.metro} area)"
        return f"{city}, {self.country}: {self.iata}, {self.name}"


@lru_cache(maxsize=1)
def load_airports(path: Path = DATA_PATH) -> List[Airport]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Airport(r["iata"], r["name"], r["city"], r["country"], r["type"]) for r in csv.DictReader(f)]


@lru_cache(maxsize=1)
def by_code() -> Dict[str, Airport]:
    return {a.iata: a for a in load_airports()}


def get(code: str) -> Optional[Airport]:
    return by_code().get((code or "").strip().upper())


def label_for(code: str) -> str:
    a = get(code)
    return a.label if a else code


def search(query: str, limit: int = 20) -> List[Airport]:
    """Find airports by IATA code, city, metro area or airport name (case-insensitive).

    Preferred majors (JFK for New York, LHR for London, etc.) rank first when the
    query matches that city/metro.
    """
    q = _fold(query)
    if not q:
        return []
    preferred = PREFERRED_IATA.get(q)
    scored = []
    for a in load_airports():
        city, name = _fold(a.city), _fold(a.name)
        metro = _fold(a.metro or _METRO_BY_CODE.get(a.iata, ""))
        if a.iata.lower() == q:
            score = 0
        elif preferred and a.iata == preferred:
            score = 0
        elif city.startswith(q) or metro.startswith(q):
            score = 1
        elif a.iata.lower().startswith(q):
            score = 2
        elif q in city or q in metro or q in name:
            score = 3
        else:
            continue
        # Prefer the preferred major over other same-score matches
        pref_penalty = 0 if (preferred and a.iata == preferred) else (0 if not preferred else 1)
        scored.append((score, pref_penalty, a.size != "large", a.city, a.iata, a))
    scored.sort(key=lambda t: t[:5])
    return [t[-1] for t in scored[:limit]]


def picker_options() -> List[str]:
    """All IATA codes for a selectbox: large airports first, then medium, each by city."""
    return [a.iata for a in sorted(load_airports(), key=lambda a: (a.size != "large", a.city, a.iata))]
