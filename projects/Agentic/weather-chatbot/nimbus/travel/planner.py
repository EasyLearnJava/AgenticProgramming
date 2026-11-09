"""A confirmed park visit runs five independent checks against the same dates and traveler counts."""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Literal, Self

import structlog
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from nimbus.lanes import LaneId
from nimbus.nps_alerts import PARKS, AlertsReport, NpsAlertsService, ParkId
from nimbus.park_tools import KnowledgeService
from nimbus.parks import Destination, ParkChunk
from nimbus.travel.conditions import (
    GENERAL_GUIDANCE as GENERAL_GUIDANCE,
)
from nimbus.travel.conditions import (
    Forecast,
    Section,
    TripWeather,
    checked,
    park_notices,
    preparation,
    verified_reference,
    visit_weather,
)
from nimbus.travel.models import (
    MAX_STAY_NIGHTS,
    FlightSearch,
    FlightWindow,
    HotelSearch,
    ReturnWindow,
    SearchDate,
    TravelReport,
)
from nimbus.travel.service import TravelTurn

PlaceText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


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
    depart_window: FlightWindow = ""
    return_window: ReturnWindow = ""
    skip_flights: bool = False
    skip_hotels: bool = False
    adults: int = Field(ge=1, le=9)
    rooms: int | None = Field(default=None, ge=1, le=9)
    children_ages: tuple[Annotated[int, Field(ge=0, le=17)], ...] = Field(default=(), max_length=8)
    activity: Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)] = ""
    currency: Literal["USD", "EUR", "GBP", "CAD"] = "USD"
    # The chat's locale, when the form came from the chat: the plan's units then match the chat's.
    locale: Annotated[str, StringConstraints(max_length=35)] = ""
    unit_system: Literal["", "metric", "imperial"] = ""
    time_zone: Annotated[str, StringConstraints(max_length=100)] = ""

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
        if (self.departure - self.arrival).days > MAX_STAY_NIGHTS:
            raise ValueError(f"Choose a stay of at most {MAX_STAY_NIGHTS} nights.")
        if (
            self.transport == "fly"
            and not self.skip_flights
            and (not self.origin or not self.gateway or self.origin.casefold() == self.gateway.casefold())
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
            depart_window=self.depart_window,
            return_window=self.return_window,
            adults=self.adults + sum(age >= 12 for age in self.children_ages),
            infants=sum(age < 2 for age in self.children_ages),
            children=sum(2 <= age < 12 for age in self.children_ages),
            currency=self.currency,
        )

    def hotel(self, destination: Destination | None, *, check_in: date | None = None) -> HotelSearch:
        """Use the park reference point where available, independently of its flight gateway."""
        return HotelSearch.model_validate(
            {
                "destination": None if destination else f"{PARKS[self.park][0]} National Park, United States",
                "latitude": destination.latitude if destination else None,
                "longitude": destination.longitude if destination else None,
                "check_in": check_in or self.arrival,
                "check_out": self.departure,
                "adults": self.adults,
                "rooms": self.rooms,
                "children_ages": self.children_ages,
                "currency": self.currency,
            }
        )


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


def _travel_section(report: TravelReport) -> Section[TravelReport]:
    """Distinguish a provider problem from empty inventory or disabled features in plan telemetry."""
    return Section(report, failed=report.status not in {"found", "partial", "no_results", "disabled"})


def park_destination(knowledge: KnowledgeService | None, trip: ParkTrip) -> Destination | None:
    """Resolve a confirmed registry ID before using coordinates or a park timezone."""
    return verified_reference(knowledge, trip.park)


async def make_plan(
    trip: ParkTrip,
    destination: Destination | None,
    knowledge: KnowledgeService | None,
    alerts: NpsAlertsService,
    travel: TravelTurn,
    forecast: Forecast,
    *,
    park_start: date,
    flight_query: FlightSearch | None,
    hotel_query: HotelSearch | None,
    now: datetime,
    deadline: float,
) -> ParkPlan:
    """Run the eligible checks concurrently, producing a usable report even if a provider fails."""

    # ① Each service keeps its own cutoff (including provider setup) inside the whole plan's deadline.
    async def flights() -> Section[TravelReport]:
        """Only flying visitors request flights."""
        if trip.skip_flights:
            return Section(message="Skipped at your request.")
        if trip.transport == "drive":
            return Section(message="Skipped because you selected driving or already there.")
        if flight_query is None:
            return Section(message="Flight search is disabled for this plan.")
        return _travel_section(await travel.search_flights(flight_query))

    async def hotels() -> Section[TravelReport]:
        """Search near the park, even when the gateway is farther away."""
        if trip.skip_hotels:
            return Section(message="Skipped at your request.")
        if park_start >= trip.departure:
            return Section(message="There are no remaining overnight stays at the park for these dates.")
        if hotel_query is None:
            return Section(message="Hotel search is disabled for this plan.")
        return _travel_section(await travel.search_hotels(hotel_query))

    # ② Parallel calls finish independently. The outer task group also closes on visitor cancellation.
    async with asyncio.TaskGroup() as group:
        air = group.create_task(checked(flights(), deadline, "flight"))
        stay = group.create_task(checked(hotels(), deadline, "hotel"))
        sky = group.create_task(
            checked(visit_weather(destination, park_start, trip.departure, forecast, now), deadline, "weather")
        )
        advice = group.create_task(
            checked(preparation(knowledge, trip.park, trip.park, trip.activity, park_start), deadline, "park guidance")
        )
        nps = group.create_task(checked(park_notices(trip.park, alerts), deadline, "NPS notices"))
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
