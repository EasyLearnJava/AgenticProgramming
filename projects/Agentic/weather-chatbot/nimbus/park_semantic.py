"""Bounded hosted park retrieval: Qdrant ranks public chunk IDs; SQLite remains the source of answer text."""

import asyncio
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from uuid import NAMESPACE_URL, uuid5

import httpx2

from nimbus.config import Settings

PARK_MODEL: Final = "sentence-transformers/all-minilm-l6-v2"
PARK_PROFILE: Final = "nimbus-park-minilm-title-section-text-v1"
PARK_DIMENSIONS: Final = 384
PARK_SCHEMA: Final = 1
PARK_SEARCH_SECONDS = 3.0
MAX_RESPONSE_BYTES = 1_000_000
DENSE_LIMIT: Final = 32
type SemanticStatus = Literal["ready", "unconfigured", "index_mismatch", "unavailable", "invalid_response", "timeout"]


@dataclass(frozen=True)
class SemanticResult:
    """A fixed outcome and bounded scores, with no provider passage text, request text or credentials."""

    status: SemanticStatus
    scores: dict[str, float] = field(default_factory=dict)
    provider: Literal["qdrant"] = "qdrant"


def point_id(index_version: str, chunk_id: str) -> str:
    """A deterministic UUID for a versioned public chunk, never a browser cache record."""
    return str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/{index_version}/chunk/{chunk_id}"))


def manifest_id(index_version: str) -> str:
    """A separate readiness marker, published only after all vectors and payloads have been verified."""
    return str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/{index_version}/manifest"))


def manifest_payload(index_version: str, chunk_count: int) -> dict[str, object]:
    """The exact public ingestion contract the serving application requires before querying this version."""
    return {
        "kind": "manifest",
        "schema": PARK_SCHEMA,
        "index_version": index_version,
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "chunk_count": chunk_count,
    }


def chunk_payload(chunk: Mapping[str, Any], index_version: str) -> dict[str, object]:
    """Public identity and filter metadata; the provider does not become the authority for source text."""
    return {
        "kind": "chunk",
        "index_version": index_version,
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "chunk_id": chunk["id"],
        "content_hash": chunk["content_hash"],
        "park_id": chunk["park_id"],
        "destination_ids": chunk["destination_ids"],
        "seasons": chunk["seasons"],
    }


def make_client() -> httpx2.AsyncClient:
    """Use bounded TLS requests without redirects; the operation deadline covers both readiness and search."""
    return httpx2.AsyncClient(
        timeout=PARK_SEARCH_SECONDS + 1, follow_redirects=False, limits=httpx2.Limits(max_connections=4)
    )


class QdrantParkAPI:
    """The collection-scoped HTTP boundary shared by the read adapter and explicit ingestion command."""

    def __init__(self, settings: Settings) -> None:
        """Keep the key only in request headers and independently refuse the weather-cache collection."""
        key = settings.parks_qdrant_api_key or settings.qdrant_api_key
        self._key = key.get_secret_value() if key else ""
        collection = settings.parks_qdrant_collection
        self.base = f"{settings.qdrant_url.rstrip('/')}/collections/{collection}"
        self.configured = bool(
            settings.qdrant_url
            and self._key
            and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", collection)
            and collection != settings.qdrant_collection
        )

    async def request(
        self,
        http: httpx2.AsyncClient,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        missing_ok: bool = False,
    ) -> dict[str, Any] | None:
        """Read only bounded JSON; provider bodies, URLs and exceptions never enter our logs or traces."""
        if not self.configured:
            raise ValueError("Park search is not configured")
        async with http.stream(
            method, self.base + path, json=body, headers={"api-key": self._key}, follow_redirects=False
        ) as response:
            if missing_ok and response.status_code == 404:
                return None
            response.raise_for_status()
            data = bytearray()
            async for block in response.aiter_bytes(chunk_size=8192):
                if len(data) + len(block) > MAX_RESPONSE_BYTES:
                    raise ValueError("Oversized park search response")
                data.extend(block)
            document = json.loads(data)
            if not isinstance(document, dict) or document.get("status") != "ok":
                raise ValueError("Invalid park search response")
            return document


