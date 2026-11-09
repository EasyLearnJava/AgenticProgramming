"""Park trip intake and report. Every search begins with a validated, visitor-submitted same-origin form."""

import asyncio
from collections.abc import Mapping
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from nimbus.chat import TIME_ZONES, open_lane_tools
from nimbus.constants import ANSWER_TIMEOUT_SECONDS
from nimbus.forms import read_form_fields
from nimbus.lanes import Lane, get_lane, is_open
from nimbus.memory.context import load_memory
from nimbus.nps_alerts import PARKS
from nimbus.pages import render_page
from nimbus.parks import Destination
from nimbus.retrieval_gate import RetrievalGate
from nimbus.tools import ForecastOutput
from nimbus.travel import briefing
from nimbus.travel.airports import AIRPORT_ZONES, normalize_origin
from nimbus.travel.models import MAX_DAYS_AHEAD
from nimbus.travel.park_forecast import park_forecast
from nimbus.travel.planner import ParkPlan, ParkTrip, make_plan, park_destination
from nimbus.travel.preferences import prefill_preferences
from nimbus.travel.service import TravelService
from nimbus.utils import is_usable_locale, to_browser_locale

router = APIRouter()
FORM_ERRORS = {
    400: "Please check the trip dates, park, airports, rooms and traveler counts.",
    403: "Submit the trip form from this site.",
    413: "The trip details exceed the form size limit.",
    415: "Submit the park trip form.",
    429: "Trip planning is busy. Please wait and try again.",
}


def _render(
    request: Request, fields: Mapping[str, str], plan: ParkPlan | None = None, error: str = "", status: int = 200
) -> HTMLResponse:
    """Return a report for chat or a full planner page for navigation, keeping trip details out of caches."""
    inline = request.method == "POST" and request.headers.get("hx-request") == "true"
    response = render_page(
        request,
        "trip_report.html" if inline else "park_trip.html",
        {
            "fields": fields,
            "flights_enabled": request.app.state.settings.flights_enabled,
            "hotels_enabled": request.app.state.settings.hotels_enabled,
            "plan": plan,
            "error": error,
            "menu_path": "/parks/trip",
            "park_name": PARKS.get(fields.get("park", ""), ("",))[0],
        },
        status_code=status,
    )
    response.headers["cache-control"] = "no-store"
    if inline:
        response.headers["x-nimbus-trip"] = "fragment"
    return response


def _check_enabled(request: Request) -> None:
    """The planner is available where park preparation and at least one travel provider are enabled."""
    settings = request.app.state.settings
    if not settings.parks_enabled or not (settings.flights_enabled or settings.hotels_enabled):
        raise HTTPException(404)


@router.get("/parks/trip", response_class=HTMLResponse)
async def planner_page(request: Request) -> HTMLResponse:
    """Display trip intake. Only a reviewed park ID may preselect the public form."""
    _check_enabled(request)
    fields = dict(request.query_params)
    if fields and (
        list(request.query_params.keys()) != ["park"]
        or len(request.query_params.multi_items()) != 1
        or fields["park"] not in PARKS
    ):
        return _render(request, {}, error="Choose a supported park using the form.", status=400)
    memory = await load_memory(request)
    return _render(request, prefill_preferences(fields, memory.preferences))


async def _forecast(
    request: Request, destination: Destination, days: int, lane: Lane, deadline: float
) -> ForecastOutput:
    """Use the chosen units, with the browser locale as fallback, through the normal weather lane protections."""
    chat_locale: str = getattr(request.state, "units_locale", "")
    locale = chat_locale or to_browser_locale(request.headers.get("accept-language", ""))
    return await park_forecast(
        destination,
        days,
        locale,
        open_lane_tools(request, lane, deadline),
        unit_system=getattr(request.state, "unit_system", ""),
    )


