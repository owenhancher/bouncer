"""Optional live data providers for Bouncer, with mock fallback.

Providers:
  * FlightPowersFlightProvider  - cash fares (Google Flights Live API on RapidAPI)
  * FlightPowersHotelProvider   - cash hotel rates (Booking Live API, FlightPowers)
  * AwardTravelFinderProvider   - British Airways / Cathay Pacific award seats
  * CompositeFlightProvider     - merges providers, falls back to mocks

Use ``build_providers_from_env()`` to get (flight_provider, hotel_provider, source_label).
No network calls happen at import time or when keys are absent.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from .models import CabinClass, TravelOption, TravelType
from .providers import FlightProvider, HotelProvider, MockFlightProvider, MockHotelProvider

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT = 45

FLIGHTS_HOST = "google-flights-live-api.p.rapidapi.com"
FLIGHTS_BASE = f"https://{FLIGHTS_HOST}/api/google_flights"
# Hotels: Booking Live API on RapidAPI (verified live 2026-11-04). The FlightPowers direct
# domain (x-api-key) is kept only as a fallback.
HOTELS_HOST = "booking-live-api.p.rapidapi.com"
HOTELS_URL = f"https://{HOTELS_HOST}/search"
HOTELS_DIRECT_URL = "https://api.flightpowers.com/v1/hotels/search"

# Booking Live API wants a city name; map common airport/metro codes.
IATA_CITY = {
    "LHR": "London", "LGW": "London", "LCY": "London", "STN": "London", "LTN": "London", "LON": "London",
    "JFK": "New York", "LGA": "New York", "EWR": "New York", "NYC": "New York",
    "CDG": "Paris", "ORY": "Paris", "PAR": "Paris", "HND": "Tokyo", "NRT": "Tokyo", "TYO": "Tokyo",
    "HKG": "Hong Kong", "LAX": "Los Angeles", "SFO": "San Francisco", "MIA": "Miami", "ORD": "Chicago",
    "BOS": "Boston", "DXB": "Dubai", "SIN": "Singapore", "FCO": "Rome", "MAD": "Madrid", "BCN": "Barcelona",
    "AMS": "Amsterdam", "FRA": "Frankfurt", "DUB": "Dublin", "LIS": "Lisbon", "SYD": "Sydney",
}


def _airport_code(v: Any) -> str:
    """'New York (JFK)' -> 'JFK'; passthrough otherwise."""
    m = re.search(r"\(([A-Z]{3})\)", str(v or ""))
    return m.group(1) if m else str(v or "")


def _primary_airline(v: Any) -> str:
    """'American | Iberia, Finnair' -> 'American'; 'American, British Airways' stays (multi-carrier)."""
    return (str(v or "").split("|")[0].strip()) or "Unknown airline"
ATF_BASE = "https://awardtravelfinder.com/api/v1"

SEAT_TYPE = {
    CabinClass.ECONOMY: 1,
    CabinClass.PREMIUM_ECONOMY: 2,
    CabinClass.BUSINESS: 3,
    CabinClass.FIRST: 4,
}

# Program names matching bouncer/valuations.py where one exists.
ATF_PROGRAMS = {
    "british_airways": ("British Airways Avios", "British Airways"),
    "cathay_pacific": ("Cathay Pacific Asia Miles", "Cathay Pacific"),  # not in valuations -> default value
}

# Rough FX for award taxes quoted in non-USD currencies.
FX_TO_USD = {"USD": 1.0, "GBP": 1.27, "EUR": 1.08, "HKD": 0.128}


class ProviderError(Exception):
    pass


def load_env() -> None:
    """Load .env from project root (no-op if python-dotenv missing or file absent)."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[\d][\d,]*(?:\.\d+)?", str(v))
    return float(m.group(0).replace(",", "")) if m else None


