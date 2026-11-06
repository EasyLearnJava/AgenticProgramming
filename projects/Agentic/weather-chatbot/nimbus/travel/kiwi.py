"""Adapter for Kiwi's read-only flight search, including outbound and return legs."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from nimbus.travel.airports import AIRPORT_ZONES
from nimbus.travel.mcp_client import TravelProviderError, call_search
from nimbus.travel.models import FlightSearch, ReturnWindow, TravelOffer, TravelReport
from nimbus.travel.providers import currency_code, money, offer_link, records_report, short_text

# IATA's metropolitan city codes that name no airport of their own, with the airports each covers: a model may send
# CHI for Chicago, and Kiwi answers from ORD or MDW. Any other three letters are one exact airport. Each offer
# shows its actual airports.
METRO_AIRPORTS = {
    "NYC": {"JFK", "LGA", "EWR", "SWF"},
    "WAS": {"DCA", "IAD", "BWI"},
    "CHI": {"ORD", "MDW"},
    "DTT": {"DTW"},
    "YTO": {"YYZ", "YTZ"},
    "YMQ": {"YUL", "YHU"},
    "YEA": {"YEG"},
    "LON": {"LHR", "LGW", "LCY", "LTN", "STN", "SEN"},
    "PAR": {"CDG", "ORY", "BVA"},
    "MIL": {"MXP", "LIN", "BGY"},
    "ROM": {"FCO", "CIA"},
    "STO": {"ARN", "BMA", "NYO", "VST"},
    "MOW": {"SVO", "DME", "VKO", "ZIA"},
    "BUH": {"OTP", "BBU"},
    "REK": {"KEF", "RKV"},
    "TYO": {"NRT", "HND"},
    "OSA": {"KIX", "ITM", "UKB"},
    "SEL": {"ICN", "GMP"},
    "BJS": {"PEK", "PKX", "NAY"},
    "JKT": {"CGK", "HLP"},
    "SAO": {"GRU", "CGH", "VCP"},
    "RIO": {"GIG", "SDU"},
    "BUE": {"EZE", "AEP"},
}


def _clock_range(window: ReturnWindow) -> tuple[time, time]:
    """Inclusive local bounds; Kiwi receives coarse hours, each returned card is checked to the minute."""
    if window == "morning":
        return time(6), time(11, 59, 59, 999999)
    if window == "evening":
        return time(18), time.max
    if window == "by_noon":
        return time.min, time(12)
    if window.startswith("by_"):
        return time.min, time.fromisoformat(window.removeprefix("by_"))
    return time.min, time.max


def _return_departure_start(query: FlightSearch, arrival_day: date) -> date:
    """A departure the night before may arrive home on the requested morning or by its deadline."""
    if query.return_window == "morning" or query.return_window.startswith("by_"):
        return max(query.departure_date, arrival_day - timedelta(days=1))
    return arrival_day


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
        start = _return_departure_start(query, query.return_date)
        args["returnDate"] = start.strftime("%d/%m/%Y")
        if start != query.return_date:
            args["returnDateTo"] = query.return_date.strftime("%d/%m/%Y")
    for prefix, window in (("dtime", query.depart_window), ("ret_atime", query.return_window)):
        if window:
            earliest, latest = _clock_range(window)
            args[f"{prefix}_from"] = earliest.hour
            args[f"{prefix}_to"] = latest.hour
    if query.max_price is not None:
        args["price_to"] = int(query.max_price)
    if query.max_stops is not None:
        args["max_sector_stopovers"] = query.max_stops
    return args


@dataclass(frozen=True)
class _Leg:
    origin: str
    destination: str
    depart: datetime
    arrive: datetime
    stops: int

    @property
    def route(self) -> str:
        return f"{self.origin} → {self.destination}"

    @property
    def detail(self) -> str:
        return f"{self.route}: {self.depart:%b %d %H:%M} to {self.arrive:%b %d %H:%M} local · {self.stops} stop(s)"

    def check_return(self, inbound: "_Leg") -> None:
        """Compare absolute instants, or airport-local clocks when both events use the very same airport."""
        arrived, leaving = self.arrive, inbound.depart
        if arrived.tzinfo and leaving.tzinfo:
            arrived, leaving = arrived.astimezone(UTC), leaving.astimezone(UTC)
        elif self.destination == inbound.origin and arrived.tzinfo is None and leaving.tzinfo is None:
            pass  # Both unqualified timestamps are local to the same airport.
        else:
            return
        if leaving <= arrived:
            raise ValueError("The return departs before the outbound trip has finished")


def _at_airport(value: str, airport: str, check_local: bool) -> datetime:
    """Kiwi supplies airport-local times. Convert explicitly offset timestamps when the airport zone is known."""
    stamp = datetime.fromisoformat(value)
    if zone := AIRPORT_ZONES.get(airport):
        local = ZoneInfo(zone)
        if stamp.tzinfo is not None:
            return stamp.astimezone(local)
        localized = stamp.replace(tzinfo=local)
        if localized.utcoffset() != localized.replace(fold=1).utcoffset():
            raise ValueError("The local clock changes at this time; an explicit offset is required")
        return localized
    if stamp.tzinfo is not None and check_local:
        raise ValueError("Cannot verify the offset in the local airport zone")
    return stamp


def _in_window(stamp: datetime, day: date, window: ReturnWindow) -> bool:
    if not window:
        return True
    earliest, latest = _clock_range(window)
    return stamp.date() == day and earliest <= stamp.time() <= latest


def _upcoming(stamp: datetime, now: datetime) -> bool:
    """Avoid suggesting elapsed departures. Fail honestly if a same-day offset cannot be established."""
    if stamp.tzinfo is not None:
        return stamp.astimezone(UTC) > now
    if stamp.date() > (now + timedelta(hours=14)).date():
        return True
    if stamp.date() < (now - timedelta(hours=12)).date():
        return False
    raise ValueError("Unknown departure airport time zone")


def _leg(
    leg: object,
    day: date,
    max_stops: int | None,
    start: str,
    end: str,
    check_local: bool,
    *,
    earliest: date | None = None,
) -> _Leg:
    """Validate a leg's airports, times, departure date and optional user-specified stop limit."""
    if not isinstance(leg, dict):
        raise ValueError("Missing flight leg")
    origin, destination = leg.get("from"), leg.get("to")
    if not isinstance(origin, str) or not isinstance(destination, str):
        raise ValueError("Missing airports")
    if not all(re.fullmatch("[A-Z]{3}", item) for item in (origin, destination)):
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
    depart = _at_airport(times[0], origin, check_local)
    arrive = _at_airport(times[1], destination, check_local)
    if check_local and depart.tzinfo and arrive.tzinfo and arrive.astimezone(UTC) <= depart.astimezone(UTC):
        raise ValueError("The flight arrival does not follow its departure")
    stops = leg.get("stops")
    if not (earliest or day) <= depart.date() <= day:
        raise ValueError("Unexpected flight date")
    if type(stops) is not int or stops < 0 or (max_stops is not None and stops > max_stops):
        raise ValueError("Unexpected flight leg")
    return _Leg(origin, destination, depart, arrive, stops)


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


