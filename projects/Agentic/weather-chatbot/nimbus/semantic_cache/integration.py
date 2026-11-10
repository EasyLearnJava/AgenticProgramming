"""Request-local cache preparation, history authentication and successful-answer admission."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import structlog
from fastapi import Request

from nimbus.chips import ToolChip
from nimbus.config import Settings
from nimbus.memory.context import MemoryContext
from nimbus.request_trace import CacheBypassReason, CacheTraceStep, RequestTrace
from nimbus.semantic_cache.evidence import to_entry
from nimbus.semantic_cache.identity import new_scope, plain_answer, read_scope, receipt, valid_receipt
from nimbus.semantic_cache.models import CachePolicy, CacheStore
from nimbus.semantic_cache.policy import cache_policy, compatible_history, context_fingerprint
from nimbus.semantic_cache.service import SemanticCacheService
from nimbus.utils import is_same_origin


@dataclass(frozen=True)
class CacheCompletion:
    """History authentication and cache storage are independent outcomes of a completed answer."""

    receipt: str
    store: CacheStore


@dataclass(frozen=True)
class CacheTurn:
    """An eligible standalone question, its browser scope and verified neutral prior weather turns."""

    service: SemanticCacheService
    policy: CachePolicy
    scope: str
    context: str
    cookie: str
    question: str
    history: tuple[tuple[str, str], ...]
    secret: str

    def receipt_for(self, html: str) -> str:
        """Allow subsequent repeats only if the browser returns the actual rendered conversation unchanged."""
        return receipt(
            self.secret,
            self.scope,
            self.context,
            (*self.history, ("user", self.question), ("assistant", plain_answer(html))),
        )

    async def completed(
        self, answer: str, chips: Sequence[ToolChip], html: str, *, trace: CacheTraceStep | None = None
    ) -> CacheCompletion:
        """Authenticate the completed turn independently of whether its evidence can enter the cache."""
        entry = to_entry(self.question, answer, chips, self.scope, self.context, self.policy, time.time())
        if entry is not None:
            stored = await self.service.store(self.question, entry, trace=trace)
        else:
            stored = CacheStore(status="not_reusable")
            structlog.get_logger().info(
                "semantic_cache.operation", action="store", status="not_reusable", reason="evidence", ms=0
            )
        # The receipt proves which conversation Nimbus produced, not that this answer is reusable weather evidence.
        return CacheCompletion(self.receipt_for(html), stored)


def prepare(
    request: Request,
    question: str,
    locale: str,
    time_zone: str,
    lane: str,
    history: Sequence[tuple[str, str]],
    supplied_receipt: str,
    memory: MemoryContext,
    now: datetime,
    *,
    trace: RequestTrace | None = None,
) -> CacheTurn | None:
    """Protect deterministic workflows and unknown context before performing any embedding request."""
    service: SemanticCacheService = request.app.state.semantic_cache

    def bypass(reason: CacheBypassReason, log_reason: str) -> None:
        """Explain a decision using fixed operational terms without recording any request content."""
        if trace is not None:
            trace.cache_outcome("bypass", reason)
        structlog.get_logger().info(
            "semantic_cache.operation", action="lookup", status="bypass", reason=log_reason, ms=0
        )

    if not service.configured:
        bypass("disabled" if service.mode == "off" else "unconfigured", "disabled")
        return None
    settings: Settings = request.app.state.settings
    origin = request.headers.get("origin", "")
    policy = cache_policy(question, now, locale, time_zone, memory.preferences.unit_system)
    if lane != "rest-no-auth":
        bypass("lane", "ineligible")
        return None
    if policy is None:
        bypass("ineligible", "ineligible")
        return None
    if not origin or not is_same_origin(origin, str(request.url)):
        bypass("origin", "ineligible")
        return None
    if memory.snapshot.status not in {"ready", "empty"}:
        bypass("memory_unavailable", "context")
        return None
    scope, cookie = read_scope(request), ""
    if scope is None:
        scope, cookie = new_scope(request)
    context = context_fingerprint(
        memory,
        settings.gemini_model,
        (settings.parks_enabled, settings.flights_enabled, settings.hotels_enabled),
        settings.vercel_git_commit_sha or "",
    )
    assert settings.qdrant_api_key is not None  # noqa: S101 - configured requires this credential
    secret = settings.qdrant_api_key.get_secret_value()
    if not valid_receipt(secret, scope, context, history, supplied_receipt):
        bypass("unverified_history", "context")
        return None
    # Explicit cities can change; signed history must still preserve time, units and same-city qualifiers.
    for role, text in history:
        if role == "user":
            earlier = cache_policy(text, now, locale, time_zone, memory.preferences.unit_system)
            if not compatible_history(earlier, policy):
                bypass("incompatible_history", "context")
                return None
    return CacheTurn(service, policy, scope, context, cookie, question, tuple(history), secret)
