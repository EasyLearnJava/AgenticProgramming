"""Shared validation of live offers. Only provider adapters see untrusted MCP payloads."""

import re
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Literal
from urllib.parse import urlsplit

from markdown_it.common.normalize_url import normalizeLink

from nimbus.travel.mcp_client import TravelProviderError
from nimbus.travel.models import MAX_OFFERS, Provider, TravelOffer, TravelReport

# Booking links currently come from these exact hosts. Locale-specific hosts require a reviewed fixture.
BOOKING_HOSTS: Final = {"kiwi": {"kiwi.com", "www.kiwi.com"}, "trivago": {"www.trivago.com", "trivago.com"}}
MAX_AMOUNT: Final = Decimal("1000000000")


def offer_link(provider: Provider, raw: object) -> str | None:
    """Accept exactly the provider's HTTPS links, keeping the opaque path and query intact."""
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw or len(raw) > 8192 or "\\" in raw:
        raise ValueError("Invalid booking URL")
    if any(ord(char) < 33 or ord(char) == 127 for char in raw):
        raise ValueError("Invalid booking URL")
    parts = urlsplit(raw)
    if (
        parts.scheme != "https"
        or parts.hostname not in BOOKING_HOSTS[provider]
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
    ):
        raise ValueError("Invalid booking URL")
    return normalizeLink(raw)


def money(value: object) -> Decimal:
    """Parse a finite nonnegative amount; provider adapters strip only recognized display formatting."""
    if not isinstance(value, (float, int, str)) or isinstance(value, bool) or len(str(value)) > 32:
        raise ValueError("Invalid price")
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid price") from None
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -4 or not 0 <= amount <= MAX_AMOUNT:
        raise ValueError("Invalid price")
    return amount


def currency_code(value: object) -> str:
    """Return the three-letter currency actually quoted by the provider."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("Missing currency")
    return value


def short_text(value: object) -> str:
    """Return a bounded plain-text label; discard fields which would exceed context budgets."""
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise ValueError("Invalid offer label")
    return " ".join(value.split())


def records_report(
    provider: Provider,
    rows: object,
    parse: Callable[[dict[str, Any]], TravelOffer | None],
    *,
    empty_reason: Literal["time_window"] | None = None,
) -> TravelReport:
    """Keep up to five distinct eligible offers. A parser returns None for a valid but ineligible result."""
    if not isinstance(rows, list):
        raise TravelProviderError("invalid_response")
    if not rows:
        return TravelReport(provider=provider, status="no_results")
    offers: list[TravelOffer] = []
    seen: set[str] = set()
    skipped = False
    for item in rows:
        try:
            if not isinstance(item, dict):
                raise ValueError("Invalid offer")
            offer = parse(item)
        except (ValueError, KeyError, TypeError):
            skipped = True
            continue
        if offer is None:
            continue
        if offer.url is not None:
            if offer.url in seen:
                continue
            seen.add(offer.url)
        offers.append(offer)
        if len(offers) == MAX_OFFERS:
            break
    if not offers and skipped:
        raise TravelProviderError("invalid_response")
    if not offers:
        return TravelReport(provider=provider, status="no_results", empty_reason=empty_reason)
    return TravelReport(provider=provider, status="partial" if skipped else "found", offers=tuple(offers))
