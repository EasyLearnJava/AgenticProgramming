"""Normalize Trivago's destination/radius accommodation search. Only selected hotel facts enter the answer."""

import re
from decimal import Decimal
from typing import Any

from nimbus.travel.mcp_client import TravelProviderError, call_search
from nimbus.travel.models import HotelSearch, TravelOffer, TravelReport
from nimbus.travel.providers import currency_code, money, offer_link, records_report, short_text

# English display prices with currency prefix/suffix and optional thousands grouping. Reject ambiguous decimals.
DISPLAY_AMOUNT = re.compile(r"(?P<amount>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)")
SYMBOL_CURRENCIES = {
    "$": {"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN", "ARS", "CLP", "COP", "TWD"},
    "US$": {"USD"},
    "CA$": {"CAD"},
    "A$": {"AUD"},
    "NZ$": {"NZD"},
    "€": {"EUR"},
    "£": {"GBP"},
    "¥": {"JPY", "CNY"},
    "₹": {"INR"},
    "kr": {"DKK", "NOK", "SEK", "ISK"},
}


def to_hotel_arguments(query: HotelSearch) -> tuple[str, dict[str, Any]]:
    """Send the requested occupancy and explicit nightly budget to the right Trivago operation."""
    args: dict[str, Any] = {
        "arrival": query.check_in.isoformat(),
        "departure": query.check_out.isoformat(),
        "rooms": query.rooms,
        "adults": query.adults,
        "children": len(query.children_ages),
        "currency": query.currency,
    }
    if query.children_ages:
        args["children_ages"] = "-".join(str(age) for age in query.children_ages)
    if query.max_price is not None:
        args["price_range"] = {"maxPrice": query.max_price, "budgetType": "PRICE_PER_NIGHT"}
    if query.destination is not None:
        return "trivago-accommodation-search", {**args, "query": query.destination}
    return "trivago-accommodation-radius-search", {**args, "latitude": query.latitude, "longitude": query.longitude}


def _price(value: object, code: str) -> Decimal:
    """Validate a decimal display price using its accompanying currency code; never infer prices from prose."""
    text = short_text(value)
    match = DISPLAY_AMOUNT.search(text)
    if match is None:
        raise ValueError("Invalid hotel price")
    units = (text[: match.start()] + text[match.end() :]).strip()
    if units and units != code and code not in SYMBOL_CURRENCIES.get(units, frozenset()):
        raise ValueError("Invalid hotel price format")
    return money(match["amount"].replace(",", ""))


def _deal(raw: object, query: HotelSearch) -> tuple[Decimal, Decimal, str | None, str]:
    """Return only a comparable stay price from a deal matching the user's currency and nightly budget."""
    if not isinstance(raw, dict) or currency_code(raw.get("currency")) != query.currency:
        raise ValueError("Mismatched hotel currency")
    stay = _price(raw.get("price_per_stay"), query.currency)
    night = _price(raw.get("price_per_night"), query.currency)
    if query.max_price is not None and night > query.max_price:
        raise ValueError("Outside nightly budget")
    return stay, night, offer_link("trivago", raw.get("deal_url")), short_text(raw.get("advertiser"))


def _hotel(row: dict[str, Any], query: HotelSearch) -> TravelOffer:
    """Select the lowest valid full-stay offer for one property and retain its corresponding link."""
    if row.get("arrival") != query.check_in.isoformat() or row.get("departure") != query.check_out.isoformat():
        raise ValueError("Mismatched stay dates")
    deals = row.get("deals")
    if not isinstance(deals, list):
        raise ValueError("Missing hotel deals")
    valid = []
    for raw in deals:
        try:
            valid.append(_deal(raw, query))
        except ValueError:
            continue
    if not valid:
        raise ValueError("No comparable hotel deal")
    stay, night, link, seller = min(valid, key=lambda deal: deal[0])
    return TravelOffer(
        title=short_text(row.get("accommodation_name")),
        price=stay,
        currency=query.currency,
        price_basis="stay_total",
        details=(f"{night} {query.currency} per night", seller),
        url=link,
    )


def to_hotel_report(payload: dict[str, Any], query: HotelSearch) -> TravelReport:
    """Return validated accommodation facts, omitting provider prompts, image URLs and opaque metadata."""
    if payload.get("validation_errors"):
        return TravelReport(provider="trivago", status="invalid_input")
    if payload.get("error"):
        raise TravelProviderError("unavailable")
    return records_report("trivago", payload.get("accommodations"), lambda row: _hotel(row, query))


async def search_hotels(query: HotelSearch) -> TravelReport:
    """Search Trivago once and return a typed outcome to the planner or the chat tool."""
    try:
        # ① The argument builder chooses a fixed search operation; the user can supply neither a tool nor an endpoint.
        name, args = to_hotel_arguments(query)
        return to_hotel_report(await call_search("trivago", name, args), query)
    except TravelProviderError as error:
        return TravelReport(provider="trivago", status=error.reason)
