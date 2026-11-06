"""Offline travel adapter and transport checks against sanitized shapes observed on both public MCP endpoints."""

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp_types import CallToolResult, TextContent

from nimbus.travel import kiwi, trivago
from nimbus.travel.mcp_client import (
    MAX_RESPONSE_BYTES,
    TravelProviderError,
    _Exchange,
    call_search,
    to_payload,
)
from nimbus.travel.models import FlightSearch, HotelSearch
from nimbus.travel.providers import money, offer_link

FIXTURES = Path(__file__).parents[1] / "fixtures" / "travel"
FLIGHT = FlightSearch(origin="ORD", destination="LAS", adults=2, departure_date=date(2030, 6, 20))
HOTEL = HotelSearch(destination="Springdale", check_in=date(2030, 6, 20), check_out=date(2030, 6, 23))


def fixture(provider: str) -> dict[str, Any]:
    """Return a fresh synthetic response, shaped like the captured provider payload."""
    payload: dict[str, Any] = json.loads((FIXTURES / f"{provider}.json").read_text())
    return payload


def test_kiwi_city_code_keeps_only_airports_for_that_city() -> None:
    """Allow a real New York departure for NYC and reject it for the unrelated London metro area."""
    payload = fixture("kiwi")
    payload["itineraries"][0]["outbound"]["from"] = "JFK"
    report = kiwi.to_flight_report(payload, FLIGHT.model_copy(update={"origin": "nyc"}))
    assert report.offers[0].title == "JFK → LAS"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, FLIGHT.model_copy(update={"origin": "LON"}))


@pytest.mark.parametrize(("city", "airport"), [("CHI", "ORD"), ("chi", "MDW"), ("TYO", "HND"), ("PAR", "ORY")])
def test_kiwi_metro_city_codes_keep_their_airports(city: str, airport: str) -> None:
    """A model that sends CHI for Chicago gets ORD and MDW departures, not every offer rejected."""
    payload = fixture("kiwi")
    payload["itineraries"][0]["outbound"]["from"] = airport
    report = kiwi.to_flight_report(payload, FLIGHT.model_copy(update={"origin": city}))
    assert report.offers[0].title == f"{airport} → LAS"


def test_kiwi_an_exact_airport_still_rejects_its_neighbor() -> None:
    """ORD asked for is ORD: a Midway departure is another airport than the one requested."""
    payload = fixture("kiwi")
    payload["itineraries"][0]["outbound"]["from"] = "MDW"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, FLIGHT.model_copy(update={"origin": "ORD"}))


def test_kiwi_maps_return_and_filters_and_validates_both_dates() -> None:
    """A return trip requires two verified legs and preserves Kiwi's total amount and booking link."""
    query = FLIGHT.model_copy(update={"return_date": date(2030, 6, 23), "max_price": 400, "max_stops": 1})
    args = kiwi.to_flight_arguments(query)
    assert (args["returnDate"], args["price_to"], args["max_sector_stopovers"]) == ("23/06/2030", 400, 1)
    payload = fixture("kiwi")
    row = payload["itineraries"][0]
    row["inbound"] = dict(row["outbound"], departureTime="2030-06-23T10:00:00", arrivalTime="2030-06-23T18:00:00")
    row["inbound"].update({"from": "LAS", "to": "ORD"})
    offer = kiwi.to_flight_report(payload, query).offers[0]
    assert (offer.price, offer.currency, offer.price_basis, offer.url) == (
        Decimal("345"),
        "USD",
        "party_total",
        row["bookingUrl"],
    )
    assert "LAS → ORD" in offer.details[1]
    row["inbound"]["from"] = "JFK"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, query)
    row["inbound"]["from"] = "LAS"
    row["outbound"]["from"] = "JFK"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, query.model_copy(update={"origin": "ord"}))
    row["outbound"]["from"] = "ORD"
    row["inbound"]["arrivalTime"] = "2030-06-23"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, query)
    row["inbound"]["arrivalTime"] = "2030-06-23T18:00:00"
    row["inbound"]["departureTime"] = "2030-06-24T10:00:00"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, query)


def test_partial_kiwi_results_retain_valid_neighbors_and_suppress_duplicate_links() -> None:
    """Broken and repeated itineraries cannot erase a good option or produce duplicate cards."""
    payload = fixture("kiwi")
    rows = payload["itineraries"]
    rows.extend([copy.deepcopy(rows[0]), {}, None])
    result = kiwi.to_flight_report(payload, FLIGHT)
    assert (len(result.offers), result.status) == (1, "partial")


