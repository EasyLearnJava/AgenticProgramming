"""Provider-independent, bounded travel requests and offers. Prices and booking links come from live search only."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

MAX_OFFERS: Final = 5
MAX_CONTEXT_BYTES: Final = 24_000
# Live provider discovery plus search took about ten seconds.
TRAVEL_TIMEOUT_SECONDS: Final = 14.0
type Provider = Literal["kiwi", "trivago"]
type TravelStatus = Literal[
    "found",
    "no_results",
    "partial",
    "invalid_response",
    "rate_limited",
    "timeout",
    "unavailable",
    "budget_exhausted",
    "busy",
    "disabled",
    "invalid_input",
]
type PriceBasis = Literal["party_total", "per_person", "per_night", "stay_total", "unknown"]
type Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
type Place = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f<>]+$")
]
type CountAdults = Annotated[int, Field(ge=1, le=9, strict=True)]
type PriceLimit = Annotated[int, Field(gt=0, le=10_000_000, strict=True)]
type FlightPlace = Annotated[
    Place, Field(description="Use a three-letter airport code for an exact airport or spell out a city name.")
]


def _date_value(value: object) -> object:
    """Accept calendar dates, including an ISO string, without treating integers as timestamps."""
    if isinstance(value, datetime) or not isinstance(value, (date, str)):
        raise ValueError("use an ISO calendar date")
    if isinstance(value, str) and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("use YYYY-MM-DD for travel dates")
    return value


type SearchDate = Annotated[date, BeforeValidator(_date_value)]


def _tool_schema(schema: dict[str, Any]) -> None:
    """Keep the Gemini function declaration compatible while validation still rejects unknown fields."""
    schema.pop("additionalProperties", None)


class _Search(BaseModel):
    """Immutable and hashable so identical searches in one answer share an upstream call."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=_tool_schema)
    currency: Currency = "USD"
    adults: CountAdults = 1


class FlightSearch(_Search):
    """The route, departure date and travelers for a one-way or return itinerary."""

    origin: FlightPlace
    max_price: PriceLimit | None = Field(default=None, description="Maximum price for the whole traveling party.")
    destination: FlightPlace
    departure_date: SearchDate
    return_date: SearchDate | None = None
    adults: CountAdults = Field(default=1, description="Travelers aged 12 and older on the flight.")
    children: int = Field(default=0, ge=0, le=8, strict=True, description="Children aged 2 through 11.")
    infants: int = Field(default=0, ge=0, le=4, strict=True, description="Infants younger than 2.")
    max_stops: int | None = Field(default=None, ge=0, le=8, strict=True)

    @model_validator(mode="after")
    def valid_trip(self) -> Self:
        """Reject impossible routes, date ranges or passenger groups before contacting Kiwi."""
        if self.origin.casefold() == self.destination.casefold():
            raise ValueError("origin and destination must be different")
        if self.return_date is not None and self.return_date < self.departure_date:
            raise ValueError("return must be on or after departure")
        if self.adults + self.children > 9 or self.infants > self.adults:
            raise ValueError("at most nine seated passengers and one infant per adult")
        return self


class HotelSearch(_Search):
    """A stay at a named destination or near coordinates, with dates and room occupancy."""

    destination: Place | None = None
    max_price: PriceLimit | None = Field(default=None, description="Maximum nightly accommodation price.")
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    check_in: SearchDate
    check_out: SearchDate
    rooms: int = Field(default=1, ge=1, le=9, strict=True)
    children_ages: tuple[Annotated[int, Field(ge=0, le=17, strict=True)], ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def valid_stay(self) -> Self:
        """Check a single location, positive stay duration, and at least one adult per room."""
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("coordinates require latitude and longitude")
        if (self.destination is None) == (self.latitude is None):
            raise ValueError("provide either a destination or coordinates")
        if self.check_out <= self.check_in:
            raise ValueError("check-out must follow check-in")
        if self.rooms > self.adults:
            raise ValueError("each room requires an adult")
        return self


class TravelOffer(BaseModel):
    """Reviewed display fields for one quote. Providers validate booking URLs against their own host policies."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
    price: Annotated[Decimal, Field(ge=0, max_digits=15, decimal_places=4, allow_inf_nan=False)] | None = None
    currency: Currency | None = None
    price_basis: PriceBasis = "unknown"
    details: tuple[Annotated[str, StringConstraints(min_length=1, max_length=240)], ...] = Field(
        default=(), max_length=6
    )
    url: Annotated[str, StringConstraints(min_length=1, max_length=8192)] | None = None

    @model_validator(mode="after")
    def priced_in_currency(self) -> Self:
        """Require a currency alongside every displayed amount."""
        if self.price is not None and self.currency is None:
            raise ValueError("an amount requires a currency")
        return self


class TravelReport(BaseModel):
    """Normalized quotes and lookup status. Empty results are valid only for a successful empty search."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: Provider
    status: TravelStatus
    offers: tuple[TravelOffer, ...] = Field(default=(), max_length=MAX_OFFERS)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        """Only successful or partial searches carry offers, and every check has a time zone."""
        if bool(self.offers) != (self.status in ("found", "partial")):
            raise ValueError("offer count and status disagree")
        if self.checked_at.utcoffset() is None:
            raise ValueError("checked_at requires a time zone")
        return self

    def bounded(self) -> Self:
        """Keep the full quote artifact within the per-tool size budget, including its verified booking URLs."""
        report = self
        while len(report.model_dump_json().encode()) > MAX_CONTEXT_BYTES and report.offers:
            remaining = report.offers[:-1]
            report = report.model_copy(
                update={"offers": remaining, "status": "partial" if remaining else "invalid_response"}
            )
        return report

    def model_context(self) -> str:
        """Give the model quote facts. Opaque booking URLs go directly to the visitor in verified cards."""
        return self.model_dump_json(exclude={"offers": {"__all__": {"url"}}})


@dataclass(frozen=True)
class TravelCallRecord:
    """The bounded report used to build the visible quote cards and verify returned links."""

    ms: int
    report: TravelReport

    @property
    def summary(self) -> str:
        """A short status or result count fit for a provider chip or request timeline."""
        if self.report.offers:
            count = len(self.report.offers)
            suffix = " (partial)" if self.report.status == "partial" else ""
            return f"{count} {'option' if count == 1 else 'options'}{suffix}"
        return self.report.status.replace("_", " ")

    @property
    def sources(self) -> tuple[str, ...]:
        """The exact approved URLs in the rendered offers."""
        return tuple(dict.fromkeys(offer.url for offer in self.report.offers if offer.url))