def _dump(name: str, resp: Any) -> None:
    """If BOUNCER_DEBUG_DIR is set, save the raw response (body + status + search header). Never headers sent."""
    d = os.environ.get("BOUNCER_DEBUG_DIR")
    if not d:
        return
    try:
        import json, time
        Path(d).mkdir(parents=True, exist_ok=True)
        try:
            body = resp.json()
        except Exception:
            body = getattr(resp, "text", None)
        hdrs = getattr(resp, "headers", None) or {}
        rec = {"status": resp.status_code, "x-search-status": hdrs.get("x-search-status"), "body": body}
        (Path(d) / f"{name}_{int(time.time())}.json").write_text(json.dumps(rec, indent=1, default=str))
    except Exception as e:  # pragma: no cover
        log.debug("debug dump failed: %s", e)


def _check(resp: requests.Response, name: str) -> None:
    if resp.status_code == 429:
        raise ProviderError(f"{name}: quota/rate limit exhausted (429)")
    if resp.status_code >= 400:
        raise ProviderError(f"{name}: HTTP {resp.status_code}: {resp.text[:200]}")


# ---------------------------------------------------------------- FlightPowers flights
class FlightPowersFlightProvider(FlightProvider):
    name = "FlightPowers"

    def __init__(self, api_key: str, session: Optional[Any] = None, limit: int = 10):
        self.api_key = api_key
        self.http = session or requests
        self.limit = limit
        self.last_status: Optional[str] = None

    def search(self, origin, destination, depart, return_date=None, travelers=1, cabin=CabinClass.ECONOMY):
        body: Dict[str, Any] = {
            "from_airport": origin.upper(),
            "to_airport": destination.upper(),
            "departure_date": depart.isoformat(),
            "currency": "USD",
            "limit": self.limit,
            "seat_type": SEAT_TYPE.get(cabin, 1),
            "passengers": [1] * max(1, travelers),
        }
        if return_date:
            body["return_date"] = return_date.isoformat()
            url = f"{FLIGHTS_BASE}/roundtrip/v1"
        else:
            url = f"{FLIGHTS_BASE}/oneway/v1"
        headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": FLIGHTS_HOST,
            "Content-Type": "application/json",
        }
        resp = self.http.post(url, json=body, headers=headers, timeout=DEFAULT_TIMEOUT)
        _dump("flights_roundtrip" if return_date else "flights_oneway", resp)
        _check(resp, self.name)
        self.last_status = (resp.headers or {}).get("x-search-status") or (resp.headers or {}).get("X-Search-Status")
        data = resp.json()
        if self.last_status == "degraded" and not data:
            raise ProviderError(f"{self.name}: search degraded (incomplete), no results")
        return parse_flightpowers_flights(data, cabin, roundtrip=bool(return_date))


