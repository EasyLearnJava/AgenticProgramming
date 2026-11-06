"""A weekend quote must fit both ends of the trip in the origin airport's clock."""

import copy
from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nimbus.travel.kiwi import to_flight_arguments, to_flight_report
from nimbus.travel.mcp_client import TravelProviderError
from nimbus.travel.models import FlightSearch, FlightWindow, HotelSearch, TravelReport
from nimbus.travel.service import TravelService
from tests.unit.test_planner import _enable, _fields
from tests.unit.test_travel_providers import fixture

CHECKED = datetime(2026, 11, 5, 18, tzinfo=UTC)
WEEKEND = FlightSearch(
    origin="DFW",
    destination="LAS",
    departure_date=date(2026, 11, 6),
    return_date=date(2026, 11, 8),
    adults=2,
    depart_window="evening",
    return_window="evening",
)


def flights(depart: str, back: str) -> dict[str, Any]:
    payload = fixture("kiwi")
    offer = payload["itineraries"][0]
    offer["outbound"].update({"from": "DFW", "departureTime": depart, "arrivalTime": "2026-11-06T21:00:00"})
    offer["inbound"] = {
        "from": "LAS",
        "to": "DFW",
        "departureTime": "2026-11-08T15:00:00",
        "arrivalTime": back,
        "stops": 0,
    }
    return payload


@pytest.mark.parametrize(
    ("depart", "back", "window", "matches"),
    [
        ("2026-11-06T18:00:00", "2026-11-08T23:59:00", "evening", True),
        ("2026-11-06T17:59:00", "2026-11-08T20:00:00", "evening", False),
        ("2026-11-06T19:00:00", "2026-11-08T17:59:00", "evening", False),
        ("2026-11-06T19:00:00", "2026-11-09T00:01:00", "evening", False),
        ("2026-11-06T19:00:00", "2026-11-08T12:00:00", "by_noon", True),
        ("2026-11-06T19:00:00", "2026-11-08T12:01:00", "by_noon", False),
        ("2026-11-06T19:00:00", "2026-11-08T09:30:00", "morning", True),
        ("2026-11-06T19:00:00", "2026-11-08T12:00:00", "morning", False),
        ("2026-11-07T01:30:00Z", "2026-11-09T01:30:00Z", "evening", True),
    ],
)
def test_only_verified_local_windows_reach_cards(depart: str, back: str, window: FlightWindow, matches: bool) -> None:
    query = WEEKEND.model_copy(update={"return_window": window})
    payload = flights(depart, back)
    if window in {"by_noon", "morning"}:
        payload["itineraries"][0]["inbound"]["departureTime"] = "2026-11-08T00:01:00"
    result = to_flight_report(payload, query, now=CHECKED)
    assert result.status == ("found" if matches else "no_results")
    assert result.empty_reason == (None if matches else "time_window")
    assert bool(result.offers) == matches
    if matches:
        assert "LAS → DFW" in result.offers[0].details[1]
    assert "return_window" not in to_flight_arguments(query)


def test_time_mismatch_searches_past_ineligible_results_without_hiding_bad_data() -> None:
    payload = flights("2026-11-06T18:01:00", "2026-11-09T01:00:00")
    rows = payload["itineraries"]
    rows.extend(copy.deepcopy(rows[0]) for _ in range(5))
    match = copy.deepcopy(rows[0])
    match["inbound"]["arrivalTime"] = "2026-11-08T20:00:00"
    match["bookingUrl"] = "https://www.kiwi.com/valid"
    rows.append(match)
    report = to_flight_report(payload, WEEKEND, now=CHECKED)
    assert report.status == "found"
    assert [offer.url for offer in report.offers] == [match["bookingUrl"]]
    rows[-1] = {"price": "bad"}
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_flight_report(payload, WEEKEND, now=CHECKED)


@pytest.mark.parametrize(
    ("outbound_arrival", "valid"),
    [
        ("2026-11-08T22:59:00Z", True),  # 14:59 in Las Vegas, before its 15:00 departure.
        ("2026-11-08T23:00:00Z", False),
        ("2026-11-10T18:00:00", False),
    ],
)
def test_return_must_follow_outbound_arrival(outbound_arrival: str, valid: bool) -> None:
    payload = flights("2026-11-06T18:01:00", "2026-11-08T20:00:00")
    payload["itineraries"][0]["outbound"]["arrivalTime"] = outbound_arrival
    if valid:
        assert to_flight_report(payload, WEEKEND, now=CHECKED).status == "found"
    else:
        with pytest.raises(TravelProviderError, match="invalid_response"):
            to_flight_report(payload, WEEKEND, now=CHECKED)


def test_elapsed_departures_and_empty_inventory_are_distinct_from_date_only_searches() -> None:
    payload = flights("2026-11-06T18:01:00", "2026-11-08T20:00:00")
    checked = datetime(2026, 11, 7, 0, 2, tzinfo=UTC)  # 18:02 in Dallas on Friday.
    assert to_flight_report(payload, WEEKEND, now=checked).empty_reason == "time_window"
    payload["itineraries"][0]["inbound"]["arrivalTime"] = "2026-11-09T01:00:00"
    unrestricted = WEEKEND.model_copy(update={"depart_window": "", "return_window": ""})
    assert to_flight_report(payload, unrestricted, now=CHECKED).status == "found"
    payload.update(itineraries=[], resultsCount=0)
    report = to_flight_report(payload, WEEKEND, now=CHECKED)
    assert (report.status, report.empty_reason) == ("no_results", None)


