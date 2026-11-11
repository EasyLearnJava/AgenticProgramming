"""Nuitée's public shared sandbox, using fixed tools and synthetic travelers only.

No caller credential, configurable endpoint, card, visitor details or arbitrary MCP tool is accepted. The official
MCP server supplies its shared sandbox credential when no key is sent. Hotel responses must additionally attest
sandbox mode; flights currently omit that flag. This module never retries a hotel booking mutation after a timeout.
"""

import asyncio
import json
import math
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent

from nimbus.mcp_lane import to_leaves
from nimbus.travel.airports import AIRPORT_ZONES
from nimbus.travel.mcp_client import travel_mcp_active

ENDPOINT = "https://mcp.liteapi.travel/api/mcp"
MAX_BYTES = 20 * 1024 * 1024
TOOLS = frozenset(
    {
        "post_flights_rates",
        "post_flights_verify",
        "post_flights_prebooks",
        "post_flights_bookings",
        "get_flights_bookings_bookingid",
        "post_hotels_rates",
        "post_rates_prebook",
        "post_rates_book",
        "list_bookings",
    }
)
_REASONS = frozenset(
    {"unavailable", "timeout", "rate_limited", "invalid_response", "no_match", "not_found", "duplicate"}
)
_ZION = (37.1889, -112.9986)  # Springdale, outside Zion's south entrance.


class DemoProviderError(Exception):
    """A fixed failure reason; provider bodies and traveler details never escape this boundary."""

    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in _REASONS else "unavailable"
        super().__init__(self.reason)


class _LimitedStream(httpx2.AsyncByteStream):
    """Bound JSON and SSE bytes before the SDK buffers the response."""

    def __init__(self, stream: httpx2.AsyncByteStream) -> None:
        self.stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_BYTES:
                raise DemoProviderError("invalid_response")
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


async def _inspect(response: httpx2.Response) -> None:
    """Refuse redirects, compressed/oversized responses and transport errors."""
    size = response.headers.get("content-length", "")
    if response.status_code == 429:
        raise DemoProviderError("rate_limited")
    if response.is_error or response.is_redirect:
        raise DemoProviderError("unavailable")
    if response.headers.get("content-encoding", "identity").lower() != "identity" or (
        size.isdecimal() and (len(size) > 12 or int(size) > MAX_BYTES)
    ):
        raise DemoProviderError("invalid_response")
    if isinstance(response.stream, httpx2.AsyncByteStream):
        response.stream = _LimitedStream(response.stream)


def _reject_live(value: Any) -> None:
    """An explicit live-environment marker is never ignored, even if nested."""
    if isinstance(value, dict):
        if "sandbox" in value and value["sandbox"] in (False, 0, "false", "0"):
            raise DemoProviderError("invalid_response")
        for item in value.values():
            _reject_live(item)
    elif isinstance(value, list):
        for item in value:
            _reject_live(item)


async def _call(name: str, arguments: dict[str, Any], seconds: float = 35) -> dict[str, Any]:
    """Exactly one call with a deadline; no retries, auth, environment proxy, cookies or remote tool imports."""
    if name not in TOOLS:
        raise DemoProviderError("invalid_response")
    token = travel_mcp_active.set(True)
    try:
        async with (
            asyncio.timeout(seconds),
            httpx2.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=seconds,
                headers={"accept-encoding": "identity"},
                event_hooks={"response": [_inspect]},
            ) as http,
            Client(
                streamable_http_client(ENDPOINT, http_client=http, max_sse_event_size=MAX_BYTES), mode="legacy"
            ) as client,
        ):
            result = await client.call_tool(name, arguments)
            if result.is_error:
                # Inspect only to classify; never forward the body to UI, logs or traces.
                body = " ".join(block.text for block in result.content if isinstance(block, TextContent))
                reason = "duplicate" if '"code":4005' in body.replace(" ", "") else "unavailable"
                raise DemoProviderError(reason)
            payload = result.structured_content
            if payload is None:
                texts = [block.text for block in result.content if isinstance(block, TextContent)]
                payload = json.loads(texts[0]) if len(texts) == 1 else None
            if not isinstance(payload, dict) or payload.get("error"):
                raise DemoProviderError("invalid_response")
            _reject_live(payload)
            return payload
    except Exception as error:
        leaves = to_leaves(error) if isinstance(error, BaseExceptionGroup) else [error]
        known = next((item.reason for item in leaves if isinstance(item, DemoProviderError)), None)
        timed_out = any(isinstance(item, (TimeoutError, httpx2.TimeoutException)) for item in leaves)
        raise DemoProviderError(known or ("timeout" if timed_out else "unavailable")) from None
    finally:
        travel_mcp_active.reset(token)


