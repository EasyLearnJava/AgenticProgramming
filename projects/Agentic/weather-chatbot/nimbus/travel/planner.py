"""A confirmed park visit runs five independent checks against the same dates and traveler counts."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Final, Literal, Self
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from nimbus.constants import MAX_FORECAST_DAYS
from nimbus.lanes import LaneId
from nimbus.nps_alerts import PARKS, AlertsReport, NpsAlertsService, ParkId
from nimbus.park_tools import KnowledgeService
from nimbus.parks import Destination, ParkChunk
from nimbus.tools import Day, ForecastOutput
from nimbus.travel.models import FlightSearch, HotelSearch, SearchDate, TravelReport
from nimbus.travel.service import TravelTurn

PlaceText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
type Forecast = Callable[[Destination, int], Awaitable[ForecastOutput]]
GENERAL_GUIDANCE: Final = "visit hiking weather preparation water clothing"


class ParkTrip(BaseModel):
    """Fields that determine the five checks. Validate the complete form before opening any provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    park: ParkId
    lane: LaneId = "rest-no-auth"
    arrival: SearchDate
    departure: SearchDate
    transport: Literal["drive", "fly", "skip"]
    origin: PlaceText = ""
    gateway: PlaceText = ""
    adults: int = Field(ge=1, le=9)
    rooms: int | None = Field(default=None, ge=1, le=9)
    children_ages: tuple[Annotated[int, Field(ge=0, le=17)], ...] = Field(default=(), max_length=8)
    activity: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] = ""
    currency: Literal["USD", "EUR", "GBP", "CAD"] = "USD"

    @field_validator("children_ages", mode="before")
    @classmethod
    def parse_ages(cls, value: object) -> object:
        """Decode the compact HTML field into ages accepted by both providers."""
        if isinstance(value, str):
            return [] if not value.strip() else [piece.strip() for piece in value.split(",")]
        return value

    @model_validator(mode="after")
    def check_itinerary(self) -> Self:
        """Reject reversed dates and ambiguous flight endpoints before any lookups."""
        if self.departure <= self.arrival:
            raise ValueError("Check-out must follow check-in.")
        if self.transport == "fly" and (
            not self.origin or not self.gateway or self.origin.casefold() == self.gateway.casefold()
        ):
            raise ValueError("Enter different departure and arrival cities or airports for the flight.")
        return self

    def flight(self) -> FlightSearch:
        """Map the round trip to explicitly confirmed airports and visitor dates."""
        return FlightSearch(
            origin=self.origin,
            destination=self.gateway,
            departure_date=self.arrival,
            return_date=self.departure,
            adults=self.adults + sum(age >= 12 for age in self.children_ages),
            infants=sum(age < 2 for age in self.children_ages),
            children=sum(2 <= age < 12 for age in self.children_ages),
            currency=self.currency,
        )

    def hotel(self, destination: Destination | None) -> HotelSearch:
        """Use the park reference point where available, independently of its flight gateway."""
        return HotelSearch.model_validate(
            {
                "destination": None if destination else f"{PARKS[self.park][0]} National Park, United States",
                "latitude": destination.latitude if destination else None,
                "longitude": destination.longitude if destination else None,
                "check_in": self.arrival,
                "check_out": self.departure,
                "adults": self.adults,
                "rooms": self.rooms,
                "children_ages": self.children_ages,
                "currency": self.currency,
            }
        )


@dataclass(frozen=True)
class Section[T]:
    """Data from one check, or an explicit reason the check has no data."""

    data: T | None = None
    message: str = ""
    failed: bool = False


@dataclass(frozen=True)
class TripWeather:
    """Only forecast days inside the visit, and their reference point and temperature scale."""

    days: tuple[Day, ...]
    unit: str
    reference: str
    partial: bool


@dataclass(frozen=True)
class ParkPlan:
    """Five independently completed outcomes. No model or generated Markdown controls links or prices."""

    flights: Section[TravelReport]
    hotels: Section[TravelReport]
    weather: Section[TripWeather]
    guidance: Section[tuple[ParkChunk, ...]]
    alerts: Section[AlertsReport]
    checked: datetime
    nights: int


async def _checked[T](call: Awaitable[Section[T]], deadline: float, name: str) -> Section[T]:
    """Keep a single provider failure local to its section and propagate visitor cancellation."""
    try:
        async with asyncio.timeout_at(deadline):
            return await call
    except TimeoutError:
        return Section(message=f"The {name} check timed out.", failed=True)
    except Exception:
        return Section(message=f"The {name} check is unavailable.", failed=True)


def _travel_section(report: TravelReport) -> Section[TravelReport]:
    """Distinguish a provider problem from empty inventory or disabled features in plan telemetry."""
    return Section(report, failed=report.status not in {"found", "no_results", "disabled"})


def park_destination(knowledge: KnowledgeService | None, trip: ParkTrip) -> Destination | None:
    """Resolve a confirmed registry ID before using coordinates or a park timezone."""
    if knowledge is None:
        return None
    try:
        raw = knowledge.resolve(PARKS[trip.park][0]).get("destination")
        if not raw:
            return None
        dest = Destination.model_validate(raw)
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
        return None
    return dest if dest.id == trip.park and dest.park_id == trip.park else None


