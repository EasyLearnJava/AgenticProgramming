"""Short in-chat follow-ups for date and park selection. This endpoint cannot request fares or rooms."""

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from nimbus.chat import open_lane_tools
from nimbus.forms import read_form_fields
from nimbus.nps_alerts import PARKS
from nimbus.pages import render_page
from nimbus.travel import briefing
from nimbus.travel.briefing import BriefPreferences
from nimbus.travel.planner_intake import TripIntent

router = APIRouter()


@router.post("/api/parks/briefing", response_class=HTMLResponse)
async def update_briefing(request: Request) -> HTMLResponse:
    """Only allow structured actions and verified destinations, with the same limits as a paid-search-free chat turn."""
    if not request.app.state.settings.parks_enabled:
        raise HTTPException(404)
    try:
        fields = await read_form_fields(request, max_bytes=4096, max_fields=len(BriefPreferences.model_fields) + 5)
        prefs = BriefPreferences.model_validate_json(fields.pop("prefs", "{}"))
        park = fields.pop("park", "")
        if park not in PARKS:
            raise ValueError("park")
        period = fields.pop("weekend", "")
        dates = period.split("/") if period else [fields.pop("arrival", ""), fields.pop("departure", "")]
        # Only typed preferences may be overridden by the editable form.
        prefs = BriefPreferences.model_validate({**prefs.model_dump(), **fields})
        ZoneInfo(prefs.time_zone)
        if prefs.destination_id and not prefs.destination_id.startswith(park):
            prefs = prefs.model_copy(update={"destination_id": ""})
        if len(dates) != 2:
            raise ValueError("dates")
        arrival, departure = (date.fromisoformat(s).isoformat() for s in dates)
        # An undated form's weekend shortcut introduces the defaults. A dated choice already carries
        # its outbound preference and can intentionally leave the return time unrestricted.
        if period and not prefs.depart_window and not prefs.skip_flights and prefs.transport != "drive":
            prefs = prefs.model_copy(
                update={
                    "depart_window": "evening",
                    "return_window": prefs.return_window or "evening",
                }
            )
        intent = TripIntent(
            kind="briefing",
            fields={"park": park, "arrival": arrival, "departure": departure},
        )
        ctx = await briefing.briefing_context(request, intent, prefs, open_lane_tools, briefing.utc_now())
        response = render_page(request, "brief_content.html", ctx)
        response.headers["x-nimbus-briefing"] = "fragment"
    except (ValueError, ValidationError, ZoneInfoNotFoundError):
        response = HTMLResponse(status_code=400)
    except HTTPException as error:
        response = HTMLResponse(status_code=error.status_code, headers=error.headers)
    response.headers["cache-control"] = "no-store"
    return response