def parse_flightpowers_flights(data: Any, cabin: CabinClass, roundtrip: bool = False) -> List[TravelOption]:
    if isinstance(data, dict):  # defensive: tolerate {"data": [...]} / {"results": [...]}
        data = data.get("data") or data.get("results") or data.get("itineraries") or []
    out: List[TravelOption] = []
    for i, it in enumerate(data or []):
        if not isinstance(it, dict):
            continue
        # Price is the total for the passengers array sent (Google Flights quotes the party total).
        price = _num(it.get("total_price_as_number" if roundtrip else "price_as_number"))
        if price is None:
            price = _num(it.get("price_as_number")) or _num(it.get("total_price")) or _num(it.get("price"))
        if price is None:
            continue
        if roundtrip:
            airline = _primary_airline(it.get("departure_flight_airline") or it.get("airline"))
            stops = it.get("total_stops")
            details = {
                "outbound_airline": it.get("departure_flight_airline"),
                "return_airline": it.get("return_flight_airline"),
                "outbound_stops": it.get("departure_flight_stops"),
                "return_stops": it.get("return_flight_stops"),
                "outbound_duration": it.get("departure_flight_duration"),
                "return_duration": it.get("return_flight_duration"),
                "outbound_departs": it.get("departure_flight_departure_description"),
                "return_departs": it.get("return_flight_departure_description"),
                "total_duration_seconds": it.get("total_duration_seconds"),
            }
        else:
            airline = _primary_airline(it.get("airline"))
            stops = it.get("stops")
            details = {
                "airline": airline,
                "airline_raw": it.get("airline"),
                "stop_airports": [s.get("stop_airport") for s in (it.get("stops_info") or []) if isinstance(s, dict)],
                "duration": it.get("duration"),
                "duration_seconds": it.get("duration_seconds"),
                "departs": it.get("departure_description"),
                "arrives": it.get("arrival_description"),
                "stops_info": it.get("stops_info"),
                "flight_numbers": it.get("flight_numbers") or it.get("flight_number"),
            }
        details.update({
            "stops": stops,
            "source": "FlightPowers",
            "price_verdict": it.get("price_range_in_relation_to_other_periods"),
            "price_insights_low": it.get("price_insights_low"),
            "price_insights_high": it.get("price_insights_high"),
        })
        stop_txt = "nonstop" if stops == 0 else (f"{stops} stop(s)" if stops is not None else "")
        route = f"{_airport_code(it.get('from_airport'))}-{_airport_code(it.get('to_airport'))}".strip("-")
        desc = f"{airline} {stop_txt} {route} ({cabin.value}{', round trip' if roundtrip else ''})"
        out.append(TravelOption(
            id=f"fp-flight-{i}",
            type=TravelType.FLIGHT,
            description=re.sub(r"\s+", " ", desc).strip(),
            cash_price=float(price),
            points_required=None,
            points_program=None,
            taxes_fees=0.0,
            cabin_or_class=cabin.value,
            details=details,
            booking_url=it.get("buy_link"),
            is_award_available=False,
        ))
    return out


# ---------------------------------------------------------------- FlightPowers hotels
class FlightPowersHotelProvider(HotelProvider):
    name = "FlightPowers Hotels"

    def __init__(self, api_key: str, session: Optional[Any] = None, limit: int = 10,
                 direct_fallback: bool = True):
        self.api_key = api_key
        self.http = session or requests
        self.limit = limit
        self.direct_fallback = direct_fallback

    def search(self, destination, check_in, check_out, travelers=1):
        city = IATA_CITY.get(str(destination).strip().upper(), destination)
        body = {
            "destination": city,
            "checkin_date": check_in.isoformat(),
            "checkout_date": check_out.isoformat(),
            "adults": max(1, travelers),
            "children": 0,
            "currency": "USD",
        }
        headers = {"x-rapidapi-key": self.api_key, "x-rapidapi-host": HOTELS_HOST,
                   "Content-Type": "application/json"}
        try:
            resp = self.http.post(HOTELS_URL, json=body, headers=headers, timeout=DEFAULT_TIMEOUT)
            _dump("hotels", resp)
            _check(resp, self.name)
        except Exception as e:
            # 429 = quota gone; same key on the direct domain draws on the same quota, so don't retry.
            if not self.direct_fallback or "429" in str(e):
                raise
            log.warning("%s RapidAPI failed (%s); trying direct domain", self.name, e)
            resp = self.http.post(HOTELS_DIRECT_URL, json=body,
                                  headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                                  timeout=DEFAULT_TIMEOUT)
            _check(resp, self.name + " (direct)")
        opts = parse_flightpowers_hotels(resp.json(), check_in, check_out)
        return sorted(opts, key=lambda o: o.cash_price)[: self.limit]


