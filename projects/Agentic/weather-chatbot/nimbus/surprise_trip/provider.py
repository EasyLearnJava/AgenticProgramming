"""Nuitée-only sandbox quotes for DFW to Flagstaff (FLG) and the Grand Canyon South Rim.

The existing sandbox transport is reused, never its fixed Zion itinerary. Quotes cover every adult and every hotel
room for the whole stay, including disclosed mandatory pay-at-property fees. No real traveler data is accepted.
"""

import asyncio
import json
import math
from datetime import UTC, date, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import TextContent

from nimbus.booking_demo import provider as nuitee
from nimbus.mcp_lane import to_leaves
from nimbus.travel.mcp_client import travel_mcp_active

DemoProviderError = nuitee.DemoProviderError
_CANYON = (35.9736, -112.1266)  # Tusayan, beside Grand Canyon's South Rim entrance.
_READ_TOOLS = frozenset({"get_flight_prebook", "get_prebooks_prebookid"})
_NAMES = (
    ("Avery", "Linton"),
    ("Morgan", "Bennett"),
    ("Riley", "Mercer"),
    ("Jordan", "Hayes"),
    ("Casey", "Rowan"),
    ("Taylor", "Ellis"),
)


def occupancies(adults: int) -> list[dict[str, int]]:
    """Allocate at most two adults per room, with an explicit final single room when needed."""
    if type(adults) is not int or not 1 <= adults <= 6:
        raise DemoProviderError("invalid_response")
    return [{"adults": min(2, adults - index)} for index in range(0, adults, 2)]


def _dates(checkin: str, checkout: str, adults: int) -> tuple[date, date]:
    occupancies(adults)
    start, end = date.fromisoformat(checkin), date.fromisoformat(checkout)
    if not 1 <= (end - start).days <= 30:
        raise DemoProviderError("invalid_response")
    return start, end


def _amount(value: Any, currency: Any, *, positive: bool = True) -> Decimal:
    """Never silently interpret missing, negative, non-USD or nonfinite amounts as free."""
    if isinstance(value, bool) or currency != "USD":
        raise DemoProviderError("invalid_response")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise DemoProviderError("invalid_response") from None
    if not amount.is_finite() or amount < 0 or amount >= 100000 or (positive and amount == 0):
        raise DemoProviderError("invalid_response")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _pricing(amount: Decimal, *, booking: Decimal | None = None, extra: Decimal = Decimal(0)) -> dict[str, Any]:
    return {
        "price": f"{amount:.2f}",
        "currency": "USD",
        "price_cents": int(amount * 100),
        "booking_price_cents": int((booking if booking is not None else amount) * 100),
        "pay_at_property_cents": int(extra * 100),
    }


async def _read_prebook(name: str, prebook_id: str) -> dict[str, Any]:
    """The two additional read-only tools, using the shared bounded, credential-free transport primitives."""
    if name not in _READ_TOOLS:
        raise DemoProviderError("invalid_response")
    token = travel_mcp_active.set(True)
    try:
        async with (
            asyncio.timeout(35),
            httpx2.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=35,
                headers={"accept-encoding": "identity"},
                event_hooks={"response": [nuitee._inspect]},
            ) as http,
            Client(
                streamable_http_client(nuitee.ENDPOINT, http_client=http, max_sse_event_size=nuitee.MAX_BYTES),
                mode="legacy",
            ) as client,
        ):
            result = await client.call_tool(name, {"prebookId": nuitee._id(prebook_id)})
            if result.is_error:
                raise DemoProviderError("unavailable")
            payload = result.structured_content
            if payload is None:
                texts = [block.text for block in result.content if isinstance(block, TextContent)]
                payload = json.loads(texts[0]) if len(texts) == 1 else None
            if not isinstance(payload, dict) or payload.get("error"):
                raise DemoProviderError("invalid_response")
            nuitee._reject_live(payload)
            return payload
    except Exception as error:
        leaves = to_leaves(error) if isinstance(error, BaseExceptionGroup) else [error]
        known = next((item.reason for item in leaves if isinstance(item, DemoProviderError)), None)
        timed_out = any(isinstance(item, (TimeoutError, httpx2.TimeoutException)) for item in leaves)
        raise DemoProviderError(known or ("timeout" if timed_out else "unavailable")) from None
    finally:
        travel_mcp_active.reset(token)


