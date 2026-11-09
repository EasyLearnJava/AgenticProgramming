"""A private weather-cache inventory: normalized labels and freshness, never a shared conversation browser."""

import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from nimbus.pages import render_page
from nimbus.semantic_cache.identity import read_scope
from nimbus.semantic_cache.models import CacheEntry, CacheListing

router = APIRouter()
MAX_VISIBLE_ENTRIES = 50


class CacheInventory(Protocol):
    """Only the cache service's read-only inventory surface is available to this page."""

    configured: bool
    mode: str

    async def list_entries(self, scope: str) -> CacheListing:
        """Return a bounded inventory belonging to one verified browser scope."""


@dataclass(frozen=True)
class CacheRow:
    """Safe display metadata, with no answer, query, identifier, vector or credential."""

    label: str
    remaining_seconds: int
    age_seconds: int
    evidence_age_seconds: int
    expires_iso: str
    expires_label: str


def to_cache_rows(entries: tuple[CacheEntry, ...], now: float) -> tuple[CacheRow, ...]:
    """Recheck freshness at rendering time and cap the list even if a provider returned extra records."""
    rows = []
    # ① An expired, future-dated or malformed timestamp cannot claim that an answer is reusable.
    for entry in sorted(entries, key=lambda item: item.created_at, reverse=True):
        stamps = (entry.created_at, entry.expires_at, entry.evidence_fetched_at)
        if not all(math.isfinite(stamp) for stamp in stamps):
            continue
        if entry.created_at > now or entry.evidence_fetched_at > now or entry.expires_at <= now:
            continue
        try:
            expires = datetime.fromtimestamp(entry.expires_at, UTC)
        except (ValueError, OverflowError, OSError):
            continue
        rows.append(
            CacheRow(
                label=entry.label,
                remaining_seconds=max(0, math.ceil(entry.expires_at - now)),
                age_seconds=max(0, int(now - entry.created_at)),
                evidence_age_seconds=max(0, int(now - entry.evidence_fetched_at)),
                expires_iso=expires.isoformat(),
                expires_label=expires.strftime("%b %d, %Y · %H:%M:%S UTC"),
            )
        )
        if len(rows) == MAX_VISIBLE_ENTRIES:
            break
    return tuple(rows)


@router.get("/weather-cache", response_class=HTMLResponse)
async def weather_cache_page(request: Request) -> HTMLResponse:
    """Show this browser's cache with an explicit unavailable state, never create an identity on a GET."""
    if request.query_params:
        raise HTTPException(400, "Open Weather cache from the menu")
    service: CacheInventory = request.app.state.semantic_cache
    rows: tuple[CacheRow, ...] = ()
    status = "ready"
    scope = read_scope(request)
    # ② No cookie means no inventory; a visitor cannot supply a scope in the address or form.
    if not service.configured or service.mode == "off":
        status = "disabled"
    elif scope is not None:
        try:
            listing = await service.list_entries(scope)
            status = listing.status
            if status == "ready":
                rows = to_cache_rows(listing.entries, time.time())
        except Exception as error:
            status = "unavailable"
            structlog.get_logger().warning(
                "semantic_cache.operation", action="list", status="error", errorClass=type(error).__name__
            )
    # ③ Cache ownership and freshness must never survive in a shared intermediary response.
    response = render_page(
        request,
        "semantic_cache.html",
        {"entries": rows, "status": status, "mode": service.mode, "menu_path": "/weather-cache"},
    )
    response.headers["cache-control"] = "no-store"
    response.headers["vary"] = "Cookie"
    return response
