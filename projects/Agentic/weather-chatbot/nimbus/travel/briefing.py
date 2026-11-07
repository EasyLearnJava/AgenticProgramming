"""Render a dated park briefing before any travel search. The browser carries editable details in POST bodies."""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, cast
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, Request
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from nimbus.constants import ANSWER_TIMEOUT_SECONDS
from nimbus.lanes import Lane, LaneId, get_lane, is_open
from nimbus.nps_alerts import PARKS, ParkId
from nimbus.parks import Destination
from nimbus.tools import ForecastOutput
from nimbus.travel.airports import AIRPORT_ZONES, normalize_origin
from nimbus.travel.conditions import check_conditions, verified_reference
from nimbus.travel.models import MAX_DAYS_AHEAD, MAX_STAY_NIGHTS, FlightWindow, ReturnWindow
from nimbus.travel.park_forecast import park_forecast
from nimbus.travel.planner_intake import TripIntent
from nimbus.travel.weekend_dates import visit_dates
from nimbus.utils import is_usable_locale, new_turn_id, to_currency

type OpenTools = Callable[[Request, Lane, float], AbstractAsyncContextManager[list[StructuredTool]]]
type ShortText = Annotated[str, StringConstraints(max_length=100)]


def utc_now() -> datetime:
    """One replaceable clock for relative date interpretation and conditions checks."""
    return datetime.now(UTC)


class BriefPreferences(BaseModel):
    """Bounded facts carried through a park or date choice; each quote has its own stricter validation."""

    model_config = ConfigDict(extra="forbid")
    lane: LaneId = "rest-no-auth"
    locale: ShortText = "en-US"
    time_zone: ShortText = "America/Chicago"
    origin: ShortText = ""
    gateway: ShortText = ""
    transport: Literal["", "drive", "fly", "skip"] = ""
    adults: Annotated[int, Field(ge=1, le=9)] = 1
    rooms: Annotated[int, Field(ge=1, le=9)] = 1
    activity: Annotated[str, StringConstraints(max_length=160)] = ""
    children_ages: Annotated[str, StringConstraints(max_length=24)] = ""
    currency: Literal["USD", "CAD", "GBP", "EUR"] = "USD"
    destination_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{0,100}$")] = ""
    depart_window: FlightWindow = ""
    return_window: ReturnWindow = ""
    skip_flights: bool = False
    skip_hotels: bool = False

    @classmethod
    def from_intent(cls, intent: TripIntent, locale: str, lane: Lane, zone: str) -> "BriefPreferences":
        fields = {k: v for k, v in intent.fields.items() if k in cls.model_fields}
        fields.update(
            locale=locale,
            time_zone=intent.origin_zone or zone,
            currency=fields.get("currency", to_currency(locale)),
            lane=lane.id,
        )
        return cls.model_validate(
            {
                **fields,
                "destination_id": intent.destination_id,
                "depart_window": intent.depart_window,
                "return_window": intent.return_window,
                "skip_flights": intent.skip_flights,
                "skip_hotels": intent.skip_hotels,
            }
        )