def _flight_details(journey: dict[str, Any], checkin: str, checkout: str, adults: int) -> list[str]:
    """Keep the route, dates and connections the user approved, with airport-local clocks."""
    start, end = _dates(checkin, checkout, adults)
    if not isinstance(journey, dict):
        raise DemoProviderError("invalid_response")
    segments = journey.get("segments")
    if not isinstance(segments, list) or any(
        not isinstance(item, dict) or item.get("direction") not in {"OUTBOUND", "INBOUND"} for item in segments
    ):
        raise DemoProviderError("invalid_response")
    if not 2 <= len(segments) <= 4:
        raise DemoProviderError("no_match")
    details = []
    prior: datetime | None = None
    for direction, origin, destination, day in (("OUTBOUND", "DFW", "FLG", start), ("INBOUND", "FLG", "DFW", end)):
        leg = [item for item in segments if item["direction"] == direction]
        if not leg or leg[0].get("originCode") != origin or leg[-1].get("destinationCode") != destination:
            raise DemoProviderError("no_match")
        for index, segment in enumerate(leg):
            depart = nuitee._local(segment.get("departureTime"), segment.get("originCode"))
            arrive = nuitee._local(segment.get("arrivalTime"), segment.get("destinationCode"))
            if (
                arrive.astimezone(UTC) <= depart.astimezone(UTC)
                or (prior is not None and depart.astimezone(UTC) <= prior.astimezone(UTC))
                or (index and leg[index - 1].get("destinationCode") != segment.get("originCode"))
            ):
                raise DemoProviderError("no_match")
            prior = arrive
        first = nuitee._local(leg[0]["departureTime"], origin)
        last = nuitee._local(leg[-1]["arrivalTime"], destination)
        if first.date() != day or last.date() != day or first.astimezone(UTC) <= datetime.now(UTC):
            raise DemoProviderError("no_match")
        details.append(
            f"{origin} → {destination} · {first:%b %d, %H:%M} to {last:%H:%M} local · {len(leg) - 1} stop(s)"
        )
    details.append(f"Round-trip total for {adults} adult(s), including quoted flight taxes and fees")
    return details


def _flight_price(pricing: dict[str, Any], adults: int) -> Decimal:
    """The provider's display.total is the whole-party total, not its perPassenger figure."""
    if not isinstance(pricing, dict):
        raise DemoProviderError("invalid_response")
    total = _amount(pricing.get("total"), pricing.get("currency"))
    people = pricing.get("perPassenger")
    if people is not None and not isinstance(people, dict):
        raise DemoProviderError("invalid_response")
    per_person = people.get("adult") if isinstance(people, dict) else None
    if per_person is not None and not isinstance(per_person, dict):
        raise DemoProviderError("invalid_response")
    if isinstance(per_person, dict):
        single = _amount(per_person.get("total"), per_person.get("currency"))
        if abs(single * adults - total) > Decimal("0.01") * adults:
            raise DemoProviderError("invalid_response")
    return total


def _flight_party(value: Any, adults: int, *, search: bool = False) -> None:
    """Search may omit counts or return zero-adult placeholders; verified counts must be exact."""
    if search and value is None:
        return
    if not isinstance(value, dict):
        raise DemoProviderError("invalid_response")
    for key, expected in (("adults", adults), ("children", 0), ("infants", 0)):
        count = value.get(key)
        if search and count is None:
            continue
        if type(count) is not int or count < 0:
            raise DemoProviderError("invalid_response")
        if count != expected and not (search and key == "adults" and count == 0):
            raise DemoProviderError("no_match")