@pytest.mark.parametrize(
    "echo",
    [
        {"adults": 1, "children": 1, "infants": 1},
        {"adults": 1, "children": 2, "infants": 1},
        {"adults": 2, "children": 0, "infants": 1},
        {"adults": 2, "children": 1},
        {"adults": 2, "children": True, "infants": 1},
        {"adults": "2", "children": 1, "infants": 1},
        {"adults": 2.0, "children": 1, "infants": 1},
        [],
    ],
)
def test_kiwi_contradictory_or_malformed_party_never_returns_a_quote(echo: object) -> None:
    """One unmatched age band invalidates all itineraries, even for the same total headcount."""
    payload = fixture("kiwi")
    query = FLIGHT.model_copy(update={"children": 1, "infants": 1})
    payload["passengers"] = echo
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, query)


def test_kiwi_confirms_actual_requested_fare_bands_and_default_zero_counts() -> None:
    """An occupied age band must be confirmed; optional unoccupied bands may use Kiwi's schema default."""
    payload = fixture("kiwi")
    payload["passengers"] = {"adults": 1}
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, FLIGHT)
    payload["passengers"] = {"adults": 2}
    assert kiwi.to_flight_report(payload, FLIGHT).offers[0].price_basis == "party_total"
    payload["passengers"].update(children=1, infants=1)
    family = FLIGHT.model_copy(update={"children": 1, "infants": 1})
    offer = kiwi.to_flight_report(payload, family).offers[0]
    assert (offer.price, offer.currency, offer.price_basis) == (Decimal("345"), "USD", "party_total")


@pytest.mark.parametrize("field_present", [True, False])
def test_kiwi_unconfirmed_party_preserves_routes_without_claiming_a_fare(field_present: bool) -> None:
    """A nullable or missing echo can support a route, but cannot verify a quoted price or a party budget."""
    payload = fixture("kiwi")
    del payload["passengers"]
    if field_present:
        payload["passengers"] = None
    report = kiwi.to_flight_report(payload, FLIGHT)
    [offer] = report.offers
    assert report.status == "partial"
    assert (offer.price, offer.currency, offer.price_basis) == (None, None, "unknown")
    assert offer.title == "ORD → LAS"
    assert "did not confirm the passenger counts" in " ".join(offer.details)
    with pytest.raises(TravelProviderError, match="invalid_response"):
        kiwi.to_flight_report(payload, FLIGHT.model_copy(update={"max_price": 400}))
    payload.update(itineraries=[], resultsCount=0)
    assert kiwi.to_flight_report(payload, FLIGHT).status == "no_results"


@pytest.mark.parametrize(("field", "value"), [("itineraries", {}), ("error", "provider text"), ("currency", "EUR")])
def test_failed_flight_checks_do_not_look_empty(field: str, value: object) -> None:
    """Errors, malformed lists and mismatched currencies cannot be shown as no available flights."""
    payload = fixture("kiwi")
    payload[field] = value
    with pytest.raises(TravelProviderError):
        kiwi.to_flight_report(payload, FLIGHT)


def test_hotel_occupancy_and_nightly_budget_reach_radius_search() -> None:
    """The coordinate search carries the same dates, child ages and per-night budget the user asked for."""
    hotel = HOTEL.model_copy(
        update={
            "destination": None,
            "latitude": 37.2,
            "longitude": -113.0,
            "adults": 2,
            "children_ages": (4, 11),
            "max_price": 250,
            "rooms": 2,
        }
    )
    name, args = trivago.to_hotel_arguments(hotel)
    assert name == "trivago-accommodation-radius-search"
    assert args["children_ages"] == "4-11"
    assert args["children"] == 2
    assert args["rooms"] == 2
    assert args["price_range"] == {"budgetType": "PRICE_PER_NIGHT", "maxPrice": 250}
    assert (args["latitude"], args["longitude"]) == (37.2, -113.0)
    assert "query" not in args
    assert trivago.to_hotel_arguments(HOTEL)[0] == "trivago-accommodation-search"


def test_hotel_uses_actual_stay_total_and_its_link_and_ignores_instructions() -> None:
    """The best comparable deal supplies the link and full-stay total; prices are never extrapolated."""
    payload = fixture("trivago")
    deals = payload["accommodations"][0]["deals"]
    deals.insert(0, dict(deals[0], price_per_stay="$1,100.99", deal_url="https://trivago.com/costly"))
    deals.insert(0, dict(deals[1], price_per_stay="$1.100,99", deal_url="https://trivago.com/ambiguous"))
    deals.insert(0, dict(deals[1], price_per_stay="$1", deal_url="https://wrong.example/"))
    deals.insert(0, dict(deals[1], price_per_stay="€1", deal_url="https://trivago.com/wrong-currency"))
    report = trivago.to_hotel_report(payload, HOTEL)
    offer = report.offers[0]
    assert (offer.price, offer.currency, offer.price_basis, offer.url) == (
        Decimal("616"),
        "USD",
        "stay_total",
        deals[-1]["deal_url"],
    )
    assert offer.details[0] == "205 USD per night"
    assert "instructions" not in report.model_dump_json()