async def briefing_context(
    request: Request,
    intent: TripIntent,
    prefs: BriefPreferences,
    open_tools: OpenTools,
    now: datetime,
    turn_id: str = "",
) -> dict[str, Any]:
    """Check only the supported public place. Dates and fares never leave Nimbus for the warning checks."""
    state = request.app.state
    if airport_zone := AIRPORT_ZONES.get(normalize_origin(prefs.origin)):
        prefs = prefs.model_copy(update={"time_zone": airport_zone})
    fields = dict(intent.fields)
    fields.update(
        {
            k: str(v).lower() if isinstance(v, bool) else str(v)
            for k, v in prefs.model_dump(exclude={"time_zone", "destination_id"}).items()
            if v
        }
    )
    park = fields.get("park", "")
    ctx: dict[str, Any] = {
        "fields": fields,
        "kind": intent.kind,
        "turn_id": turn_id or new_turn_id(),
        "prefs": prefs,
        "preference_json": prefs.model_dump_json(exclude_defaults=True),
        "park_name": PARKS[park][0] if park in PARKS else "",
        "parks": PARKS,
        "options": [],
        "candidates": intent.candidate_parks,
        "flights_enabled": state.settings.flights_enabled,
        "hotels_enabled": state.settings.hotels_enabled,
    }
    lane = get_lane(prefs.lane)
    if not is_open(lane, state.settings):
        ctx["error"] = "The selected weather connection is unavailable. Start a new trip request."
        return ctx
    if intent.kind in {"form", "choose_weekend", "choose_park"}:
        if intent.weekend_options:
            ctx["options"] = [
                (a, b, "Rest of this weekend" if i == 0 and len(intent.weekend_options) > 1 else "Following weekend")
                for i, (a, b) in enumerate(intent.weekend_options)
            ]
        elif park:
            for text, label in (("this weekend", "This weekend"), ("next weekend", "Next weekend")):
                period = visit_dates(text, now, prefs.time_zone)
                if period.interval:
                    ctx["options"].append((*period.interval, label))
                elif text == "this weekend" and len(period.options) > 1:
                    ctx["options"].append((*period.options[0], "Rest of this weekend"))
        return ctx
    if intent.kind != "briefing" or park not in PARKS:
        return ctx
    arrival, departure = date.fromisoformat(fields["arrival"]), date.fromisoformat(fields["departure"])
    park_id = cast(ParkId, park)  # Membership in the reviewed park registry was checked above.
    point = verified_reference(state.park_knowledge, park_id, prefs.destination_id)
    park_today = now.astimezone(ZoneInfo(point.time_zone if point else prefs.time_zone)).date()
    today = now.astimezone(ZoneInfo(prefs.time_zone)).date() if prefs.origin else park_today
    park_start = max(arrival, park_today)
    if not (
        today <= arrival <= today + timedelta(days=MAX_DAYS_AHEAD)
        and departure >= park_start
        and 0 < (departure - arrival).days <= MAX_STAY_NIGHTS
    ):
        ctx.update(error="Choose a future stay or one beginning today, up to 30 nights and within the next year.")
        return ctx
    ctx.update(
        arrival=arrival, departure=departure, nights=(departure - arrival).days, point=point, hotel_arrival=park_start
    )
    try:
        async with state.planner_gate.reserve(request.client.host if request.client else "unknown"):
            deadline = asyncio.get_running_loop().time() + ANSWER_TIMEOUT_SECONDS

            async def forecast(destination: Destination, days: int) -> ForecastOutput:
                locale = prefs.locale if is_usable_locale(prefs.locale) else "en-US"
                return await park_forecast(destination, days, locale, open_tools(request, lane, deadline))

            conditions = await check_conditions(
                park=park_id,
                arrival=park_start,
                departure=departure,
                activity=prefs.activity,
                destination=point,
                knowledge=state.park_knowledge,
                alerts=state.nps_alerts,
                nws=state.nws_alerts,
                forecast=forecast,
                now=now,
                deadline=deadline,
            )
            ctx["conditions"] = conditions
            sections = (conditions.weather, conditions.guidance, conditions.alerts, conditions.warnings)
            missing = (
                not conditions.weather.data or conditions.weather.data.partial,
                not conditions.guidance.data,
                not conditions.alerts.data or not conditions.alerts.data.complete,
                not conditions.warnings.data or not conditions.warnings.data.complete,
            )
            structlog.get_logger().info(
                "travel.briefing",
                tool="park_trip_briefing",
                status=conditions.decision,
                failedSections=sum(section.failed for section in sections),
                missingSections=sum(missing),
            )
    except HTTPException as error:
        if error.status_code != 429:
            raise
        ctx["error"] = "Trip checks are busy. Wait a minute and try these dates again."
    return ctx
