"""Private preference management: explicit, bounded same-origin forms and honest provider outcomes."""

import time
from dataclasses import replace

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from nimbus.forms import read_form_fields
from nimbus.memory.client import Mem0Service
from nimbus.memory.context import configured, load_memory
from nimbus.memory.identity import (
    COOKIE,
    COOKIE_SECONDS,
    BrowserIdentity,
    form_token,
    new_identity,
    read_identity,
    set_identity,
    valid_form_token,
)
from nimbus.memory.models import PreferenceProfile, Snapshot
from nimbus.pages import render_page
from nimbus.utils import is_same_origin

router = APIRouter()


def private_headers[T: Response](response: T) -> T:
    """Personal content stays out of browser, CDN and shared caches."""
    response.headers.update({"cache-control": "no-store", "vary": "Cookie"})
    return response


def view_context(request: Request, identity: BrowserIdentity | None, snapshot: Snapshot) -> dict[str, object]:
    """Only public form fields and a scoped token reach the browser; provider IDs never do."""
    return {
        "preferences": snapshot.preferences,
        "configured": configured(request),
        "enabled": bool(identity and identity.mode == "active"),
        "has_identity": identity is not None,
        "deleting": bool(identity and identity.mode == "deleting"),
        "snapshot_status": snapshot.status,
        "revision": snapshot.revision,
        "token": form_token(request, identity),
        "message": "",
        "error": "",
    }


def _render(
    request: Request,
    identity: BrowserIdentity | None,
    snapshot: Snapshot,
    *,
    message: str = "",
    error: str = "",
    status: int = 200,
) -> HTMLResponse:
    """Render management without provider exceptions, IDs or private values in an address."""
    return private_headers(
        render_page(
            request,
            "preferences.html",
            {
                **view_context(request, identity, snapshot),
                "message": message,
                "error": error,
                "menu_path": "/preferences",
            },
            status_code=status,
        )
    )


@router.get("/preferences", response_class=HTMLResponse)
async def preferences_page(request: Request) -> HTMLResponse:
    """Viewing does not opt in or create a profile."""
    context = await load_memory(request, include_paused=True)
    error = ""
    if context.snapshot.status in {"unavailable", "pending"}:
        error = "Saved preferences could not be read. Nimbus will continue without them; try again shortly."
    elif context.snapshot.status == "conflict":
        error = "Conflicting saved preferences need review. Forget them here, then save the choices you want."
    if context.identity and context.identity.mode == "deleting":
        error = "Preference use is off. Deletion is not yet confirmed; choose Forget preferences to retry."
    return _render(request, context.identity, context.snapshot, error=error)


@router.post("/api/preferences/action", response_class=HTMLResponse)
async def preference_action(request: Request) -> Response:
    """Only an authenticated browser form may save, pause, resume or delete its own preference scope."""
    identity = read_identity(request)
    snapshot = Snapshot(status="empty")
    response: Response
    if not configured(request):
        return _render(
            request, identity, snapshot, error="Preference memory is not configured on this deployment.", status=503
        )
    try:
        # ① Origin and scoped form token are checked before any third-party operation.
        if not request.headers.get("origin") or not is_same_origin(request.headers["origin"], str(request.url)):
            raise HTTPException(403)
        fields = await read_form_fields(request, max_bytes=4096, max_fields=10)
        if not valid_form_token(request, fields.pop("_token", ""), identity):
            raise HTTPException(403)
        action = fields.pop("action", "")
        revision = fields.pop("revision", "")
        service: Mem0Service = request.app.state.mem0
        caller = request.client.host if request.client else "unknown"
        if action == "save":
            if fields.pop("consent", "") != "yes" or (identity and identity.mode == "deleting"):
                raise HTTPException(400)
            profile = PreferenceProfile.model_validate(fields)
            async with request.app.state.memory_gate.reserve(caller):
                identity = identity or new_identity()
                snapshot = await service.save(identity.user_id, profile, revision)
            confirmed = snapshot.status == "ready" and snapshot.preferences == profile
            # An uncertain initial write keeps its scope for retry/deletion but does not activate memory use.
            identity = replace(
                identity, mode="active" if confirmed else "paused", expires=int(time.time()) + COOKIE_SECONDS
            )
            error = (
                ""
                if confirmed
                else (
                    "Preferences changed in another tab or contain a conflict. Refresh to review before saving again."
                    if snapshot.status == "conflict"
                    else "Saving is not confirmed. Preference use is paused; refresh to check or retry."
                )
            )
            response = (
                private_headers(RedirectResponse("/preferences", status_code=303))
                if confirmed
                else _render(request, identity, snapshot, error=error, status=409)
            )
            set_identity(response, request, identity)
            return response
        if fields or identity is None or action not in {"pause", "resume", "forget"}:
            raise HTTPException(400)
        if action == "pause":
            response = private_headers(RedirectResponse("/preferences", status_code=303))
            set_identity(
                response, request, replace(identity, mode="deleting" if identity.mode == "deleting" else "paused")
            )
            structlog.get_logger().info(
                "memory.operation", tool="memory_preferences", action=action, status="ready", ms=0
            )
            return response
        # ② Pausing is immediate and local; deletion keeps the credential until the remote outcome is confirmed.
        if action == "forget":
            identity = replace(identity, mode="deleting")
            async with request.app.state.memory_gate.reserve(caller):
                forgotten = await service.forget(identity.user_id)
            if forgotten:
                response = private_headers(RedirectResponse("/preferences", status_code=303))
                response.delete_cookie(
                    COOKIE, path="/", secure=request.url.scheme == "https", httponly=True, samesite="strict"
                )
                return response
            response = _render(
                request,
                identity,
                Snapshot(status="unavailable"),
                status=503,
                error="Preference use is off, but deletion is not confirmed. Retry Forget preferences.",
            )
            set_identity(response, request, identity)
            return response
        if action == "resume" and identity.mode == "deleting":
            raise HTTPException(400)
        if action == "resume":
            async with request.app.state.memory_gate.reserve(caller):
                snapshot = await service.read(identity.user_id)
            if snapshot.status != "ready":
                identity = replace(identity, mode="paused")
                response = _render(
                    request,
                    identity,
                    snapshot,
                    error="Preferences could not be verified. They remain paused.",
                    status=409,
                )
                set_identity(response, request, identity)
                return response
        identity = replace(identity, mode="active")
        response = private_headers(RedirectResponse("/preferences", status_code=303))
        set_identity(response, request, identity)
        structlog.get_logger().info("memory.operation", tool="memory_preferences", action=action, status="ready", ms=0)
        return response
    except ValidationError:
        return _render(request, identity, snapshot, error="Check the airport code and preference choices.", status=400)
    except HTTPException as error:
        message = (
            "Memory is busy. Please wait a minute and try again."
            if error.status_code == 429
            else ("This form could not be accepted. Open My preferences and try again.")
        )
        response = _render(request, identity, snapshot, error=message, status=error.status_code)
        if identity and identity.mode == "deleting":
            set_identity(response, request, identity)
        response.headers.update(error.headers or {})
        return response