def to_flight_report(payload: dict[str, Any], query: FlightSearch, *, now: datetime | None = None) -> TravelReport:
    """Filter provider output into price, route, schedule and the verified booking link."""
    if payload.get("error"):
        raise TravelProviderError("unavailable")
    if payload.get("resultsCount") and not payload.get("itineraries"):
        raise TravelProviderError("invalid_response")
    party_confirmed = _confirmed_party(payload.get("passengers"), query)
    checked = now or datetime.now(UTC)
    check_local = bool(query.depart_window or query.return_window)

    def parse(item: dict[str, Any]) -> TravelOffer | None:
        """Keep a single complete itinerary for the dates the traveler requested."""
        code = currency_code(payload.get("currency"))
        price = money(item.get("price"))
        if code != query.currency or (query.max_price is not None and (not party_confirmed or price > query.max_price)):
            raise ValueError("Offer does not match search")
        outbound = _leg(
            item.get("outbound"), query.departure_date, query.max_stops, query.origin, query.destination, check_local
        )
        title, details = outbound.route, [outbound.detail]
        matches = _in_window(outbound.depart, query.departure_date, query.depart_window)
        if query.return_date:
            inbound = _leg(
                item.get("inbound"),
                query.return_date,
                query.max_stops,
                query.destination,
                query.origin,
                check_local,
                earliest=_return_departure_start(query, query.return_date),
            )
            outbound.check_return(inbound)
            details.append(inbound.detail)
            matches = matches and _in_window(inbound.arrive, query.return_date, query.return_window)
            title += " · round trip"
        elif item.get("inbound") is not None:
            raise ValueError("Unexpected return leg")
        if not party_confirmed:
            details.append("Kiwi did not confirm the passenger counts. Check the fare for your party.")
        offer = TravelOffer(
            title=title,
            price=price if party_confirmed else None,
            currency=code if party_confirmed else None,
            price_basis="party_total" if party_confirmed else "unknown",
            details=tuple(details),
            url=offer_link("kiwi", item.get("bookingUrl")),
        )
        if not matches or not _upcoming(outbound.depart, checked):
            return None
        return offer

    report = records_report(
        "kiwi", payload.get("itineraries"), parse, empty_reason="time_window" if check_local else None
    )
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