async def make_plan(
    trip: ParkTrip,
    destination: Destination | None,
    knowledge: KnowledgeService | None,
    alerts: NpsAlertsService,
    travel: TravelTurn,
    forecast: Forecast,
    *,
    flight_query: FlightSearch | None,
    hotel_query: HotelSearch | None,
    now: datetime,
    deadline: float,
) -> ParkPlan:
    """Run the eligible checks concurrently, producing a usable report even if a provider fails."""

    # ① Each service keeps its own cutoff (including provider setup) inside the whole plan's deadline.
    async def flights() -> Section[TravelReport]:
        """Only flying visitors request flights."""
        if trip.transport == "drive":
            return Section(message="Skipped because you selected driving or already there.")
        if flight_query is None:
            return Section(message="Flight search is disabled for this plan.")
        return _travel_section(await travel.search_flights(flight_query))

    async def hotels() -> Section[TravelReport]:
        """Search near the park, even when the gateway is farther away."""
        if hotel_query is None:
            return Section(message="Hotel search is disabled for this plan.")
        return _travel_section(await travel.search_hotels(hotel_query))

    async def weather() -> Section[TripWeather]:
        """Check only trip dates inside the forecast window at the park."""
        if destination is None:
            return Section(message="Park forecast coordinates are unavailable.", failed=True)
        today = now.astimezone(ZoneInfo(destination.time_zone)).date()
        end = min(trip.departure, today + timedelta(days=MAX_FORECAST_DAYS - 1))
        if end < trip.arrival:
            return Section(message=f"Check again within the {MAX_FORECAST_DAYS}-day forecast window.")
        result = await forecast(destination, (end - today).days + 1)
        days = tuple(day for day in result.days if trip.arrival <= date.fromisoformat(day.date) <= end)
        if not days:
            return Section(message="No forecast days were returned for this visit.", failed=True)
        known_days = len({day.date for day in days})
        return Section(
            TripWeather(
                days,
                result.temperature_unit,
                destination.forecast_reference,
                known_days < (trip.departure - trip.arrival).days + 1,
            ),
            failed=known_days < (end - trip.arrival).days + 1,
        )

    async def guidance() -> Section[tuple[ParkChunk, ...]]:
        """Return dated NPS passages scoped to the visitor's selected park and season."""
        if knowledge is None:
            return Section(message="The park guidance index is unavailable.", failed=True)
        queries = dict.fromkeys([trip.activity or GENERAL_GUIDANCE, GENERAL_GUIDANCE])
        for query in queries:
            response = await knowledge.search(trip.park, query, trip.arrival)
            if response.get("status") in {"unsupported", "unavailable"}:
                return Section(message="The park guidance index is unavailable.", failed=True)
            passages = (ParkChunk.model_validate(raw) for raw in response.get("passages", [])[:3])
            scoped = tuple(p for p in passages if p.park_id == trip.park and trip.park in p.destination_ids)
            if scoped:
                fallback = query != (trip.activity or GENERAL_GUIDANCE)
                label = "No passages matched your topic. Showing general park preparation." if fallback else ""
                return Section(scoped, message=label)
        return Section(message="No preparation passages matched the visit.")

    async def notices() -> Section[AlertsReport]:
        """Always check today's official notices for the selected park."""
        report = await alerts.get(trip.park, tool="park_trip_plan")
        return Section(report, failed=not report.complete and report.status != "not_configured")

    # ② Parallel calls finish independently. The outer task group also closes on visitor cancellation.
    async with asyncio.TaskGroup() as group:
        air = group.create_task(_checked(flights(), deadline, "flight"))
        stay = group.create_task(_checked(hotels(), deadline, "hotel"))
        sky = group.create_task(_checked(weather(), deadline, "weather"))
        advice = group.create_task(_checked(guidance(), deadline, "park guidance"))
        nps = group.create_task(_checked(notices(), deadline, "NPS notices"))
    plan = ParkPlan(
        air.result(),
        stay.result(),
        sky.result(),
        advice.result(),
        nps.result(),
        now,
        (trip.departure - trip.arrival).days,
    )
    missing = (
        (
            flight_query is not None
            and (not plan.flights.data or plan.flights.data.status not in {"found", "no_results"})
        ),
        hotel_query is not None and (not plan.hotels.data or plan.hotels.data.status not in {"found", "no_results"}),
        not plan.weather.data or plan.weather.data.partial,
        not plan.guidance.data,
        not plan.alerts.data or not plan.alerts.data.complete,
    )
    structlog.get_logger().info(
        "travel.plan",
        tool="park_trip_plan",
        status="partial" if any(missing) else "ok",
        missingSections=sum(missing),
        failedSections=sum(
            section.failed for section in (plan.flights, plan.hotels, plan.weather, plan.guidance, plan.alerts)
        ),
    )
    return plan