@pytest.mark.parametrize(("origin", "utc_hour"), [("MSP", 0), ("SAN", 2), ("PDX", 2), ("MCO", 23), ("PHL", 23)])
def test_same_day_departure_uses_the_origin_airport_clock(origin: str, utc_hour: int) -> None:
    day = 6 if utc_hour == 23 else 7
    checked = datetime(2026, 11, day, utc_hour, 29, tzinfo=UTC)
    payload = flights("2026-11-06T18:30:00", "2026-11-08T21:00:00")
    row = payload["itineraries"][0]
    row["outbound"]["from"] = row["inbound"]["to"] = origin
    query = WEEKEND.model_copy(update={"origin": origin})
    assert to_flight_report(payload, query, now=checked).status == "found"
    assert to_flight_report(payload, query, now=checked.replace(minute=30)).empty_reason == "time_window"


def test_kiwi_receives_departure_hours_and_overnight_return_range_and_cards_meet_exact_deadline() -> None:
    query = FlightSearch.model_validate({**WEEKEND.model_dump(), "return_window": "by_15:15"})
    args = to_flight_arguments(query)
    assert (args["returnDate"], args["returnDateTo"]) == ("07/11/2026", "08/11/2026")
    assert (args["dtime_from"], args["dtime_to"], args["ret_atime_from"], args["ret_atime_to"]) == (18, 23, 0, 15)
    payload = flights("2026-11-06T18:30:00", "2026-11-08T15:15:00")
    leg = payload["itineraries"][0]["inbound"]
    leg["departureTime"] = "2026-11-07T21:00:00"
    report = to_flight_report(payload, query, now=CHECKED)
    assert report.status == "found"
    assert "Nov 07 21:00 to Nov 08 15:15" in report.offers[0].details[1]
    leg["arrivalTime"] = "2026-11-08T15:16:00"
    assert to_flight_report(payload, query, now=CHECKED).empty_reason == "time_window"
    leg.update(departureTime="2026-11-07T12:00:00", arrivalTime="2026-11-07T18:00:00")
    assert to_flight_report(payload, query, now=CHECKED).empty_reason == "time_window"


def test_unknown_and_ambiguous_departure_offsets_cannot_verify_the_window() -> None:
    payload = flights("2026-11-01T01:30:00", "2026-11-08T20:00:00")  # Dallas repeats 01:30.
    query = WEEKEND.model_copy(update={"departure_date": date(2026, 11, 1), "depart_window": ""})
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_flight_report(payload, query, now=datetime(2026, 10, 31, tzinfo=UTC))
    payload["itineraries"][0]["outbound"]["departureTime"] = "2026-11-01T01:30:00-06:00"
    assert to_flight_report(payload, query, now=datetime(2026, 10, 31, tzinfo=UTC)).status == "found"


def test_any_time_still_excludes_elapsed_departures_and_keeps_verifiable_future_dates() -> None:
    query = WEEKEND.model_copy(update={"depart_window": "", "return_window": ""})
    payload = flights("2026-11-06T18:30:00", "2026-11-08T20:00:00")
    now = datetime(2026, 11, 7, 0, 45, tzinfo=UTC)  # 18:45 in Dallas.
    assert to_flight_report(payload, query, now=now).status == "no_results"
    row = payload["itineraries"][0]
    row["outbound"]["from"] = row["inbound"]["to"] = "QQQ"  # No known zone for a naive stamp.
    unknown = query.model_copy(update={"origin": "QQQ"})
    assert to_flight_report(payload, unknown, now=datetime(2026, 11, 3, tzinfo=UTC)).status == "found"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_flight_report(payload, unknown, now=now)


def test_return_window_needs_a_return_date() -> None:
    with pytest.raises(ValidationError, match="return date"):
        FlightSearch.model_validate({**WEEKEND.model_dump(), "return_date": None})


def test_unverifiable_local_time_cannot_qualify_a_flight() -> None:
    payload = flights("2026-11-06T18:00:00Z", "2026-11-08T20:00:00")
    row = payload["itineraries"][0]
    row["outbound"]["from"] = row["inbound"]["to"] = "QQQ"  # No known airport clock.
    query = WEEKEND.model_copy(update={"origin": "QQQ"})
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_flight_report(payload, query, now=CHECKED)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"skip_flights": "true", "skip_hotels": "true", "origin": "", "gateway": ""}, []),
        ({"skip_flights": "true", "transport": "skip"}, ["hotel"]),
        ({"skip_hotels": "true"}, ["flight"]),
    ],
)
def test_specifically_declined_providers_receive_no_calls_even_on_repeat_submit(
    client: TestClient, flags: dict[str, str], expected: list[str]
) -> None:
    app = _enable(client)
    calls: list[str] = []

    async def flight(query: FlightSearch) -> TravelReport:
        calls.append("flight")
        assert (query.depart_window, query.return_window) == ("evening", "by_noon")
        return TravelReport(provider="kiwi", status="no_results", empty_reason="time_window")

    async def hotel(_query: HotelSearch) -> TravelReport:
        calls.append("hotel")
        return TravelReport(provider="trivago", status="no_results")

    app.state.travel_service = TravelService(flights=flight, hotels=hotel)
    fields = {**_fields(), "depart_window": "evening", "return_window": "by_noon", **flags}
    for _ in range(2):
        response = client.post("/api/parks/trip", data=fields)
        assert response.status_code == 200
        if "flight" in expected:
            assert "None of the returned flights met your time preferences" in response.text
        assert calls == expected
        calls.clear()