def _text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise DemoProviderError("invalid_response")
    return value.strip()


def _id(value: Any) -> str:
    text = _text(value, 16000)
    if not re.fullmatch(r"[A-Za-z0-9_.:/+=-]+", text):
        raise DemoProviderError("invalid_response")
    return text


def _money(value: Any, currency: Any) -> str:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise DemoProviderError("invalid_response") from None
    if currency != "USD" or not amount.is_finite() or not 0 < amount < 100000:
        raise DemoProviderError("invalid_response")
    return str(amount.quantize(Decimal("0.01")))


def _first(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("data")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise DemoProviderError("no_match")
    return items[0]


def _dates(checkin: str, checkout: str) -> tuple[date, date]:
    start, end = date.fromisoformat(checkin), date.fromisoformat(checkout)
    if start.weekday() != 4 or (end - start).days != 2:
        raise DemoProviderError("invalid_response")
    return start, end


def _local(value: Any, airport: Any) -> datetime:
    zone = AIRPORT_ZONES.get(airport) if isinstance(airport, str) else None
    if zone is None:
        raise DemoProviderError("invalid_response")
    stamp = datetime.fromisoformat(_text(value, 40))
    if stamp.tzinfo is not None:
        return stamp.astimezone(ZoneInfo(zone))
    local = stamp.replace(tzinfo=ZoneInfo(zone))
    if local.utcoffset() != local.replace(fold=1).utcoffset():
        raise DemoProviderError("invalid_response")
    return local


def _flight_details(journey: dict[str, Any], checkin: str, checkout: str) -> list[str]:
    """Validate every connection and the final local-day/window constraints, not just provider filters."""
    start, end = _dates(checkin, checkout)
    segments = journey.get("segments")
    if not isinstance(segments, list) or not 2 <= len(segments) <= 6:
        raise DemoProviderError("invalid_response")
    details = []
    prior_arrival: datetime | None = None
    for direction, origin, destination, day in (("OUTBOUND", "DFW", "LAX", start), ("INBOUND", "LAX", "DFW", end)):
        leg = [s for s in segments if isinstance(s, dict) and s.get("direction") == direction]
        if not leg or leg[0].get("originCode") != origin or leg[-1].get("destinationCode") != destination:
            raise DemoProviderError("no_match")
        for i, segment in enumerate(leg):
            depart = _local(segment.get("departureTime"), segment.get("originCode"))
            arrive = _local(segment.get("arrivalTime"), segment.get("destinationCode"))
            if arrive.astimezone(UTC) <= depart.astimezone(UTC) or (
                prior_arrival is not None and depart.astimezone(UTC) <= prior_arrival.astimezone(UTC)
            ):
                raise DemoProviderError("no_match")
            if i and leg[i - 1].get("destinationCode") != segment.get("originCode"):
                raise DemoProviderError("no_match")
            prior_arrival = arrive
        first = _local(leg[0].get("departureTime"), origin)
        last = _local(leg[-1].get("arrivalTime"), destination)
        if first.date() != day or last.date() != day or first.astimezone(UTC) <= datetime.now(UTC):
            raise DemoProviderError("no_match")
        if direction == "INBOUND" and last.hour < 12:
            raise DemoProviderError("no_match")
        details.append(
            f"{origin} → {destination} · {first:%a %b %d, %H:%M} to {last:%H:%M} local · {len(leg) - 1} connection(s)"
        )
    if any(not isinstance(s, dict) or s.get("direction") not in {"OUTBOUND", "INBOUND"} for s in segments):
        raise DemoProviderError("invalid_response")
    return details


async def search_flight(checkin: str, checkout: str) -> dict[str, Any]:
    """Find only the requested DFW-LAX weekend; never silently substitute a gateway or Monday arrival."""
    _dates(checkin, checkout)
    payload = await _call(
        "post_flights_rates",
        {
            "legs": [
                {"origin": "DFW", "destination": "LAX", "date": checkin, "direction": "OUTBOUND"},
                {
                    "origin": "LAX",
                    "destination": "DFW",
                    "date": checkout,
                    "direction": "INBOUND",
                    "filters": {"arrivalTimeAfter": "12:00", "arrivalTimeBefore": "23:59", "excludeOvernight": True},
                },
            ],
            "adults": 1,
            "children": 0,
            "infants": 0,
            "currency": "USD",
            "country": "US",
            "cabinClass": "ECONOMY",
            "filters": {"showCheapestOfferOnly": True, "maxStops": 1, "excludeOvernight": True},
            "sort": {"sortBy": "price", "sortOrder": "asc"},
        },
        50,
    )
    candidates = []
    for journey in _first(payload).get("journeys", []):
        try:
            details = _flight_details(journey, checkin, checkout)
            if journey.get("parameters") != {"adults": 1, "children": 0, "infants": 0}:
                continue
            offer = journey["cheapestOffer"]
            pricing = offer["pricing"]["display"]
            candidates.append(
                {
                    "offer_id": _id(offer["offerId"]),
                    "title": "DFW ↔ LAX · round trip",
                    "details": details,
                    "price": _money(pricing["total"], pricing["currency"]),
                    "currency": "USD",
                    "checkin": checkin,
                    "checkout": checkout,
                }
            )
        except (DemoProviderError, KeyError, TypeError, ValueError):
            continue
    if not candidates:
        raise DemoProviderError("no_match")
    candidates.sort(key=lambda candidate: Decimal(str(candidate["price"])))
    return {**candidates[0], "alternatives": candidates[1:3]}


async def verify_flight(offer: dict[str, Any], checkin: str, checkout: str) -> dict[str, Any]:
    """Verify at most three candidates before prebooking; a failed supplier can yield to another valid offer."""
    choices = [{k: v for k, v in offer.items() if k != "alternatives"}, *offer.get("alternatives", [])][:3]
    for candidate in choices:
        try:
            payload = await _call("post_flights_verify", {"offerId": _id(candidate["offer_id"])}, 25)
            journey = _first(payload)["journey"]
            if journey.get("passengers") != {"adults": 1, "children": 0, "infants": 0}:
                raise DemoProviderError("no_match")
            details = _flight_details(journey, checkin, checkout)
            pricing = journey["pricing"]["display"]
            return {**candidate, "details": details, "price": _money(pricing["total"], pricing["currency"])}
        except (DemoProviderError, KeyError, TypeError, ValueError):
            continue
    raise DemoProviderError("unavailable")


async def prebook_flight(offer: dict[str, Any]) -> dict[str, Any]:
    """Only fabricated demonstration identity; no visitor-provided name, contact or document is accepted."""
    payload = await _call(
        "post_flights_prebooks",
        {
            "offerId": _id(offer["offer_id"]),
            "travelPurpose": "LEISURE",
            "contact": {
                "firstName": "Avery",
                "lastName": "Linton",
                "email": "nimbus-demo@example.com",
                "phoneCountryCode": "1",
                "phoneNumber": "2025550123",
            },
            "passengers": [
                {
                    "firstName": "Avery",
                    "lastName": "Linton",
                    "birthday": "1990-01-15",
                    "gender": "M",
                    "nationality": "US",
                    "passengerType": 0,
                }
            ],
        },
        45,
    )
    data = _first(payload)
    if "ACC_CREDIT_CARD" not in data.get("paymentTypes", []):
        raise DemoProviderError("invalid_response")
    details = _flight_details(data["booking"]["journey"], offer["checkin"], offer["checkout"])
    return {
        "prebook_id": _id(data["prebookId"]),
        "details": details,
        "price": _money(data["price"], data["currency"]),
        "currency": "USD",
    }


def _booking(data: dict[str, Any], *, flight: bool) -> dict[str, Any]:
    raw = data.get("status", "UNKNOWN")
    statuses = {
        "CONFIRMED": "confirmed",
        "TICKETED": "confirmed",
        "PENDING_CONFIRMATION": "pending",
        "PENDING": "pending",
        "PROCESSING": "pending",
        "CANCELLED": "failed",
        "CANCELED": "failed",
        "FAILED": "failed",
        "REJECTED": "failed",
    }
    result = {
        "status": statuses.get(raw, "unknown"),
        "provider_status": raw if raw in statuses else "UNKNOWN",
        "booking_id": _id(data["bookingId"]),
        "reference": _text(data.get("bookingRef") or data["bookingId"], 100),
    }
    pricing = data.get("pricing", {}) if flight else data
    value = pricing.get("totalAmount") if flight else pricing.get("price")
    if value is not None:
        result.update(price=_money(value, pricing.get("currency")), currency="USD")
    return result


async def book_flight(prebook_id: str) -> dict[str, Any]:
    """Simulated payment only; the provider deduplicates by this prebook ID."""
    payload = await _call(
        "post_flights_bookings",
        {
            "prebookId": _id(prebook_id),
            "payment": {"method": "ACC_CREDIT_CARD"},
            "customTags": {"PURPOSE": "NIMBUS_SANDBOX_DEMO"},
        },
        75,
    )
    return _booking(_first(payload)["booking"], flight=True)


async def retrieve_flight(booking_id: str) -> dict[str, Any]:
    """Read one known booking; never enumerate the shared sandbox account."""
    payload = await _call("get_flights_bookings_bookingid", {"bookingId": _id(booking_id)})
    data = _first(payload)["booking"]
    if data.get("bookingId") != booking_id:
        raise DemoProviderError("invalid_response")
    return _booking(data, flight=True)


async def recover_flight(prebook_id: str) -> dict[str, Any]:
    """Explicit recovery only: the flight provider returns the existing booking for this same prebook ID.

    Unlike hotels, the documented flight booking endpoint is idempotent by prebook ID. This never creates a new
    prebook or changes traveler/offer details; a still-processing duplicate may return an unavailable status.
    """
    return await book_flight(prebook_id)


def _near_zion(hotel: dict[str, Any]) -> bool:
    try:
        lat, lon = float(hotel["latitude"]), float(hotel["longitude"])
        phi, base = math.radians(lat), math.radians(_ZION[0])
        a = (
            math.sin((phi - base) / 2) ** 2
            + math.cos(phi) * math.cos(base) * math.sin(math.radians(lon - _ZION[1]) / 2) ** 2
        )
        distance = 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))
        return math.isfinite(lat) and math.isfinite(lon) and distance <= 10000 and hotel.get("country_code") == "US"
    except (KeyError, TypeError, ValueError):
        return False


