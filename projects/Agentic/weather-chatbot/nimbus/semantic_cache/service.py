"""Bounded Qdrant REST operations with hosted MiniLM inference and fail-open answer reuse."""

import asyncio
import hmac
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from typing import Literal
from uuid import UUID

import httpx2
import structlog

from nimbus.config import Settings
from nimbus.request_trace import CacheTraceStep
from nimbus.retrieval_gate import RetrievalGate
from nimbus.semantic_cache.identity import signature
from nimbus.semantic_cache.models import (
    MODEL,
    TTL_SECONDS,
    VERSION,
    CacheEntry,
    CacheListing,
    CacheLookup,
    CachePolicy,
    CacheStore,
)
from nimbus.semantic_cache.policy import digest, embedding_text, normalized

MAX_RESPONSE_BYTES = 2_000_000
MAX_POINTS = 2000
TIMEOUT_SECONDS = 2.0
log = structlog.get_logger()


@contextmanager
def qdrant_step(
    trace: CacheTraceStep | None,
    action: Literal["exact", "similarity", "cleanup", "count", "save"],
    deadline: asyncio.Timeout,
) -> Iterator[CacheTraceStep | None]:
    """Close each provider span and distinguish our timeout from a visitor cancelling the request."""
    with trace.step(action) if trace is not None else nullcontext(None) as operation:
        try:
            yield operation
        except asyncio.CancelledError:
            if operation is not None and deadline.expired():
                operation.outcome("error")
            raise


def make_client() -> httpx2.AsyncClient:
    """Use HTTPS with bounded connections, no redirects and no local inference dependencies."""
    return httpx2.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False, limits=httpx2.Limits(max_connections=4))