def parse_flightpowers_hotels(data: Any, check_in: date, check_out: date) -> List[TravelOption]:
    props = data.get("properties", []) if isinstance(data, dict) else (data or [])
    nights = (check_out - check_in).days or 1
    out = []
    for i, p in enumerate(props):
        if not isinstance(p, dict):
            continue
        price = _num(p.get("price"))
        if price is None:
            price = _num(p.get("price_string"))
        if price is None:
            continue
        name = p.get("name") or "Hotel"
        n = p.get("nights") if isinstance(p.get("nights"), int) and p.get("nights") > 0 else nights
        ps = str(p.get("price_string") or "")
        currency = "USD" if ("US$" in ps or ps.startswith("$") or not ps) else re.sub(r"[\d.,\s]", "", ps) or "USD"
        out.append(TravelOption(
            id=f"fp-hotel-{i}",
            type=TravelType.HOTEL,
            description=f"{name} ({n} nights)",
            cash_price=float(price),  # Booking Live API "price" = total for the stay (nights in response)
            cabin_or_class=p.get("room_type") or "standard",
            details={k: p.get(k) for k in ("review_score", "review_count", "location", "price_string",
                                           "latitude", "longitude", "image_url")} | {
                "source": "FlightPowers", "nights": n, "currency": currency,
                "price_per_night": round(float(price) / n, 2)},
            booking_url=p.get("link"),
            is_award_available=False,
        ))
    return out


# ---------------------------------------------------------------- Award Travel Finder
class AwardTravelFinderProvider(FlightProvider):
    name = "Award Travel Finder"
    CABIN_KEYS = {
        CabinClass.ECONOMY: "economy",
        CabinClass.PREMIUM_ECONOMY: "premium_economy",
        CabinClass.BUSINESS: "business",
        CabinClass.FIRST: "first",
    }

    def __init__(self, api_key: str, airlines: Sequence[str] = ("british_airways", "cathay_pacific"),
                 session: Optional[Any] = None):
        self.api_key = api_key
        self.airlines = list(airlines)
        self.http = session or requests

    def search(self, origin, destination, depart, return_date=None, travelers=1, cabin=CabinClass.ECONOMY):
        results: List[TravelOption] = []
        errors = []
        for airline in self.airlines:
            try:
                resp = self.http.get(
                    f"{ATF_BASE}/{airline}/availability",
                    params={"departure_code": origin.upper(), "arrival_code": destination.upper(),
                            "date": depart.isoformat()},
                    headers={"X-API-Key": self.api_key},
                    timeout=DEFAULT_TIMEOUT,
                )
                _dump(f"atf_{airline}", resp)
                if resp.status_code in (202, 503):
                    raise ProviderError(f"{airline}: search pending/unavailable ({resp.status_code})")
                _check(resp, f"{self.name}/{airline}")
                results.extend(parse_award_travel_finder(resp.json(), airline, cabin, travelers))
            except Exception as e:  # per-airline isolation
                log.warning("Award Travel Finder %s failed: %s", airline, e)
                errors.append(e)
        if errors and not results and len(errors) == len(self.airlines):
            raise ProviderError(f"{self.name}: all airlines failed: {errors[0]}")
        return results


def parse_award_travel_finder(data: Any, airline: str, cabin: CabinClass, travelers: int = 1) -> List[TravelOption]:
    program, carrier = ATF_PROGRAMS.get(airline, (airline, airline))
    payload = data.get("data", data) if isinstance(data, dict) else {}
    avail = payload.get("availability") or {}
    days = avail if isinstance(avail, list) else [avail]
    route = payload.get("route", "")
    key = AwardTravelFinderProvider.CABIN_KEYS.get(cabin, "economy")
    out = []
    for d in days:
        if not isinstance(d, dict):
            continue
        c = (d.get("cabins") or {}).get(key) or {}
        pts = c.get("points")
        if not c.get("available") or pts is None:
            continue
        seats = c.get("seats")
        if isinstance(seats, int) and seats < travelers:
            continue
        cur = (c.get("taxes_currency") or "USD").upper()
        taxes = (_num(c.get("taxes")) or 0.0) * FX_TO_USD.get(cur, 1.0)
        out.append(TravelOption(
            id=f"atf-{airline}-{d.get('date', '')}-{key}",
            type=TravelType.FLIGHT,
            description=f"{carrier} award {route} ({cabin.value})".replace("  ", " "),
            # Convention from mocks: cash_price is the cash equivalent for comparison; unknown here,
            # so 0 means "no cash comparison" — the composite fills it from live cash fares if present.
            cash_price=0.0,
            points_required=int(pts) * travelers,
            points_program=program,
            taxes_fees=round(taxes * travelers, 2),
            cabin_or_class=cabin.value,
            details={"source": "Award Travel Finder", "seats": seats, "date": d.get("date"),
                     "peak": d.get("peak"), "taxes_original": c.get("taxes"), "taxes_currency": cur},
            booking_url="https://www.britishairways.com" if airline == "british_airways" else "https://www.cathaypacific.com",
            is_award_available=True,
            blackout=False,
        ))
    return out


