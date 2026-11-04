"""Tests for live providers using stub HTTP sessions (no network)."""
from datetime import date

import pytest

from bouncer.models import CabinClass, TravelType
from bouncer.providers import MockFlightProvider, MockHotelProvider
from bouncer import live_providers as lp


class Resp:
    def __init__(self, data, status=200, headers=None):
        self._d, self.status_code, self.headers, self.text = data, status, headers or {}, str(data)

    def json(self):
        return self._d


class Stub:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.resp(url, kw) if callable(self.resp) else self.resp

    get = lambda self, url, **kw: (self.calls.append(("GET", url, kw)) or
                                   (self.resp(url, kw) if callable(self.resp) else self.resp))


D = date(2027, 1, 10)
R = date(2027, 1, 17)


def test_flightpowers_oneway_parse():
    data = [{"from_airport": "JFK", "to_airport": "LHR", "price": "$433", "price_as_number": 433,
             "airline": "British Airways", "stops": 0, "duration": "7 hr", "buy_link": "https://g.co/x",
             "price_range_in_relation_to_other_periods": "low"},
            {"price": "n/a"}]
    s = Stub(Resp(data, headers={"x-search-status": "ok"}))
    p = lp.FlightPowersFlightProvider("k", session=s)
    out = p.search("jfk", "lhr", D, travelers=2, cabin=CabinClass.BUSINESS)
    assert len(out) == 1 and out[0].cash_price == 433
    o = out[0]
    assert o.is_award_available is False and o.points_required is None and o.points_program is None
    assert o.details["stops"] == 0 and o.details["airline"] == "British Airways" and o.booking_url
    method, url, kw = s.calls[0]
    assert url.endswith("/oneway/v1")
    assert kw["json"]["seat_type"] == 3 and kw["json"]["passengers"] == [1, 1]
    assert kw["headers"]["x-rapidapi-host"] == lp.FLIGHTS_HOST


def test_flightpowers_roundtrip_parse():
    data = [{"total_price": "$900", "total_price_as_number": 900, "departure_flight_airline": "Delta",
             "total_stops": 1, "from_airport": "JFK", "to_airport": "LHR"}]
    s = Stub(Resp(data))
    out = lp.FlightPowersFlightProvider("k", session=s).search("JFK", "LHR", D, R)
    assert out[0].cash_price == 900 and "round trip" in out[0].description
    assert s.calls[0][1].endswith("/roundtrip/v1") and s.calls[0][2]["json"]["return_date"] == "2027-01-17"


def test_flightpowers_degraded_empty_raises():
    s = Stub(Resp([], headers={"x-search-status": "degraded"}))
    with pytest.raises(lp.ProviderError):
        lp.FlightPowersFlightProvider("k", session=s).search("JFK", "LHR", D)


def test_flightpowers_429_raises():
    with pytest.raises(lp.ProviderError):
        lp.FlightPowersFlightProvider("k", session=Stub(Resp({}, 429))).search("JFK", "LHR", D)


def test_hotels_parse():
    data = {"properties": [{"name": "The Savoy", "price": 2434.0, "price_string": "US$2,434",
                            "link": "https://booking.com/x", "review_score": 9.1, "room_type": "Deluxe"},
                           {"name": "No price"}]}
    s = Stub(Resp(data))
    out = lp.FlightPowersHotelProvider("k", session=s).search("London", D, R, 2)
    assert len(out) == 1 and out[0].type == TravelType.HOTEL and out[0].cash_price == 2434.0
    assert out[0].is_award_available is False
    assert s.calls[0][2]["json"]["destination"] == "London" and s.calls[0][2]["json"]["adults"] == 2


def _atf(points=26000, available=True, cur="GBP"):
    return {"success": True, "data": {"route": "LHR -> JFK", "availability": {
        "date": "2027-01-10", "peak": False, "cabins": {
            "economy": {"available": available, "seats": 5, "points": points, "taxes": 100, "taxes_currency": cur},
            "business": {"available": False, "seats": 0, "points": None}}}}}


def test_award_travel_finder_parse():
    out = lp.parse_award_travel_finder(_atf(), "british_airways", CabinClass.ECONOMY, travelers=2)
    assert len(out) == 1
    o = out[0]
    assert o.points_required == 52000 and o.points_program == "British Airways Avios"
    assert o.taxes_fees == pytest.approx(100 * 1.27 * 2) and o.is_award_available
    assert lp.parse_award_travel_finder(_atf(), "british_airways", CabinClass.BUSINESS) == []
    assert lp.parse_award_travel_finder(_atf(available=False), "cathay_pacific", CabinClass.ECONOMY) == []


def test_award_provider_calls_both_airlines():
    s = Stub(Resp(_atf()))
    out = lp.AwardTravelFinderProvider("k", session=s).search("LHR", "JFK", D)
    assert len(out) == 2
    assert {c[1].split("/")[-2] for c in s.calls} == {"british_airways", "cathay_pacific"}
    assert s.calls[0][2]["headers"]["X-API-Key"] == "k"


class Boom(MockFlightProvider):
    name = "boom"

    def search(self, *a, **k):
        raise ConnectionError("network down")


class Empty(MockFlightProvider):
    def search(self, *a, **k):
        return []


