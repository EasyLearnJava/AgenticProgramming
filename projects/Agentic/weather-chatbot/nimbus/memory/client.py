"""Bounded Mem0 HTTP access for one explicit, owned preference document; no inference or conversation upload."""

import asyncio
import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import httpx2
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from nimbus.memory.models import MemoryReason, PreferenceProfile, Snapshot
from nimbus.memory.tracing import MemoryTrace, memory_trace
from nimbus.model import Tracer
from nimbus.request_trace import TraceParent

MEM0_BASE = "https://api.mem0.ai"
HTTP_SECONDS = 3.0
OPERATION_SECONDS = 8.0
MAX_RESPONSE_BYTES = 65_536
PAGE_SIZE = 50
MAX_PAGES = 3
RETENTION_DAYS = 180
PROFILE_KIND = "travel_preferences"
USER_ID = re.compile(r"^nimbus_[0-9a-f]{32}$")


class _MemoryError(Exception):
    """Carry only a bounded reason code; upstream errors and private payloads never leave this module."""

    def __init__(self, reason: MemoryReason) -> None:
        """Keep a safe reason without an HTTP response, credential or visitor fact."""
        super().__init__(reason)
        self.reason = reason


class _Record(BaseModel):
    """A bounded upstream row, including independent owner metadata for APIs which omit user_id."""

    id: UUID
    memory: str = Field(max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = Field(default=None, max_length=200)
    expiration_date: date | None = None


class _Page(BaseModel):
    """Require an explicit total and list; an error-shaped object cannot mean no saved preferences."""

    count: int = Field(ge=0)
    results: list[_Record] = Field(max_length=PAGE_SIZE)
    next: str | None = Field(default=None, max_length=2048)


class _Metadata(BaseModel):
    """Namespaced metadata identifies the schema and owner independently of result ordering or ranking."""

    model_config = ConfigDict(extra="ignore")
    nimbus_kind: Literal["travel_preferences"]
    nimbus_schema: Literal[1]
    nimbus_owner: str
    nimbus_revision: UUID

    @field_validator("nimbus_schema", mode="before")
    @classmethod
    def to_schema_version(cls, value: object) -> int:
        """Mem0 stringifies metadata values; accept only this exact schema version in either wire form."""
        if (type(value) is int and value == 1) or (type(value) is str and value == "1"):
            return 1
        raise ValueError("Unsupported preference schema")


def _snapshot(records: list[_Record]) -> Snapshot:
    """Return a single valid canonical profile or an explicit conflict, never choose between duplicates."""
    if not records:
        return Snapshot(status="empty")
    ids = tuple(str(record.id) for record in records)
    if len(records) != 1:
        return Snapshot(status="conflict", reason="duplicates", memory_ids=ids)
    record = records[0]
    metadata = _Metadata.model_validate(record.metadata)
    return Snapshot(
        status="ready",
        preferences=PreferenceProfile.model_validate_json(record.memory),
        revision=str(metadata.nimbus_revision),
        memory_ids=ids,
    )


class Mem0Service:
    """Read and replace approved defaults; all writes require a fresh revision and owned record discovery."""

    def __init__(
        self,
        key: SecretStr | None,
        make_client: Callable[[], httpx2.AsyncClient] | None = None,
        *,
        tracer: Tracer | None = None,
    ) -> None:
        """Create no network connection until an opted-in visitor requests an operation."""
        self._key = key
        self._tracer = tracer
        self._make_client = make_client or httpx2.AsyncClient

    @property
    def configured(self) -> bool:
        """Whether a nonempty API credential is available, without exposing its contents."""
        return self._key is not None and bool(self._key.get_secret_value())

    def _check_identity(self, user_id: str) -> None:
        """Reject client-supplied free-form identities and disabled providers before opening HTTP."""
        if not self.configured:
            raise _MemoryError("not_configured")
        if USER_ID.fullmatch(user_id) is None:
            raise _MemoryError("invalid_identity")

    def _logged(self, snapshot: Snapshot, trace: MemoryTrace) -> Snapshot:
        """Give tracing only the checked outcome vocabulary; the private snapshot stays inside this service."""
        trace.outcome(snapshot.status, snapshot.reason)
        return snapshot

    async def _exchange(
        self,
        client: httpx2.AsyncClient,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        params: dict[str, int] | None = None,
    ) -> Any:
        """Call a fixed Mem0 URL once, with a byte/time budget and no redirect or automatic write retry."""
        key = self._key
        if key is None:
            raise _MemoryError("not_configured")
        headers = {
            "Authorization": f"Token {key.get_secret_value()}",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        async with client.stream(
            method,
            MEM0_BASE + path,
            json=payload,
            params=params,
            headers=headers,
            timeout=HTTP_SECONDS,
            follow_redirects=False,
        ) as response:
            if response.status_code in {401, 403}:
                raise _MemoryError("authentication_failed")
            if response.status_code == 429:
                raise _MemoryError("rate_limited")
            if not 200 <= response.status_code < 300:
                raise _MemoryError("unavailable")
            size = response.headers.get("content-length", "")
            if response.headers.get("content-encoding", "identity").lower() != "identity" or (
                size.isdecimal() and (len(size) > 12 or int(size) > MAX_RESPONSE_BYTES)
            ):
                raise _MemoryError("invalid_response")
            body = bytearray()
            async for part in response.aiter_bytes():
                body.extend(part)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise _MemoryError("invalid_response")
            if not body and response.status_code == 204:
                return {}
            try:
                return json.loads(body)
            except (ValueError, RecursionError):
                raise _MemoryError("invalid_response") from None

    async def _records(self, client: httpx2.AsyncClient, user_id: str, *, expired: bool = False) -> list[_Record]:
        """Read a bounded, user-scoped set without following provider pagination URLs or trusting absent owners."""
        records: list[_Record] = []
        seen: set[UUID] = set()
        count = 0
        for number in range(1, MAX_PAGES + 1):
            page = _Page.model_validate(
                await self._exchange(
                    client,
                    "POST",
                    "/v3/memories/",
                    {"filters": {"user_id": user_id}, "show_expired": expired},
                    params={"page": number, "page_size": PAGE_SIZE},
                )
            )
            if page.count > PAGE_SIZE * MAX_PAGES:
                raise _MemoryError("pagination_limit")
            count += len(page.results)
            for record in page.results:
                if record.id in seen:
                    raise _MemoryError("invalid_response")
                seen.add(record.id)
                if record.user_id is not None and record.user_id != user_id:
                    raise _MemoryError("ownership_mismatch")
                if record.metadata.get("nimbus_kind") != PROFILE_KIND:
                    continue
                if record.metadata.get("nimbus_owner") != user_id:
                    raise _MemoryError("ownership_mismatch")
                if expired or record.expiration_date is None or record.expiration_date >= datetime.now(UTC).date():
                    records.append(record)
            if page.next is None:
                if count != page.count:
                    raise _MemoryError("invalid_response")
                return records
        raise _MemoryError("pagination_limit")

    async def read(self, user_id: str, parent: TraceParent | None = None) -> Snapshot:
        """
        Read approved preferences, returning no usable values when the provider or ownership check fails; traced as a
        step of the parent, a chat request's root, when there is one.
        """
        with memory_trace(self._tracer, "read", parent) as trace:
            try:
                self._check_identity(user_id)
                async with asyncio.timeout(OPERATION_SECONDS), self._make_client() as client:
                    snapshot = _snapshot(await self._records(client, user_id))
            except _MemoryError as error:
                snapshot = Snapshot(status="unavailable", reason=error.reason)
            except (TimeoutError, httpx2.TimeoutException):
                snapshot = Snapshot(status="unavailable", reason="timeout")
            except httpx2.HTTPError:
                snapshot = Snapshot(status="unavailable", reason="unavailable")
            except (ValidationError, ValueError):
                snapshot = Snapshot(status="unavailable", reason="invalid_response")
            return self._logged(snapshot, trace)

    async def save(self, user_id: str, preferences: PreferenceProfile, expected_revision: str) -> Snapshot:
        """Replace the matching revision, then verify provider readback; an acknowledgement alone is not success."""
        with memory_trace(self._tracer, "save") as trace:
            attempted = False
            acknowledged = False
            try:
                self._check_identity(user_id)
                preferences = PreferenceProfile.model_validate(preferences.model_dump())
                async with asyncio.timeout(OPERATION_SECONDS), self._make_client() as client:
                    # ① Read immediately before mutation. Mem0 does not expose transactional compare-and-swap;
                    # concurrent first saves become a visible conflict rather than silently selecting a duplicate.
                    current = _snapshot(await self._records(client, user_id))
                    if current.status == "conflict":
                        return self._logged(current, trace)
                    if current.revision != expected_revision:
                        return self._logged(Snapshot(status="conflict", reason="stale_revision"), trace)
                    revision = str(uuid4())
                    metadata = {
                        "nimbus_kind": PROFILE_KIND,
                        "nimbus_schema": 1,
                        "nimbus_owner": user_id,
                        "nimbus_revision": revision,
                    }
                    expiry = (datetime.now(UTC).date() + timedelta(days=RETENTION_DAYS)).isoformat()
                    text = preferences.model_dump_json()
                    # ② Only this typed JSON is sent, with inference disabled. No raw message or automatic extraction.
                    attempted = True
                    if current.memory_ids:
                        await self._exchange(
                            client,
                            "PUT",
                            f"/v1/memories/{current.memory_ids[0]}/",
                            {
                                "text": text,
                                "metadata": metadata,
                                "expiration_date": expiry,
                            },
                        )
                    else:
                        await self._exchange(
                            client,
                            "POST",
                            "/v3/memories/add/",
                            {
                                "messages": [{"role": "user", "content": text}],
                                "user_id": user_id,
                                "metadata": metadata,
                                "infer": False,
                                "expiration_date": expiry,
                            },
                        )
                    acknowledged = True
                    # ③ Verify persisted content and revision, not a provider success string or returned ID alone.
                    snapshot = _snapshot(await self._records(client, user_id))
                    if snapshot.status == "conflict":
                        return self._logged(snapshot, trace)
                    if snapshot.revision != revision or snapshot.preferences != preferences:
                        snapshot = Snapshot(status="pending", reason="pending_confirmation")
            except _MemoryError as error:
                uncertain = acknowledged or (attempted and error.reason in {"unavailable", "invalid_response"})
                snapshot = Snapshot(status="pending" if uncertain else "unavailable", reason=error.reason)
            except (TimeoutError, httpx2.TimeoutException):
                snapshot = Snapshot(status="pending" if attempted else "unavailable", reason="timeout")
            except httpx2.HTTPError:
                snapshot = Snapshot(status="pending" if attempted else "unavailable", reason="unavailable")
            except (ValidationError, ValueError):
                snapshot = Snapshot(status="pending" if attempted else "unavailable", reason="invalid_response")
            return self._logged(snapshot, trace)

    async def forget(self, user_id: str) -> bool:
        """Delete only discovered, owned Nimbus records, including expired ones, and confirm their absence."""
        with memory_trace(self._tracer, "forget") as trace:
            try:
                self._check_identity(user_id)
                async with asyncio.timeout(OPERATION_SECONDS), self._make_client() as client:
                    # Keep the identity until this verification succeeds so a failed deletion can be retried.
                    records = await self._records(client, user_id, expired=True)
                    for record in records:
                        await self._exchange(client, "DELETE", f"/v1/memories/{record.id}/")
                    remaining = await self._records(client, user_id, expired=True)
                    snapshot = Snapshot(
                        status="empty" if not remaining else "pending",
                        reason="" if not remaining else "pending_confirmation",
                    )
            except _MemoryError as error:
                snapshot = Snapshot(status="unavailable", reason=error.reason)
            except (TimeoutError, httpx2.TimeoutException):
                snapshot = Snapshot(status="unavailable", reason="timeout")
            except httpx2.HTTPError:
                snapshot = Snapshot(status="unavailable", reason="unavailable")
            except (ValidationError, ValueError):
                snapshot = Snapshot(status="unavailable", reason="invalid_response")
            return self._logged(snapshot, trace).status == "empty"