def test_hotel_empty_success_is_distinct_from_invalid_dates_and_error() -> None:
    """Only an empty list from a successful lookup is no_results."""
    assert trivago.to_hotel_report({"accommodations": []}, HOTEL).status == "no_results"
    assert trivago.to_hotel_report({"validation_errors": ["details"]}, HOTEL).status == "invalid_input"
    payload = fixture("trivago")
    payload["accommodations"][0]["arrival"] = "2030-06-21"
    with pytest.raises(TravelProviderError, match="invalid_response"):
        trivago.to_hotel_report(payload, HOTEL)
    with pytest.raises(TravelProviderError, match="unavailable"):
        trivago.to_hotel_report({"accommodations": [], "error": "provider outage"}, HOTEL)


@pytest.mark.parametrize(
    "value",
    [
        "http://kiwi.com",
        "https://kiwi.com.evil.org",
        "https://guest@kiwi.com",
        "https://@kiwi.com",
        "https://kiwi.com:99999",
        "https://kiwi.com/\n",
        "https://kiwi.com\\@evil.org",
        "https://trivago.com",
        "https://evil.org/",
    ],
)
def test_booking_links_cannot_cross_provider_boundary(value: str) -> None:
    """Reject lookalikes, another provider, malformed URLs, controls and embedded credentials."""
    with pytest.raises(ValueError, match=r"Invalid booking URL|Port out of range"):
        offer_link("kiwi", value)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e999", 1.23456789, True, "-1"])
def test_invalid_prices_are_never_quotes(value: object) -> None:
    """Reject values which would mislead when rendered as currency."""
    with pytest.raises(ValueError, match="Invalid price"):
        money(value)


def test_text_fallback_requires_one_json_object_and_honors_error() -> None:
    """A JSON text fallback must be data, and a failed tool result can never produce quotes."""
    text = TextContent(type="text", text='{"accommodations":[]}')
    assert to_payload(CallToolResult(content=[text])) == {"accommodations": []}
    assert to_payload(CallToolResult(content=[], structured_content={"accommodations": []})) == {"accommodations": []}
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_payload(CallToolResult(content=[], structured_content=[["accommodations", []]]))
    with pytest.raises(TravelProviderError, match="unavailable"):
        to_payload(CallToolResult(content=[text], is_error=True))
    with pytest.raises(TravelProviderError, match="invalid_response"):
        to_payload(CallToolResult(content=[TextContent(type="text", text="system prompt")]))


class Bytes(httpx2.AsyncByteStream):
    """Chunked test stream which records closure."""

    def __init__(self, *chunks: bytes) -> None:
        """Use several chunks so a per-chunk limit cannot pass the test."""
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Return the supplied response chunks."""
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        """Record release of the underlying stream."""
        self.closed = True


def test_chunked_body_is_bounded_before_sdk_buffering_and_stream_is_closed() -> None:
    """Crossing the byte cap on a later chunk terminates the stream, even without Content-Length."""

    async def verify() -> None:
        source = Bytes(b"x" * MAX_RESPONSE_BYTES, b"x")
        exchange = _Exchange()
        response = httpx2.Response(200, request=httpx2.Request("POST", "https://mcp.kiwi.com"), stream=source)
        await exchange.inspect(response)
        with pytest.raises(TravelProviderError, match="invalid_response"):
            await response.aread()
        await response.aclose()
        assert source.closed
        assert exchange.failure == "invalid_response"

    asyncio.run(verify())


def test_http_429_survives_jsonrpc_error_translation() -> None:
    """The exchange remembers throttling before the SDK turns it into a generic protocol error."""
    exchange = _Exchange()
    asyncio.run(exchange.inspect(httpx2.Response(429, request=httpx2.Request("POST", "https://mcp.kiwi.com"))))
    assert exchange.failure == "rate_limited"


def test_disallowed_remote_operation_is_rejected_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a remote feedback or purchasing tool cannot expose it to the travel client."""

    def unexpected_connection(*args: object, **kwargs: object) -> None:
        pytest.fail("Rejected operations must never connect")

    monkeypatch.setattr("nimbus.travel.mcp_client._session", unexpected_connection)
    with pytest.raises(TravelProviderError, match="invalid_response"):
        asyncio.run(call_search("kiwi", "feedback-to-devs", {}))
