"""Request-local optional memory loading; an outage or paused browser leaves ordinary Nimbus behavior intact."""

from dataclasses import dataclass

from fastapi import HTTPException, Request

from nimbus.memory.client import Mem0Service
from nimbus.memory.identity import BrowserIdentity, read_identity
from nimbus.memory.models import PreferenceProfile, Snapshot
from nimbus.utils import is_same_origin


@dataclass(frozen=True)
class MemoryContext:
    """Private preferences and their availability, never reused between requests or visitors."""

    identity: BrowserIdentity | None
    snapshot: Snapshot

    @property
    def preferences(self) -> PreferenceProfile:
        """Only active, successfully read preferences can influence an answer."""
        if self.identity and self.identity.mode == "active" and self.snapshot.status == "ready":
            return self.snapshot.preferences
        return PreferenceProfile()


def configured(request: Request) -> bool:
    """Memory requires its own feature switch, API credential and stable signing secret."""
    settings = request.app.state.settings
    if not getattr(settings, "memory_enabled", False) or not settings.memory_cookie_secret:
        return False
    service: Mem0Service = request.app.state.mem0
    return service.configured


async def load_memory(request: Request, *, include_paused: bool = False) -> MemoryContext:
    """Read once for this request, with a per-instance gate and no public-response caching."""
    identity = read_identity(request)
    empty = MemoryContext(identity, Snapshot(status="empty"))
    if not configured(request) or identity is None:
        return empty
    if identity.mode != "active" and not include_paused:
        return empty
    # Memory must never be consumed by a cross-origin chat POST, even if a custom client submits a cookie.
    if request.method != "GET" and (
        not request.headers.get("origin") or not is_same_origin(request.headers["origin"], str(request.url))
    ):
        return empty
    cached = getattr(request.state, "memory_context", None)
    if isinstance(cached, MemoryContext):
        return cached
    service: Mem0Service = request.app.state.mem0
    try:
        async with request.app.state.memory_gate.reserve(request.client.host if request.client else "unknown"):
            snapshot = await service.read(identity.user_id)
    except HTTPException:
        snapshot = Snapshot(status="unavailable", reason="rate_limited")
    context = MemoryContext(identity, snapshot)
    request.state.memory_context = context
    return context
