"""Cheap hotel / location guesses from a title + description. Heuristic; curators can edit in the admin."""
from __future__ import annotations

import re
from typing import Tuple

BRANDS = [
    "Burj Al Arab", "Atlantis The Royal", "Atlantis", "Marina Bay Sands", "Bellagio", "Venetian", "Caesars Palace",
    "Wynn", "Encore", "Aria", "Cosmopolitan", "MGM Grand", "Fontainebleau", "Waldorf Astoria", "Ritz-Carlton",
    "Ritz Carlton", "Four Seasons", "St. Regis", "St Regis", "Mandarin Oriental", "Peninsula", "Park Hyatt",
    "Grand Hyatt", "Andaz", "Hyatt", "Conrad", "Hilton", "Marriott", "JW Marriott", "W Hotel", "EDITION", "Aman",
    "Six Senses", "Rosewood", "Raffles", "Fairmont", "Sofitel", "Shangri-La", "InterContinental", "Kimpton",
    "Soneva", "One&Only", "Banyan Tree", "Capella", "Bvlgari", "Nobu", "Hoshinoya", "Disney's", "Capsule Hotel",
]
PLACES = [
    "Dubai", "Abu Dhabi", "Maldives", "Bora Bora", "Bali", "Tokyo", "Kyoto", "Osaka", "Seoul", "Singapore", "Bangkok",
    "Phuket", "Hong Kong", "Paris", "London", "Rome", "Venice", "Amalfi", "Santorini", "Mykonos", "Barcelona",
    "Lisbon", "Istanbul", "New York", "NYC", "Las Vegas", "Vegas", "Miami", "Los Angeles", "Hawaii", "Maui",
    "Cancun", "Tulum", "Mexico City", "Cabo", "Bahamas", "Jamaica", "Grand Cayman", "Cape Town", "Marrakech",
    "Sydney", "Iceland", "Switzerland", "Zermatt", "Seattle", "Orlando", "Chicago", "San Francisco", "Doha", "Qatar",
]
_HOTEL_RE = re.compile(r"\b((?:[A-Z][\w'&.-]+\s){0,4}(?:Hotel|Resort|Inn|Lodge|Suites|Motel|Hostel|Palace))\b")


def guess(title: str, description: str = "") -> Tuple[str, str]:
    text = f"{title} {description[:300]}"
    hotel = ""
    for b in BRANDS:
        if re.search(rf"\b{re.escape(b)}", text, re.I):
            m = re.search(rf"((?:[A-Z][\w'&.-]+\s){{0,2}}{re.escape(b)}(?:\s[A-Z][\w'&.-]+){{0,2}})", text)
            hotel = (m.group(1) if m else b).strip()
            break
    if not hotel:
        m = _HOTEL_RE.search(title)
        if m and m.group(1).strip().lower() not in {"hotel", "the hotel", "resort", "motel"}:
            hotel = m.group(1).strip()
    place = next((p for p in PLACES if re.search(rf"\b{re.escape(p)}\b", text, re.I)), "")
    return hotel[:80], place


HOTEL_WORDS = re.compile(r"hotel|resort|suite|villa|room tour|lobby|\binn\b|lodge|motel|hostel|ryokan|capsule|"
                         r"bungalow|airbnb|penthouse|all[- ]inclusive|stayed (?:at|in)", re.I)


def is_hotel_related(title: str, extra: str = "") -> bool:
    return HOTEL_WORDS.search(f"{title} {extra}") is not None


# Never auto-post these, even if licensed (tragedy, adult, violence, games, demolition, etc.).
UNSAFE_WORDS = re.compile(r"shoot|shooting|massacre|terror|bomb|nazi|concentration camp|murder|kill|dead|death|"
                          r"demolition|fire\b|collapse|thong|underwear|lingerie|nude|naked|sex|gta\b|roblox|minecraft|"
                          r"fortnite|prank|haunted|ghost|war\b|afghanistan|riot|accident|crash", re.I)


def is_safe_for_autopost(text: str) -> bool:
    return UNSAFE_WORDS.search(text or "") is None