async def search_flight(checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    _dates(checkin, checkout, adults)
    payload = await nuitee._call(
        "post_flights_rates",
        {
            "legs": [
                {"origin": "DFW", "destination": "FLG", "date": checkin, "direction": "OUTBOUND"},
                {"origin": "FLG", "destination": "DFW", "date": checkout, "direction": "INBOUND"},
            ],
            "adults": adults,
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
    data = payload.get("data")
    if not isinstance(data, list):
        raise DemoProviderError("invalid_response")
    if not data:
        raise DemoProviderError("no_match")
    if not isinstance(data[0], dict) or not isinstance(data[0].get("journeys"), list):
        raise DemoProviderError("invalid_response")
    candidates = []
    malformed = False
    for journey in data[0]["journeys"]:
        try:
            if not isinstance(journey, dict):
                raise DemoProviderError("invalid_response")
            _flight_party(journey.get("parameters"), adults, search=True)
            details = _flight_details(journey, checkin, checkout, adults)
            offer = journey["cheapestOffer"]
            amount = _flight_price(offer["pricing"]["display"], adults)
            candidates.append(
                {
                    "offer_id": nuitee._id(offer["offerId"]),
                    "title": "DFW ↔ Flagstaff (FLG)",
                    "details": details,
                    "checkin": checkin,
                    "checkout": checkout,
                    "adults": adults,
                    **_pricing(amount),
                }
            )
        except DemoProviderError as error:
            malformed |= error.reason != "no_match"
        except (KeyError, TypeError, ValueError, AttributeError):
            malformed = True
    if not candidates:
        raise DemoProviderError("invalid_response" if malformed else "no_match")
    candidates.sort(key=lambda item: item["price_cents"])
    return {**candidates[0], "alternatives": candidates[1:3]}


async def verify_flight(offer: dict[str, Any], checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    _dates(checkin, checkout, adults)
    choices = [{k: v for k, v in offer.items() if k != "alternatives"}, *offer.get("alternatives", [])][:3]
    failures = []
    for candidate in choices:
        try:
            payload = await nuitee._call("post_flights_verify", {"offerId": nuitee._id(candidate["offer_id"])}, 25)
            data = payload.get("data")
            if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                raise DemoProviderError("invalid_response")
            journey = data[0]["journey"]
            if not isinstance(journey, dict):
                raise DemoProviderError("invalid_response")
            _flight_party(journey.get("passengers"), adults)
            details = _flight_details(journey, checkin, checkout, adults)
            return {**candidate, "details": details, **_pricing(_flight_price(journey["pricing"]["display"], adults))}
        except DemoProviderError as error:
            failures.append(error.reason)
        except (KeyError, TypeError, ValueError, AttributeError):
            failures.append("invalid_response")
    reason = next(
        (
            item
            for item in ("rate_limited", "timeout", "invalid_response", "unavailable", "no_match")
            if item in failures
        ),
        failures[0] if failures else "unavailable",
    )
    raise DemoProviderError(reason)


def _flight_prepared(data: dict[str, Any], checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    _dates(checkin, checkout, adults)
    if "ACC_CREDIT_CARD" not in data.get("paymentTypes", []):
        raise DemoProviderError("invalid_response")
    booking = data["booking"]
    passengers = booking.get("passengers")
    if not isinstance(passengers, list) or len(passengers) != adults:
        raise DemoProviderError("invalid_response")
    for index, passenger in enumerate(passengers):
        if (
            not isinstance(passenger, dict)
            or passenger.get("firstName") != _NAMES[index][0]
            or passenger.get("lastName") != _NAMES[index][1]
            or passenger.get("birthday") != "1990-01-15"
            or (
                "passengerType" in passenger
                and (type(passenger["passengerType"]) is not int or passenger["passengerType"] != 0)
            )
        ):
            raise DemoProviderError("invalid_response")
    journey = booking["journey"]
    if not isinstance(journey, dict):
        raise DemoProviderError("invalid_response")
    if "passengers" in journey:
        _flight_party(journey["passengers"], adults)
    total = _amount(data.get("price"), data.get("currency"))
    if total != _amount(booking["pricing"].get("totalAmount"), booking["pricing"].get("currency")):
        raise DemoProviderError("invalid_response")
    if total != _flight_price(booking["journey"]["pricing"]["display"], adults):
        raise DemoProviderError("invalid_response")
    return {
        "prebook_id": nuitee._id(data["prebookId"]),
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "details": _flight_details(booking["journey"], checkin, checkout, adults),
        **_pricing(total),
    }


async def prebook_flight(offer: dict[str, Any], adults: int) -> dict[str, Any]:
    occupancies(adults)
    payload = await nuitee._call(
        "post_flights_prebooks",
        {
            "offerId": nuitee._id(offer["offer_id"]),
            "travelPurpose": "LEISURE",
            "contact": {
                "firstName": "Avery",
                "lastName": "Linton",
                "email": "nimbus-surprise@example.com",
                "phoneCountryCode": "1",
                "phoneNumber": "2025550123",
            },
            "passengers": [
                {
                    "firstName": first,
                    "lastName": last,
                    "birthday": "1990-01-15",
                    "gender": "M",
                    "nationality": "US",
                    "passengerType": 0,
                }
                for first, last in _NAMES[:adults]
            ],
        },
        45,
    )
    return _flight_prepared(nuitee._first(payload), offer["checkin"], offer["checkout"], adults)


async def refresh_flight(prepared: dict[str, Any], checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    """Read the same checkout session; no re-search, new prebook, payment or booking."""
    payload = await _read_prebook("get_flight_prebook", prepared["prebook_id"])
    raw = payload.get("data")
    data = nuitee._first(payload) if isinstance(raw, list) else raw
    if not isinstance(data, dict) or data.get("prebookId") != prepared["prebook_id"]:
        raise DemoProviderError("invalid_response")
    return _flight_prepared(data, checkin, checkout, adults)


def _near_canyon(hotel: dict[str, Any]) -> bool:
    try:
        lat, lon = float(hotel["latitude"]), float(hotel["longitude"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return False
        phi, base = math.radians(lat), math.radians(_CANYON[0])
        a = (
            math.sin((phi - base) / 2) ** 2
            + math.cos(phi) * math.cos(base) * math.sin(math.radians(lon - _CANYON[1]) / 2) ** 2
        )
        distance = 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))
        return distance <= 20000 and hotel.get("country_code") == "US"
    except (KeyError, TypeError, ValueError):
        return False


def _room_price(room_types: list[dict[str, Any]], adults: int) -> tuple[Decimal, Decimal]:
    """Validate exact occupancies, then total all rooms once, adding only excluded mandatory fees."""
    expected = occupancies(adults)
    rates = [rate for room in room_types for rate in room["rates"]]
    if len(rates) != len(expected):
        raise DemoProviderError("invalid_response")
    occupied: set[int] = set()
    total, extra = Decimal(0), Decimal(0)
    for rate in rates:
        number = rate.get("occupancyNumber")
        if type(number) is not int or not 1 <= number <= len(expected) or number in occupied:
            raise DemoProviderError("invalid_response")
        if rate.get("adultCount") != expected[number - 1]["adults"] or rate.get("childCount") != 0:
            raise DemoProviderError("invalid_response")
        occupied.add(number)
        retail = rate["retailRate"]
        amounts = retail.get("total")
        if not isinstance(amounts, list) or len(amounts) != 1:
            raise DemoProviderError("invalid_response")
        total += _amount(amounts[0].get("amount"), amounts[0].get("currency"))
        # Official schema: null or omitted fees means no disclosed excluded fees. Unknown entries fail closed.
        fees = retail.get("taxesAndFees")
        if fees is None:
            fees = []
        if not isinstance(fees, list):
            raise DemoProviderError("invalid_response")
        for fee in fees:
            if not isinstance(fee, dict) or type(fee.get("included")) is not bool:
                raise DemoProviderError("invalid_response")
            if not fee["included"]:
                extra += _amount(fee.get("amount"), fee.get("currency"), positive=False)
    return total, extra


def _hotel_details(adults: int, checkin: str, checkout: str, extra: Decimal) -> list[str]:
    nights = (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days
    return [
        f"Grand Canyon South Rim / Tusayan area · {adults} adult(s) · "
        f"{len(occupancies(adults))} room(s) · {nights} night(s)",
        f"Full-stay total includes USD {extra:.2f} in disclosed mandatory fees payable at the property.",
        "Flagstaff to Grand Canyon ground transportation (about 80 miles) is not included.",
    ]


async def search_hotel(checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    _dates(checkin, checkout, adults)
    payload = await nuitee._call(
        "post_hotels_rates",
        {
            "occupancies": occupancies(adults),
            "currency": "USD",
            "guestNationality": "US",
            "checkin": checkin,
            "checkout": checkout,
            "latitude": _CANYON[0],
            "longitude": _CANYON[1],
            "radius": 20000,
            "limit": 8,
            "maxRatesPerHotel": 1,
            "includeHotelData": True,
            "timeout": 10,
            "sort": [{"field": "price", "direction": "ascending"}],
        },
    )
    if payload.get("sandbox") is not True:
        raise DemoProviderError("invalid_response")
    hotels = {h["id"]: h for h in payload.get("hotels", []) if isinstance(h, dict) and "id" in h and _near_canyon(h)}
    candidates = []
    for item in payload.get("data", []):
        try:
            hotel = hotels[item["hotelId"]]
            room = item["roomTypes"][0]
            base, extra = _room_price([room], adults)
            retail = room["offerRetailRate"]
            if base != _amount(retail.get("amount"), retail.get("currency")):
                raise DemoProviderError("invalid_response")
            candidates.append(
                {
                    "offer_id": nuitee._id(room["offerId"]),
                    "hotel_id": nuitee._id(hotel["id"]),
                    "title": nuitee._text(hotel["name"]),
                    "details": _hotel_details(adults, checkin, checkout, extra),
                    "checkin": checkin,
                    "checkout": checkout,
                    "adults": adults,
                    **_pricing(base + extra, booking=base, extra=extra),
                }
            )
        except (DemoProviderError, KeyError, IndexError, TypeError, ValueError):
            continue
    if not candidates:
        raise DemoProviderError("no_match")
    # The sandbox refuses some hotels' rates at prebook, so the next-cheapest few stay available as fallbacks.
    candidates.sort(key=lambda item: item["price_cents"])
    return {**candidates[0], "alternatives": candidates[1:4]}


def _hotel_prepared(data: dict[str, Any], hotel_id: str, checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    if data.get("hotelId") != hotel_id or data.get("checkin") != checkin or data.get("checkout") != checkout:
        raise DemoProviderError("invalid_response")
    if "ACC_CREDIT_CARD" not in data.get("paymentTypes", []):
        raise DemoProviderError("invalid_response")
    base, extra = _room_price(data["roomTypes"], adults)
    if base != _amount(data.get("price"), data.get("currency")):
        raise DemoProviderError("invalid_response")
    return {
        "prebook_id": nuitee._id(data["prebookId"]),
        "hotel_id": hotel_id,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "details": _hotel_details(adults, checkin, checkout, extra),
        **_pricing(base + extra, booking=base, extra=extra),
    }


async def prebook_hotel(offer: dict[str, Any], adults: int) -> dict[str, Any]:
    """Prebook the cheapest hotel, or the next-cheapest when the sandbox refuses a rate (issue 194)."""
    choices = [{k: v for k, v in offer.items() if k != "alternatives"}, *offer.get("alternatives", [])][:4]
    reason = "unavailable"
    for candidate in choices:
        try:
            payload = await nuitee._call(
                "post_rates_prebook",
                {
                    "offerId": nuitee._id(candidate["offer_id"]),
                    "usePaymentSdk": False,
                    "timeout": 20,
                },
            )
            if payload.get("sandbox") is not True:
                raise DemoProviderError("invalid_response")
            prepared = _hotel_prepared(
                payload["data"], candidate["hotel_id"], candidate["checkin"], candidate["checkout"], adults
            )
            return {**prepared, "title": candidate["title"]}
        except DemoProviderError as error:
            reason = error.reason
        except (KeyError, TypeError, ValueError):
            reason = "invalid_response"
    raise DemoProviderError(reason)


async def refresh_hotel(prepared: dict[str, Any], checkin: str, checkout: str, adults: int) -> dict[str, Any]:
    """Read the same hotel prebook; the endpoint omits sandbox, so its previously attested ID is checked."""
    payload = await _read_prebook("get_prebooks_prebookid", prepared["prebook_id"])
    data = payload.get("data", {})
    if data.get("prebookId") != prepared["prebook_id"]:
        raise DemoProviderError("invalid_response")
    return _hotel_prepared(data, prepared["hotel_id"], checkin, checkout, adults)


async def book_flight(prebook_id: str) -> dict[str, Any]:
    """Called only by the confirmation-gated workflow; the provider deduplicates this same prebook."""
    return await nuitee.book_flight(prebook_id)


async def book_hotel(prebook_id: str, client_reference: str, adults: int) -> dict[str, Any]:
    """One synthetic lead guest per requested room, one mutation, one persistent deduplication reference."""
    rooms = occupancies(adults)
    payload = await nuitee._call(
        "post_rates_book",
        {
            "prebookId": nuitee._id(prebook_id),
            "clientReference": nuitee._text(client_reference, 100),
            "timeout": 60,
            "holder": {
                "firstName": "Avery",
                "lastName": "Linton",
                "email": "nimbus-surprise@example.com",
                "phone": "+12025550123",
            },
            "guests": [
                {
                    "occupancyNumber": index + 1,
                    "firstName": _NAMES[index * 2][0],
                    "lastName": _NAMES[index * 2][1],
                    "email": "nimbus-surprise@example.com",
                }
                for index in range(len(rooms))
            ],
            "payment": {"method": "ACC_CREDIT_CARD"},
            "customTags": {"PURPOSE": "NIMBUS_SURPRISE_SANDBOX"},
        },
        75,
    )
    if payload.get("sandbox") is not True or payload.get("data", {}).get("clientReference") != client_reference:
        raise DemoProviderError("invalid_response")
    return nuitee._booking(payload["data"], flight=False)


async def retrieve_flight(booking_id: str) -> dict[str, Any]:
    return await nuitee.retrieve_flight(booking_id)


async def recover_flight(prebook_id: str) -> dict[str, Any]:
    """Read only: an unknown attempt must never turn a status refresh into a new booking submission."""
    payload = await _read_prebook("get_flight_prebook", prebook_id)
    raw = payload.get("data")
    data = nuitee._first(payload) if isinstance(raw, list) else raw
    if not isinstance(data, dict) or data.get("prebookId") != prebook_id:
        raise DemoProviderError("invalid_response")
    booking = data.get("booking")
    booking_id = booking.get("bookingId") if isinstance(booking, dict) else None
    if not booking_id:
        raise DemoProviderError("not_found")
    return await nuitee.retrieve_flight(nuitee._id(booking_id))


async def recover_hotel(client_reference: str) -> dict[str, Any]:
    return await nuitee.recover_hotel(client_reference)
