"""Only the surprise-trip sandbox's planner, signed quote actions and explicit confirmation endpoints."""

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError

from nimbus.forms import read_form_fields
from nimbus.pages import render_page
from nimbus.surprise_trip.state import (
    COOKIE,
    LIFETIME,
    MAX_TOKEN,
    TripInput,
    browser_scope,
    date_context,
    new_state,
)
from nimbus.surprise_trip.workflow import SurpriseWorkflow

router = APIRouter()


def runtime(request: Request) -> SurpriseWorkflow:
    """This feature's switch has no effect on the ordinary planner or the original Zion demo."""
    if not request.app.state.settings.surprise_trip_enabled:
        raise HTTPException(404)
    workflow: SurpriseWorkflow = request.app.state.surprise_trip
    return workflow


def bind_browser(response: Response, request: Request, owner: str) -> None:
    """Use a separate HTTP-only browser cookie and keep all receipts out of shared caches and URLs."""
    response.headers["cache-control"] = "no-store"
    response.headers["vary"] = "Cookie"
    response.set_cookie(
        COOKIE,
        owner,
        max_age=LIFETIME,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def seed(request: Request) -> tuple[str, str]:
    """The initial form is not a booking or an inventory request."""
    service = runtime(request)
    owner = browser_scope(request.cookies.get(COOKIE))
    return owner, service.receipts.form(owner)


def _error(detail: str, status: int, code: str = "invalid_request") -> JSONResponse:
    return JSONResponse(
        {"detail": detail, "code": code},
        status_code=status,
        headers={"cache-control": "no-store"},
    )


@router.get("/demo/surprise-trip", response_class=HTMLResponse)
async def planner_page(request: Request) -> HTMLResponse:
    """Display dates and party size; the server never books anything while loading this page."""
    owner, token = seed(request)
    response = render_page(request, "surprise_trip.html", {"seed": token, **date_context()})
    bind_browser(response, request, owner)
    return response


@router.post("/api/surprise-trip/start")
async def start(request: Request) -> JSONResponse:
    """Create an unapproved quote workflow from a valid form. There are no booking calls here."""
    service = runtime(request)
    fields = await read_form_fields(request, max_bytes=4096, max_fields=5)
    if set(fields) != {"action", "token", "checkin", "checkout", "adults"} or fields["action"] != "quote":
        return _error("Use the surprise-trip planner to choose dates and travelers.", 400)
    owner = request.cookies.get(COOKIE, "")
    try:
        service.receipts.check_form(fields["token"], owner)
    except ValueError:
        return _error("This planner expired. Reopen the surprise-trip planner to request a new quote.", 410, "expired")
    try:
        selection = TripInput.model_validate({key: fields[key] for key in ("checkin", "checkout", "adults")})
    except (ValueError, ValidationError):
        return _error("Choose 1 to 6 adults and a future stay of 1 to 14 nights within the next 330 days.", 400)
    try:
        async with service.gate.reserve(owner):
            state = new_state(owner, selection)
            response = JSONResponse(service.remember(state))
    except HTTPException as error:
        return _error(
            "The surprise-trip demo is busy. Wait a minute before requesting another quote.", error.status_code
        )
    bind_browser(response, request, owner)
    return response


@router.post("/api/surprise-trip/advance")
async def advance(request: Request) -> JSONResponse:
    """Only an authenticated confirm action can authorize the quoted flight and hotel."""
    service = runtime(request)
    fields = await read_form_fields(request, max_bytes=MAX_TOKEN * 2, max_fields=2)
    if set(fields) != {"action", "token"} or fields["action"] not in {"advance", "confirm", "recover", "cancel"}:
        return _error("Invalid surprise-trip action.", 400)
    owner = request.cookies.get(COOKIE, "")
    try:
        state = service.receipts.decode(fields["token"], owner)
    except ValueError:
        return _error(
            "This receipt expired or the server restarted. "
            "Saved results are snapshots; do not rebook an uncertain attempt.",
            410,
            "expired",
        )
    service.prune()
    try:
        async with service.gate.reserve(owner):
            if state.id in service.busy:
                return _error(
                    "This surprise trip is still processing. Wait, then refresh the existing attempt.", 409, "busy"
                )
            kept = service.latest.get(state.id)
            if kept is not None and kept.version > state.version:
                # In particular, an old Yes can never approve a replacement quote with a new price.
                response = JSONResponse(service.remember(kept.model_copy(deep=True)))
                bind_browser(response, request, owner)
                return response
            service.busy.add(state.id)
            try:
                state = await service.act(state, fields["action"])
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, str) else "This quote cannot be booked yet."
                return _error(detail, error.status_code, "action_required")
            except Exception as error:
                phase = state.phase
                if phase in {"flight_book", "hotel_book"}:
                    product = state.flight if phase == "flight_book" else state.hotel
                    product.status = "unknown"
                    product.submitted = True
                    product.message = "Confirmation was not received. Refresh this attempt; do not rebook."
                state.phase = "failed"
                state.message = "The surprise-trip step did not finish. Existing submitted bookings can be refreshed."
                state.version += 1
                structlog.get_logger().error("surprise_trip.failed", step=phase, errorClass=type(error).__name__)
            finally:
                service.busy.discard(state.id)
    except HTTPException as error:
        return _error(
            "The surprise-trip demo is busy. Wait a minute, then refresh this attempt.", error.status_code, "busy"
        )
    response = JSONResponse(service.remember(state))
    bind_browser(response, request, owner)
    return response
