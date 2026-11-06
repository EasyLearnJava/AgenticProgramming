"""Park trip intake and report. Every search begins with a validated, visitor-submitted same-origin form."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from nimbus.chat import open_lane_tools
from nimbus.constants import ANSWER_TIMEOUT_SECONDS
from nimbus.forms import read_form_fields
from nimbus.lanes import Lane, get_lane, is_open
from nimbus.nps_alerts import PARKS
from nimbus.pages import render_page
from nimbus.parks import Destination
from nimbus.retrieval_gate import RetrievalGate
from nimbus.tools import GET_FORECAST, ForecastInput, ForecastOutput
from nimbus.travel.models import MAX_DAYS_AHEAD
from nimbus.travel.planner import ParkPlan, ParkTrip, make_plan, park_destination
from nimbus.travel.service import TravelService
from nimbus.utils import is_usable_locale, to_browser_locale, to_unit_system

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
    """Render the same form after success or failure; CDN and browser caches must not retain trip details."""
    response = render_page(
        request,
        "park_trip.html",
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
    return _render(request, fields)


async def _forecast(
    request: Request, destination: Destination, days: int, lane: Lane, deadline: float
) -> ForecastOutput:
    """
    Use the selected weather lane, including its normal timeout, cache, telemetry and fallbacks, in the units of the
    browser's first language, as the chat's rule 13 does.
    """
    chat_locale: str = getattr(request.state, "units_locale", "")
    units = to_unit_system(chat_locale or to_browser_locale(request.headers.get("accept-language", "")))
    async with open_lane_tools(request, lane, deadline) as tools:
        params = ForecastInput(
            latitude=destination.latitude,
            longitude=destination.longitude,
            days=days,
            include_hourly=False,
            units=units,
        )
        tool = next(tool for tool in tools if tool.name == GET_FORECAST.name)
        result = await tool.ainvoke(params.model_dump())
        return ForecastOutput.model_validate_json(result)


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
        elif fields.get("transport") == "skip":
            return _render(request, fields, error="Choose flying or driving.", status=400)
        if not state.settings.hotels_enabled:
            # Previously opened forms may still submit a room count after hotels have been switched off.
            fields.pop("rooms", None)
        trip = ParkTrip.model_validate(fields)
        request.state.units_locale = trip.locale if is_usable_locale(trip.locale) else ""
        lane = get_lane(trip.lane)
        if not is_open(lane, state.settings):
            return _render(request, fields, error="The selected weather lane is unavailable.", status=400)
        destination = park_destination(state.park_knowledge, trip)
        now = datetime.now(UTC)
        # With a missing park record, allow a same-day arrival everywhere in the supported mainland US.
        today = (
            now.astimezone(ZoneInfo(destination.time_zone)).date() if destination else (now - timedelta(hours=8)).date()
        )
        if trip.arrival < today:
            return _render(request, fields, error="Choose today or a future date at the park for check-in.", status=400)
        if trip.arrival > today + timedelta(days=MAX_DAYS_AHEAD):
            return _render(request, fields, error="Choose a check-in date within the next year.", status=400)
        flight_query = trip.flight() if trip.transport == "fly" else None
        hotel_query = trip.hotel(destination) if state.settings.hotels_enabled else None
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
