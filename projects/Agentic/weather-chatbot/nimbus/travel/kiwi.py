"""Adapter for Kiwi's read-only flight search, including outbound and return legs."""

import re
from datetime import date, datetime
from typing import Any

from nimbus.travel.mcp_client import TravelProviderError, call_search
from nimbus.travel.models import FlightSearch, TravelOffer, TravelReport
from nimbus.travel.providers import currency_code, money, offer_link, records_report, short_text

# For other multi-airport regions use the full city name. Show the actual airports on each offer.
METRO_AIRPORTS = {
    "NYC": {"JFK", "LGA", "EWR", "SWF"},
    "LON": {"LHR", "LGW", "LCY", "LTN", "STN", "SEN"},
    "WAS": {"DCA", "IAD", "BWI"},
}


def to_flight_arguments(query: FlightSearch) -> dict[str, Any]:
    """Translate ISO travel dates and explicit filters to Kiwi's search schema."""
    args: dict[str, Any] = {
        "flyFrom": query.origin,
        "flyTo": query.destination,
        "departureDate": query.departure_date.strftime("%d/%m/%Y"),
        "adults": query.adults,
        "children": query.children,
        "infants": query.infants,
        "currency": query.currency,
    }
    if query.return_date is not None:
        args["returnDate"] = query.return_date.strftime("%d/%m/%Y")
    if query.max_price is not None:
        args["price_to"] = int(query.max_price)
    if query.max_stops is not None:
        args["max_sector_stopovers"] = query.max_stops
    return args


def _leg(leg: object, day: date, max_stops: int | None, start: str, end: str) -> tuple[str, str]:
    """Validate a leg's airports, times, departure date and optional user-specified stop limit."""
    if not isinstance(leg, dict):
        raise ValueError("Missing flight leg")
    origin, destination = leg.get("from"), leg.get("to")
    if not all(isinstance(item, str) and re.fullmatch("[A-Z]{3}", item) for item in (origin, destination)):
        raise ValueError("Invalid airports")
    for requested, actual in ((start, origin), (end, destination)):
        code = requested.upper()
        if re.fullmatch("[A-Za-z]{3}", requested) and actual not in METRO_AIRPORTS.get(code, {code}):
            raise ValueError("Different airport than requested")
    if origin == destination:
        raise ValueError("Identical endpoints")
    times = [short_text(leg.get(key)) for key in ("departureTime", "arrivalTime")]
    if not all(re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value) for value in times):
        raise ValueError("Expected local date and time")
    depart, arrive = (datetime.fromisoformat(value) for value in times)
    stops = leg.get("stops")
    if depart.date() != day or type(stops) is not int or stops < 0 or (max_stops is not None and stops > max_stops):
        raise ValueError("Unexpected flight leg")
    route = f"{origin} → {destination}"
    return route, f"{route}: {depart:%b %d %H:%M} to {arrive:%b %d %H:%M} local · {stops} stop(s)"


def _confirmed_party(passengers: object, query: FlightSearch) -> bool:
    """Kiwi may omit the entire echo. In a supplied echo each omitted age band defaults to zero."""
    if passengers is None:
        return False
    if not isinstance(passengers, dict):
        raise TravelProviderError("invalid_response")
    for band, requested in (("adults", query.adults), ("children", query.children), ("infants", query.infants)):
        count = passengers.get(band, 0)
        if type(count) is not int or count != requested:
            raise TravelProviderError("invalid_response")
    return True


def to_flight_report(payload: dict[str, Any], query: FlightSearch) -> TravelReport:
    """Filter provider output into price, route, schedule and the verified booking link."""
    if payload.get("error"):
        raise TravelProviderError("unavailable")
    if payload.get("resultsCount") and not payload.get("itineraries"):
        raise TravelProviderError("invalid_response")
    party_confirmed = _confirmed_party(payload.get("passengers"), query)

    def parse(item: dict[str, Any]) -> TravelOffer:
        """Keep a single complete itinerary for the dates the traveler requested."""
        code = currency_code(payload.get("currency"))
        price = money(item.get("price"))
        if code != query.currency or (query.max_price is not None and (not party_confirmed or price > query.max_price)):
            raise ValueError("Offer does not match search")
        title, outbound = _leg(
            item.get("outbound"), query.departure_date, query.max_stops, query.origin, query.destination
        )
        details = [outbound]
        if query.return_date:
            _, inbound = _leg(item.get("inbound"), query.return_date, query.max_stops, query.destination, query.origin)
            details.append(inbound)
            title += " · round trip"
        elif item.get("inbound") is not None:
            raise ValueError("Unexpected return leg")
        if not party_confirmed:
            details.append("Kiwi did not confirm the passenger counts. Check the fare for your party.")
        return TravelOffer(
            title=title,
            price=price if party_confirmed else None,
            currency=code if party_confirmed else None,
            price_basis="party_total" if party_confirmed else "unknown",
            details=tuple(details),
            url=offer_link("kiwi", item.get("bookingUrl")),
        )

    report = records_report("kiwi", payload.get("itineraries"), parse)
    if report.offers and not party_confirmed:
        return report.model_copy(update={"status": "partial"})
    return report


async def search_flights(query: FlightSearch) -> TravelReport:
    """Search Kiwi once and return a typed outcome to the planner or the chat tool."""
    try:
        # ① Input is validated by the local model. A failed upstream check has a distinct status from zero results.
        payload = await call_search("kiwi", "search-flight", to_flight_arguments(query))
        return to_flight_report(payload, query)
    except TravelProviderError as error:
        return TravelReport(provider="kiwi", status=error.reason)