async def search_hotel(checkin: str, checkout: str) -> dict[str, Any]:
    """One room for one synthetic adult, within ten kilometres of Springdale, Utah."""
    _dates(checkin, checkout)
    payload = await _call(
        "post_hotels_rates",
        {
            "occupancies": [{"adults": 1}],
            "currency": "USD",
            "guestNationality": "US",
            "checkin": checkin,
            "checkout": checkout,
            "latitude": _ZION[0],
            "longitude": _ZION[1],
            "radius": 10000,
            "limit": 8,
            "maxRatesPerHotel": 1,
            "includeHotelData": True,
            "timeout": 10,
            "sort": [{"field": "price", "direction": "ascending"}],
        },
    )
    if payload.get("sandbox") is not True:
        raise DemoProviderError("invalid_response")
    hotels = {h["id"]: h for h in payload.get("hotels", []) if isinstance(h, dict) and "id" in h and _near_zion(h)}
    candidates = []
    for rates in payload.get("data", []):
        try:
            hotel = hotels[rates["hotelId"]]
            rate = rates["roomTypes"][0]
            price = rate["offerRetailRate"]
            candidates.append(
                {
                    "offer_id": _id(rate["offerId"]),
                    "hotel_id": _id(hotel["id"]),
                    "title": _text(hotel["name"]),
                    "details": [_text(hotel["address"]), "Near Zion · Springdale area · 1 adult · 1 room · 2 nights"],
                    "price": _money(price["amount"], price["currency"]),
                    "currency": "USD",
                    "checkin": checkin,
                    "checkout": checkout,
                }
            )
        except (DemoProviderError, KeyError, IndexError, TypeError, ValueError):
            continue
    if not candidates:
        raise DemoProviderError("no_match")
    return min(candidates, key=lambda candidate: Decimal(candidate["price"]))