def test_composite_falls_back_to_mock():
    c = lp.CompositeFlightProvider([Boom(), Empty()])
    out = c.search("JFK", "LHR", D)
    assert c.used_fallback and out and all(o.id.startswith("mock-") for o in out)
    assert any("network down" in e for e in c.last_errors)


def test_composite_merges_and_fills_award_cash():
    cash = lp.FlightPowersFlightProvider("k", session=Stub(Resp([{"price_as_number": 500, "airline": "AA"}])))
    award = lp.AwardTravelFinderProvider("k", airlines=["british_airways"], session=Stub(Resp(_atf())))
    c = lp.CompositeFlightProvider([Boom(), cash, award])
    out = c.search("JFK", "LHR", D)
    assert not c.used_fallback and len(out) == 2
    assert [o for o in out if o.is_award_available][0].cash_price == 500


def test_hotel_fallback():
    class Bad(MockHotelProvider):
        def search(self, *a, **k):
            raise lp.ProviderError("429")
    h = lp.FallbackHotelProvider(Bad())
    assert h.search("London", D, R) and h.used_fallback


def test_factory_selection():
    f, h, label = lp.build_providers_from_env(env={})
    assert isinstance(f, MockFlightProvider) and isinstance(h, MockHotelProvider) and label == "Mock data"
    f, h, label = lp.build_providers_from_env(env={"RAPIDAPI_KEY": "x", "AWARDTRAVELFINDER_API_KEY": "y"})
    assert isinstance(f, lp.CompositeFlightProvider) and len(f.providers) == 2
    assert isinstance(h, lp.FallbackHotelProvider) and "FlightPowers" in label and label.startswith("Live")
    f, h, label = lp.build_providers_from_env(env={"FLIGHTPOWERS_API_KEY": "x"})
    assert isinstance(f, lp.CompositeFlightProvider)
    f, h, label = lp.build_providers_from_env(env={"RAPIDAPI_KEY": "x", "BOUNCER_USE_MOCK": "1"})
    assert isinstance(f, MockFlightProvider) and "forced" in label


def test_no_real_network(monkeypatch):
    def fail(*a, **k):
        raise AssertionError("real network call attempted")
    monkeypatch.setattr(lp.requests, "post", fail)
    monkeypatch.setattr(lp.requests, "get", fail)
    f, h, _ = lp.build_providers_from_env(env={})
    assert f.search("JFK", "LHR", D)


# ---- fixtures trimmed from real responses (2026-11-04) ----
import json
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def test_flightpowers_real_fixture():
    data = json.loads((FIX / "flightpowers_oneway_jfk_lhr.json").read_text())
    out = lp.parse_flightpowers_flights(data, CabinClass.ECONOMY)
    assert len(out) == 4
    assert out[0].cash_price == 882.0 and out[0].details["airline"] == "American"
    assert out[0].details["airline_raw"].startswith("American | ")
    assert "JFK-LHR" in out[0].description and "nonstop" in out[0].description
    assert out[1].details["airline"] == "British Airways"
    assert out[2].details["stops"] == 1 and out[2].details["stop_airports"] == ["CLT"]
    assert out[3].details["airline"] == "Delta"
    assert all(o.booking_url.startswith("https://www.google.com/travel/flights") for o in out)


def test_booking_live_real_fixture_and_rapidapi_headers():
    data = json.loads((FIX / "booking_live_london.json").read_text())
    s = Stub(Resp(data))
    out = lp.FlightPowersHotelProvider("k", session=s).search("LHR", date(2026, 12, 19), date(2026, 12, 22))
    url, kw = s.calls[0][1], s.calls[0][2]
    assert url == "https://booking-live-api.p.rapidapi.com/search"
    assert kw["headers"]["x-rapidapi-host"] == "booking-live-api.p.rapidapi.com"
    assert kw["json"]["destination"] == "London" and kw["json"]["children"] == 0
    assert [o.cash_price for o in out] == sorted(o.cash_price for o in out)  # cheapest first
    strand = next(o for o in out if o.description.startswith("Strand Palace"))
    assert strand.cash_price == 580.0 and strand.details["nights"] == 3
    assert strand.details["price_per_night"] == 193.33 and strand.details["currency"] == "USD"
    assert strand.details["review_score"] == 8.5 and "booking.com" in strand.booking_url


def test_hotel_direct_fallback_on_error_not_on_429():
    def resp(url, kw):
        return Resp({}, status=500) if "rapidapi" in url else Resp({"properties": [{"name": "X", "price": 10}]})
    s = Stub(resp)
    out = lp.FlightPowersHotelProvider("k", session=s).search("London", D, R)
    assert out[0].cash_price == 10.0 and len(s.calls) == 2
    s2 = Stub(Resp({}, status=429))
    with pytest.raises(lp.ProviderError):
        lp.FlightPowersHotelProvider("k", session=s2).search("London", D, R)
    assert len(s2.calls) == 1


def test_flightpowers_roundtrip_real_fixture():
    data = json.loads((FIX / "flightpowers_roundtrip_jfk_lhr.json").read_text())
    out = lp.parse_flightpowers_flights(data, CabinClass.ECONOMY, roundtrip=True)
    assert [o.cash_price for o in out] == [1426.0, 1687.0, 1358.0]
    assert out[1].description.startswith("British Airways nonstop JFK-LHR")
    assert out[2].description.startswith("Delta 1 stop(s)")