class QdrantParkSearch:
    """Hosted semantic candidates scoped and checked against the caller's immutable local knowledge index."""

    provider: Final = "qdrant"
    model: Final = PARK_MODEL

    def __init__(
        self,
        settings: Settings,
        factory: Callable[[], httpx2.AsyncClient] = make_client,
        *,
        chunk_count: int,
    ) -> None:
        """Construct without network calls or importing a local embedding model."""
        self._api = QdrantParkAPI(settings)
        self._factory = factory
        self._chunk_count = chunk_count

    @property
    def configured(self) -> bool:
        """A missing credential or unsafe collection causes an explicit keyword fallback before any HTTP call."""
        return self._api.configured and 0 < self._chunk_count <= 1000

    async def search(
        self,
        query: str,
        *,
        index_version: str,
        park_id: str,
        destination_id: str,
        season: str | None,
        eligible: Mapping[str, str],
    ) -> SemanticResult:
        """Check publication, then rank public IDs; all remote content must match local scope and hashes."""
        if not self.configured:
            return SemanticResult("unconfigured")
        if not eligible:
            return SemanticResult("ready")
        if len(eligible) > 1000 or not query.strip() or len(query) > 2000:
            return SemanticResult("invalid_response")
        if season not in {None, "winter", "spring", "summer", "fall"}:
            return SemanticResult("invalid_response")
        try:
            async with asyncio.timeout(PARK_SEARCH_SECONDS), self._factory() as http:
                # ① A different or unpublished index must not silently appear to be a semantic miss.
                manifest = await self._api.request(
                    http, "GET", f"/points/{manifest_id(index_version)}", missing_ok=True
                )
                expected = manifest_payload(index_version, self._chunk_count)
                result = manifest.get("result") if manifest else None
                payload = result.get("payload") if isinstance(result, dict) else None
                if (
                    not isinstance(payload, dict)
                    or type(payload.get("schema")) is not int
                    or type(payload.get("chunk_count")) is not int
                    or any(payload.get(key) != value for key, value in expected.items())
                ):
                    return SemanticResult("index_mismatch")
                values = {
                    "kind": "chunk",
                    "index_version": index_version,
                    "model": PARK_MODEL,
                    "profile": PARK_PROFILE,
                    "park_id": park_id,
                    "destination_ids": destination_id,
                }
                conditions: list[dict[str, object]] = [
                    {"key": key, "match": {"value": value}} for key, value in values.items()
                ]
                if season is not None:
                    conditions.append({"key": "seasons", "match": {"any": [season, "all"]}})
                # ② The eligible IDs enforce exactly the same local candidate scope before vector ranking.
                conditions.append({"has_id": [point_id(index_version, identity) for identity in sorted(eligible)]})
                response = await self._api.request(
                    http,
                    "POST",
                    "/points/query",
                    {
                        "query": {"text": query, "model": PARK_MODEL},
                        "filter": {"must": conditions},
                        "limit": min(DENSE_LIMIT, len(eligible)),
                        "with_payload": True,
                        "with_vector": False,
                    },
                )
                result = response.get("result") if response else None
                points = result.get("points") if isinstance(result, dict) else None
                if not isinstance(points, list) or len(points) > min(DENSE_LIMIT, len(eligible)):
                    raise ValueError("Invalid park candidate response")
                scores: dict[str, float] = {}
                for point in points:
                    if not isinstance(point, dict) or not isinstance(point.get("payload"), dict):
                        raise ValueError("Invalid park candidate")
                    payload = point["payload"]
                    identity, score = payload.get("chunk_id"), point.get("score")
                    destinations, seasons = payload.get("destination_ids"), payload.get("seasons")
                    # ③ Never accept another version, destination, document body or a malformed numeric score.
                    if (
                        not isinstance(identity, str)
                        or identity not in eligible
                        or identity in scores
                        or point.get("id") != point_id(index_version, identity)
                        or payload.get("content_hash") != eligible[identity]
                        or any(payload.get(key) != value for key, value in values.items() if key != "destination_ids")
                        or not isinstance(destinations, list)
                        or destination_id not in destinations
                        or not isinstance(seasons, list)
                        or (season is not None and season not in seasons and "all" not in seasons)
                        or isinstance(score, bool)
                        or not isinstance(score, (int, float))
                        or not -1 <= score <= 1
                        or not math.isfinite(score)
                    ):
                        raise ValueError("Park candidate does not match the local index")
                    scores[identity] = float(score)
                return SemanticResult("ready", scores)
        except (TimeoutError, httpx2.TimeoutException):
            return SemanticResult("timeout")
        except (ValueError, TypeError, KeyError):
            return SemanticResult("invalid_response")
        except Exception:
            return SemanticResult("unavailable")