# ---------------------------------------------------------------- Composite
class CompositeFlightProvider(FlightProvider):
    def __init__(self, providers: Sequence[FlightProvider], fallback: Optional[FlightProvider] = None):
        self.providers = list(providers)
        self.fallback = fallback or MockFlightProvider()
        self.last_errors: List[str] = []
        self.used_fallback = False

    def search(self, origin, destination, depart, return_date=None, travelers=1, cabin=CabinClass.ECONOMY):
        self.last_errors, self.used_fallback = [], False
        results: List[TravelOption] = []
        for p in self.providers:
            try:
                results.extend(p.search(origin, destination, depart, return_date, travelers, cabin))
            except Exception as e:
                msg = f"{getattr(p, 'name', type(p).__name__)}: {e}"
                log.warning("Provider failed: %s", msg)
                self.last_errors.append(msg)
        if not results:
            self.used_fallback = True
            return self.fallback.search(origin, destination, depart, return_date, travelers, cabin)
        # Give award options a cash comparison from the cheapest live cash fare in same cabin.
        cash = [o.cash_price for o in results if not o.is_award_available and o.cash_price > 0]
        if cash:
            for o in results:
                if o.is_award_available and not o.cash_price:
                    o.cash_price = min(cash)
        return results


class FallbackHotelProvider(HotelProvider):
    def __init__(self, primary: HotelProvider, fallback: Optional[HotelProvider] = None):
        self.primary = primary
        self.fallback = fallback or MockHotelProvider()
        self.used_fallback = False
        self.last_error: Optional[str] = None

    def search(self, destination, check_in, check_out, travelers=1):
        self.used_fallback, self.last_error = False, None
        try:
            res = self.primary.search(destination, check_in, check_out, travelers)
            if res:
                return res
        except Exception as e:
            self.last_error = str(e)
            log.warning("Hotel provider failed: %s", e)
        self.used_fallback = True
        return self.fallback.search(destination, check_in, check_out, travelers)


# ---------------------------------------------------------------- Factory
def _truthy(v: Optional[str]) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def build_providers_from_env(force_mock: Optional[bool] = None, env: Optional[Dict[str, str]] = None,
                             load_dotenv_file: bool = True) -> Tuple[FlightProvider, HotelProvider, str]:
    """Return (flight_provider, hotel_provider, source_label)."""
    if env is None:
        if load_dotenv_file:
            load_env()
        env = dict(os.environ)
    if force_mock is None:
        force_mock = _truthy(env.get("BOUNCER_USE_MOCK"))
    if force_mock:
        return MockFlightProvider(), MockHotelProvider(), "Mock data (forced)"

    rapid = (env.get("RAPIDAPI_KEY") or env.get("FLIGHTPOWERS_API_KEY") or "").strip()
    atf = (env.get("AWARDTRAVELFINDER_API_KEY") or "").strip()

    live_flights: List[FlightProvider] = []
    labels = []
    if rapid:
        live_flights.append(FlightPowersFlightProvider(rapid))
        labels.append("FlightPowers")
    if atf:
        live_flights.append(AwardTravelFinderProvider(atf))
        labels.append("Award Travel Finder")

    flight: FlightProvider = CompositeFlightProvider(live_flights) if live_flights else MockFlightProvider()
    hotel: HotelProvider = FallbackHotelProvider(FlightPowersHotelProvider(rapid)) if rapid else MockHotelProvider()
    label = ("Live: " + " + ".join(labels) + " (mock fallback)") if labels else "Mock data"
    return flight, hotel, label
