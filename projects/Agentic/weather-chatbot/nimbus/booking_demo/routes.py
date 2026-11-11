"""Dedicated sandbox-only endpoints; never expose a general booking proxy or account-wide booking list."""

from datetime import UTC, date, datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from nimbus.booking_demo.state import CHICAGO, COOKIE, LIFETIME, MAX_TOKEN, DemoState, browser_scope, new_state
from nimbus.booking_demo.workflow import DemoWorkflow
from nimbus.forms import read_form_fields
from nimbus.pages import render_page

router = APIRouter()


def runtime(request: Request) -> DemoWorkflow:
    """Disabling the demo removes all its routes without changing production trip search."""
    if not request.app.state.settings.booking_demo_enabled:
        raise HTTPException(404)
    workflow: DemoWorkflow = request.app.state.booking_demo
    return workflow


def bind_browser(response: Response, request: Request, owner: str) -> None:
    """A dedicated cookie binds signed receipts to this browser; no query-string identifiers or credentials."""
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


def seed(request: Request) -> tuple[DemoState, str]:
    """Prepare an authenticated workflow only. No inventory is searched or booked on a GET."""
    service = runtime(request)
    owner = browser_scope(request.cookies.get(COOKIE))
    state = new_state(owner)
    return state, service.receipts.encode(state)


@router.get("/demo/bookings", response_class=HTMLResponse)
async def bookings_page(request: Request) -> HTMLResponse:
    """Show the current tab's stored demo receipt; a deliberate button starts another simulation."""
    runtime(request)
    owner = browser_scope(request.cookies.get(COOKIE))
    response = render_page(request, "booking_demo.html", {})
    bind_browser(response, request, owner)
    return response


@router.post("/api/booking-demo/start")
async def start(request: Request) -> JSONResponse:
    """Start a new, browser-bound synthetic trip, without making a provider call."""
    service = runtime(request)
    fields = await read_form_fields(request, max_bytes=64, max_fields=1)
    if fields != {"action": "start"}:
        raise HTTPException(400, "Use the demo booking button")
    state, _ = seed(request)
    async with service.gate.reserve(state.owner):
        response = JSONResponse(service.remember(state))
    bind_browser(response, request, state.owner)
    return response


@router.post("/api/booking-demo/advance")
async def advance(request: Request) -> JSONResponse:
    """Advance or recover only a signed receipt from this browser; one bounded provider step per request."""
    service = runtime(request)
    fields = await read_form_fields(request, max_bytes=MAX_TOKEN * 2, max_fields=2)
    if set(fields) != {"token", "action"} or fields["action"] not in {"advance", "recover"}:
        raise HTTPException(400, "Invalid demo action")
    try:
        owner = request.cookies.get(COOKIE, "")
        if not owner:
            raise ValueError("Missing browser")
        state = service.receipts.decode(fields["token"], owner)
    except ValueError:
        return JSONResponse(
            {
                "detail": "This demo receipt expired or this server restarted. Saved cards remain a snapshot, "
                "not current confirmation. Do not start another booking to retry an uncertain one."
            },
            status_code=410,
            headers={"cache-control": "no-store"},
        )
    service.prune()
    if fields["action"] == "advance" and state.flight_destination != "SGU":
        return JSONResponse(
            {
                "detail": "The demo now uses St. George (SGU). Older attempts can only be refreshed. "
                "Start a new demo for DFW to SGU.",
                "code": "route_changed",
            },
            status_code=409,
            headers={"cache-control": "no-store"},
        )
    kept = service.latest.get(state.id)
    if kept is not None and kept.version > state.version:
        state = kept.model_copy(deep=True)
        if fields["action"] == "advance":
            return JSONResponse(service.remember(state), headers={"cache-control": "no-store"})
    if (
        fields["action"] == "advance"
        and date.fromisoformat(state.checkin) < datetime.now(UTC).astimezone(CHICAGO).date()
    ):
        return JSONResponse(
            {"detail": "These departure dates have passed. Existing bookings can still be refreshed."},
            status_code=409,
            headers={"cache-control": "no-store"},
        )
    try:
        async with service.gate.reserve(state.owner):
            if state.id in service.busy:
                raise HTTPException(409, "This demo is still processing. Wait, then refresh its status.")
            service.busy.add(state.id)
            try:
                state = await service.recover(state) if fields["action"] == "recover" else await service.advance(state)
            except Exception as error:
                # A programming or malformed-response fault must not turn an uncertain booking into a retry.
                product = state.flight if state.next_phase.startswith("flight_") else state.hotel
                product.status = "unknown" if state.next_phase.endswith("_book") else "unavailable"
                product.message = "This step could not finish. Any uncertain booking must be refreshed, not rebooked."
                state.next_phase = "hotel_search" if state.next_phase.startswith("flight_") else "done"
                state.version += 1
                structlog.get_logger().error("booking_demo.failed", errorClass=type(error).__name__)
            finally:
                service.busy.discard(state.id)
    except HTTPException as error:
        return JSONResponse(
            {"detail": "The booking demo is busy. Wait a minute, then refresh the current attempt."},
            status_code=error.status_code,
            headers={"cache-control": "no-store", **(error.headers or {})},
        )
    response = JSONResponse(service.remember(state))
    bind_browser(response, request, state.owner)
    return response