async def prebook_hotel(offer: dict[str, Any]) -> dict[str, Any]:
    payload = await _call(
        "post_rates_prebook", {"offerId": _id(offer["offer_id"]), "usePaymentSdk": False, "timeout": 20}
    )
    data = payload.get("data", {})
    if (
        payload.get("sandbox") is not True
        or data.get("hotelId") != offer["hotel_id"]
        or (data.get("checkin") != offer["checkin"] or data.get("checkout") != offer["checkout"])
        or "ACC_CREDIT_CARD" not in data.get("paymentTypes", [])
    ):
        raise DemoProviderError("invalid_response")
    return {"prebook_id": _id(data["prebookId"]), "price": _money(data["price"], data["currency"]), "currency": "USD"}


async def book_hotel(prebook_id: str, client_reference: str) -> dict[str, Any]:
    """One mutation only. On timeout, callers must use recover_hotel with the same saved reference."""
    payload = await _call(
        "post_rates_book",
        {
            "prebookId": _id(prebook_id),
            "clientReference": _text(client_reference, 100),
            "timeout": 60,
            "holder": {
                "firstName": "Avery",
                "lastName": "Linton",
                "email": "nimbus-demo@example.com",
                "phone": "+12025550123",
            },
            "guests": [
                {"occupancyNumber": 1, "firstName": "Avery", "lastName": "Linton", "email": "nimbus-demo@example.com"}
            ],
            "payment": {"method": "ACC_CREDIT_CARD"},
            "customTags": {"PURPOSE": "NIMBUS_SANDBOX_DEMO"},
        },
        75,
    )
    if payload.get("sandbox") is not True:
        raise DemoProviderError("invalid_response")
    data = payload.get("data", {})
    if data.get("clientReference") != client_reference:
        raise DemoProviderError("invalid_response")
    return _booking(data, flight=False)


async def recover_hotel(client_reference: str) -> dict[str, Any]:
    """Recover a timed-out book by exact opaque reference; never list unrelated bookings or book again."""
    payload = await _call("list_bookings", {"clientReference": _text(client_reference, 100), "timeout": 10})
    items = payload.get("data", [])
    rows = [item for item in items if isinstance(item, dict) and item.get("clientReference") == client_reference]
    if not rows:
        raise DemoProviderError("not_found")
    if len(rows) != 1 or rows[0].get("sandbox") not in (True, 1):
        raise DemoProviderError("invalid_response")
    return _booking(rows[0], flight=False)