class SemanticCacheService:
    """An optional optimization: outages, bad data and exhausted quotas cannot fail ordinary chat."""

    def __init__(
        self,
        settings: Settings,
        factory: Callable[[], httpx2.AsyncClient] = make_client,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Retain only deployment configuration; per-browser records remain in Qdrant."""
        self.mode = settings.semantic_cache_mode
        self._url = settings.qdrant_url.rstrip("/")
        self._key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else ""
        self._collection = settings.qdrant_collection
        self._threshold = settings.semantic_cache_threshold
        self._factory, self._clock = factory, clock
        self._gate = RetrievalGate()

    @property
    def configured(self) -> bool:
        """An off or incomplete deployment incurs no cache network requests."""
        return self.mode != "off" and bool(self._url and self._key)

    async def _request(
        self, http: httpx2.AsyncClient, method: str, path: str, body: dict[str, object]
    ) -> dict[str, object]:
        """Read a size-bounded JSON object; never include credentials or provider error bodies in logs."""
        url = f"{self._url}/collections/{self._collection}{path}"
        async with http.stream(method, url, json=body, headers={"api-key": self._key}) as response:
            response.raise_for_status()
            data = bytearray()
            async for part in response.aiter_bytes():
                data.extend(part)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ValueError("oversized_cache_response")
            value = json.loads(data)
            if not isinstance(value, dict) or value.get("status") != "ok":
                raise ValueError("invalid_cache_response")
            return value

    def _filter(self, scope: str, context: str = "", policy: CachePolicy | None = None) -> dict[str, object]:
        """Apply browser and absolute-expiry filters before vector ranking, never after selecting another user."""
        values = {"scope": scope, "version": VERSION}
        if context:
            values["context"] = context
        if policy:
            values["guard"] = digest(policy.model_dump())
        return {
            "must": [
                *({"key": key, "match": {"value": value}} for key, value in values.items()),
                {"key": "expires_at", "range": {"gt": self._clock()}},
            ]
        }

    def _entries(self, result: dict[str, object], scope: str) -> tuple[CacheEntry, ...]:
        """Authenticate and revalidate each entry independently of remote filters and storage permissions."""
        page = result.get("result")
        if not isinstance(page, dict) or not isinstance(page.get("points"), list):
            raise ValueError("invalid_cache_points")
        entries = []
        for point in page["points"][:50]:
            if not isinstance(point, dict) or not isinstance(point.get("payload"), dict):
                continue
            payload = point["payload"]
            record, mac = payload.get("record"), payload.get("mac")
            if not isinstance(record, str) or len(record) > 60000 or not isinstance(mac, str):
                continue
            if not hmac.compare_digest(signature(self._key, "entry", record), mac):
                continue
            try:
                entry = CacheEntry.model_validate_json(record)
            except ValueError:
                continue
            now = self._clock()
            if (
                entry.scope == scope
                and entry.evidence_fetched_at <= entry.created_at <= now
                and now < entry.expires_at <= entry.created_at + TTL_SECONDS
            ):
                entries.append(entry)
        return tuple(entries)

    def _log(self, action: str, status: str, started: float, reason: str = "") -> None:
        """Emit only bounded operational facts, never scopes, questions, responses or preference values."""
        log.info(
            "semantic_cache.operation",
            action=action,
            status=status,
            reason=reason,
            ms=round((time.perf_counter() - started) * 1000),
        )

    async def lookup(
        self,
        question: str,
        scope: str,
        context: str,
        policy: CachePolicy,
        *,
        trace: CacheTraceStep | None = None,
    ) -> CacheLookup:
        """Try exact reuse without inference, then semantic similarity within identical independent guards."""
        started = time.perf_counter()
        if not self.configured:
            return CacheLookup(status="bypass")
        try:
            async with self._gate.reserve(scope), asyncio.timeout(TIMEOUT_SECONDS) as deadline, self._factory() as http:
                filters = self._filter(scope, context, policy)
                exact = digest(normalized(question))
                exact_filter = {"must": [filters, {"key": "exact", "match": {"value": exact}}]}
                with qdrant_step(trace, "exact", deadline) as operation:
                    response = await self._request(
                        http,
                        "POST",
                        "/points/scroll",
                        {
                            "filter": exact_filter,
                            "limit": 1,
                            "with_payload": True,
                            "with_vector": False,
                        },
                    )
                    candidates = self._entries(response, scope)
                    if operation is not None:
                        operation.outcome(
                            "exact_hit"
                            if any(e.context == context and e.policy == policy and e.exact == exact for e in candidates)
                            else "miss"
                        )
                status = "exact_hit"
                if not candidates:
                    with qdrant_step(trace, "similarity", deadline) as operation:
                        if operation is not None:
                            operation.similarity(None, self._threshold)
                        response = await self._request(
                            http,
                            "POST",
                            "/points/query",
                            {
                                "query": {"text": embedding_text(question), "model": MODEL},
                                "filter": filters,
                                "limit": 1,
                                "score_threshold": self._threshold,
                                "with_payload": True,
                                "with_vector": False,
                            },
                        )
                        candidates = self._entries(response, scope)
                        # Independently reject missing/non-finite/below-threshold provider scores.
                        result = response.get("result")
                        points = result.get("points") if isinstance(result, dict) else None
                        score = (
                            points[0].get("score")
                            if isinstance(points, list) and len(points) == 1 and isinstance(points[0], dict)
                            else None
                        )
                        if operation is not None:
                            operation.similarity(score, self._threshold)
                        if (
                            not isinstance(score, (float, int))
                            or isinstance(score, bool)
                            or not (self._threshold <= score <= 1.00001)
                        ):
                            candidates = ()
                        if operation is not None:
                            operation.outcome(
                                "semantic_hit"
                                if any(e.context == context and e.policy == policy for e in candidates)
                                else "miss"
                            )
                    status = "semantic_hit"
                entry = next(
                    (
                        e
                        for e in candidates
                        if e.context == context and e.policy == policy and (status != "exact_hit" or e.exact == exact)
                    ),
                    None,
                )
                if entry is None:
                    self._log("lookup", "miss", started)
                    return CacheLookup(status="miss")
                if self.mode == "shadow":
                    self._log("lookup", "shadow_hit", started)
                    return CacheLookup(status="shadow_hit")
                self._log("lookup", status, started)
                return CacheLookup(status=status, entry=entry)
        except Exception:
            self._log("lookup", "error", started, "unavailable")
            return CacheLookup(status="error")

    async def store(self, question: str, entry: CacheEntry, *, trace: CacheTraceStep | None = None) -> CacheStore:
        """Keep a fresh verified answer; cleanup is opportunistic and never controls logical expiry."""
        started = time.perf_counter()
        if not self.configured:
            return CacheStore(status="bypass")
        if entry.expires_at <= self._clock():
            return CacheStore(status="not_reusable")
        try:
            async with asyncio.timeout(TIMEOUT_SECONDS) as deadline, self._factory() as http:
                with qdrant_step(trace, "cleanup", deadline):
                    await self._request(
                        http,
                        "POST",
                        "/points/delete?wait=true",
                        {
                            "filter": {
                                "must": [
                                    {"key": "expires_at", "range": {"lte": self._clock()}},
                                ]
                            }
                        },
                    )
                with qdrant_step(trace, "count", deadline) as operation:
                    count = await self._request(http, "POST", "/points/count", {"exact": True})
                    result = count.get("result")
                    if not isinstance(result, dict) or type(result.get("count")) is not int or result["count"] < 0:
                        raise ValueError("invalid_cache_count")
                    full = result["count"] >= MAX_POINTS
                    if operation is not None and full:
                        operation.outcome("cache_full")
                if full:
                    self._log("store", "bypass", started, "capacity")
                    return CacheStore(status="cache_full")
                # One record per browser/context/guard prevents paraphrases from accumulating duplicates.
                identifier = str(UUID(digest([entry.scope, entry.context, entry.policy.model_dump()])[:32]))
                record = entry.model_dump_json()
                payload = {
                    "scope": entry.scope,
                    "context": entry.context,
                    "guard": digest(entry.policy.model_dump()),
                    "version": VERSION,
                    "exact": entry.exact,
                    "expires_at": entry.expires_at,
                    "record": record,
                    "mac": signature(self._key, "entry", record),
                }
                with qdrant_step(trace, "save", deadline) as operation:
                    await self._request(
                        http,
                        "PUT",
                        "/points?wait=true",
                        {
                            "points": [
                                {
                                    "id": identifier,
                                    "vector": {"text": embedding_text(question), "model": MODEL},
                                    "payload": payload,
                                }
                            ]
                        },
                    )
                    if operation is not None:
                        operation.outcome("saved")
                self._log("store", "stored", started)
                return CacheStore(status="saved")
        except Exception:
            self._log("store", "error", started, "unavailable")
            return CacheStore(status="error")

    async def list_entries(self, scope: str) -> CacheListing:
        """Return at most fifty still-valid entries belonging only to this browser."""
        if not self.configured:
            return CacheListing(status="disabled")
        started = time.perf_counter()
        try:
            async with self._gate.reserve(scope), asyncio.timeout(TIMEOUT_SECONDS), self._factory() as http:
                response = await self._request(
                    http,
                    "POST",
                    "/points/scroll",
                    {
                        "filter": self._filter(scope),
                        "limit": 50,
                        "with_payload": True,
                        "with_vector": False,
                    },
                )
                entries = tuple(sorted(self._entries(response, scope), key=lambda e: e.created_at, reverse=True))
                self._log("list", "ready", started)
                return CacheListing(status="ready", entries=entries)
        except Exception:
            self._log("list", "error", started, "unavailable")
            return CacheListing(status="unavailable")