@router.post("/api/parks/trip", response_class=HTMLResponse)
async def build_trip(request: Request) -> HTMLResponse:
    """Run the confirmed plan under the edge and local request gates, keeping errors on the form."""
    _check_enabled(request)
    state = request.app.state
    fields: dict[str, str] = {}
    try:
        # ① Validate the whole trip, including both providers' constraints, before spending upstream quota.
        fields = await read_form_fields(request, max_bytes=4096, max_fields=len(ParkTrip.model_fields))
        if not state.settings.flights_enabled:
            fields["transport"] = "skip"
        elif fields.get("skip_flights") == "true":
            if fields.get("transport") != "drive":
                fields["transport"] = "skip"
        elif fields.get("transport") == "skip":
            return _render(request, fields, error="Choose flying or driving.", status=400)
        if not state.settings.hotels_enabled:
            # Previously opened forms may still submit a room count after hotels have been switched off.
            fields.pop("rooms", None)
        trip = ParkTrip.model_validate(fields)
        request.state.units_locale = trip.locale if is_usable_locale(trip.locale) else ""
        request.state.unit_system = trip.unit_system
        lane = get_lane(trip.lane)
        if not is_open(lane, state.settings):
            return _render(request, fields, error="The selected weather lane is unavailable.", status=400)
        destination = park_destination(state.park_knowledge, trip)
        now = briefing.utc_now()
        # With a missing park record, allow a same-day arrival everywhere in the supported mainland US.
        park_today = (
            now.astimezone(ZoneInfo(destination.time_zone)).date() if destination else (now - timedelta(hours=8)).date()
        )
        if trip.time_zone and trip.time_zone not in TIME_ZONES:
            return _render(request, fields, error="Choose a valid time zone for the trip.", status=400)
        origin_zone = (
            (AIRPORT_ZONES.get(normalize_origin(trip.origin)) or trip.time_zone) if trip.transport == "fly" else None
        )
        today = now.astimezone(ZoneInfo(origin_zone)).date() if origin_zone else park_today
        if trip.arrival < today:
            return _render(request, fields, error="Choose today or a future date to begin the trip.", status=400)
        if trip.arrival > today + timedelta(days=MAX_DAYS_AHEAD):
            return _render(request, fields, error="Choose a check-in date within the next year.", status=400)
        flight_query = trip.flight() if trip.transport == "fly" and not trip.skip_flights else None
        check_in = max(trip.arrival, park_today)
        if check_in != trip.arrival:
            fields["hotel_check_in"] = check_in.isoformat()
        hotel_query = (
            trip.hotel(destination, check_in=check_in)
            if state.settings.hotels_enabled and not trip.skip_hotels and check_in < trip.departure
            else None
        )
        gate: RetrievalGate = state.planner_gate
        async with gate.reserve(request.client.host if request.client else "unknown"):
            # ② The same deadline and turn budget cover every travel request.
            deadline = asyncio.get_running_loop().time() + ANSWER_TIMEOUT_SECONDS
            service: TravelService = state.travel_service

            async def forecast(point: Destination, days: int) -> ForecastOutput:
                """Get a forecast using the app's injected HTTP and cache dependencies."""
                return await _forecast(request, point, days, lane, deadline)

            plan = await make_plan(
                trip,
                destination,
                state.park_knowledge,
                state.nps_alerts,
                service.new_turn(deadline, today=today),
                forecast,
                park_start=check_in,
                flight_query=flight_query,
                hotel_query=hotel_query,
                now=now,
                deadline=deadline,
            )
        return _render(request, fields, plan)
    except ValidationError as error:
        first = error.errors(include_input=False, include_url=False)[0]
        message = (
            str(first["msg"]).removeprefix("Value error, ") if first["type"] == "value_error" else FORM_ERRORS[400]
        )
        return _render(request, fields, error=message, status=400)
    except HTTPException as error:
        response = _render(
            request, fields, error=FORM_ERRORS.get(error.status_code, FORM_ERRORS[400]), status=error.status_code
        )
        response.headers.update(error.headers or {})
        return response
