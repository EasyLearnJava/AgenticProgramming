"""Qdrant owns public park passages, native BM25 and dense retrieval; every read is bounded and verified."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from uuid import NAMESPACE_URL, uuid5

import httpx2

from nimbus.config import Settings
from nimbus.park_models import ParkChunk
from nimbus.park_text import record_hash, to_embedding_text

PARK_MODEL: Final = "sentence-transformers/all-minilm-l6-v2"
PARK_PROFILE: Final = "nimbus-park-hybrid-text-v2"
PARK_DIMENSIONS: Final = 384
PARK_SCHEMA: Final = 2
BM25_FIELD: Final = "bm25_text"
PARK_SEARCH_SECONDS = 3.0
PARK_CATALOG_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1_000_000
DENSE_LIMIT: Final = 32
CATALOG_PAGE_SIZE: Final = 32
type SemanticStatus = Literal[
    "ready", "unconfigured", "index_mismatch", "unavailable", "invalid_response", "timeout", "disabled"
]
type SearchMethod = Literal["semantic", "bm25"]


@dataclass(frozen=True)
class SemanticResult:
    """A fixed outcome and bounded scores, without retaining a private question or provider exception."""

    status: SemanticStatus
    scores: dict[str, float] = field(default_factory=dict)
    provider: Literal["qdrant"] = "qdrant"


@dataclass(frozen=True)
class CatalogResult:
    """Verified public chunks, optionally carrying the actual hosted vectors for the Knowledge page."""

    status: SemanticStatus
    chunks: list[dict[str, Any]] = field(default_factory=list, repr=False)


class PublicationError(ValueError):
    """The requested immutable generation has not been verified and published."""


def point_id(index_version: str, chunk_id: str) -> str:
    """A deterministic UUID for a versioned public chunk, never a browser cache record."""
    return str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/{index_version}/chunk/{chunk_id}"))


def manifest_id(index_version: str) -> str:
    """A separate readiness marker, published only after all records and indexes have been verified."""
    return str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/{index_version}/manifest"))


def manifest_payload(index_version: str, chunk_count: int) -> dict[str, object]:
    """The public ingestion contract required before either search branch or catalog can be served."""
    return {
        "kind": "manifest",
        "schema": PARK_SCHEMA,
        "index_version": index_version,
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "chunk_count": chunk_count,
        "bm25_field": BM25_FIELD,
    }


def chunk_payload(chunk: Mapping[str, Any], index_version: str) -> dict[str, Any]:
    """Store public source text and its canonical searchable representation beside one dense vector."""
    from nimbus.parks import to_terms

    item = ParkChunk.model_validate({name: chunk[name] for name in ParkChunk.model_fields}).model_dump(mode="json")
    return {
        **item,
        "kind": "chunk",
        "schema": PARK_SCHEMA,
        "index_version": index_version,
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "chunk_id": item["id"],
        "record_hash": record_hash(item),
        BM25_FIELD: " ".join(to_terms(f"{item['section']} {item['section']} {item['text']}")),
    }


def vector_ready(value: object) -> bool:
    """Accept only a finite, nonzero hosted vector with the configured dimensionality."""
    return (
        isinstance(value, list)
        and len(value) == PARK_DIMENSIONS
        and all(type(number) in {int, float} and -1e6 < number < 1e6 and math.isfinite(number) for number in value)
        and any(number != 0 for number in value)
    )


def make_client() -> httpx2.AsyncClient:
    """Use bounded TLS requests without redirects; operation deadlines bound cumulative network work."""
    return httpx2.AsyncClient(
        timeout=PARK_SEARCH_SECONDS + 1, follow_redirects=False, limits=httpx2.Limits(max_connections=4)
    )


class QdrantParkAPI:
    """The isolated collection HTTP boundary shared by retrieval and the explicit publisher."""

    def __init__(self, settings: Settings) -> None:
        """Keep credentials in headers and refuse the weather-cache collection before any network call."""
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
        """Read bounded JSON only; provider bodies, URLs and exceptions never enter logs or traces."""
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
    """Native BM25, hosted semantic search and source reads against one immutable public collection."""

    provider: Final = "qdrant"
    model: Final = PARK_MODEL

    def __init__(
        self,
        settings: Settings,
        factory: Callable[[], httpx2.AsyncClient] = make_client,
        *,
        chunk_count: int,
    ) -> None:
        """Construct without network calls, local passage storage or an embedding model."""
        self._api = QdrantParkAPI(settings)
        self._factory = factory
        self._chunk_count = chunk_count

    @property
    def configured(self) -> bool:
        """An unsafe collection or absent credential leaves every branch explicitly unconfigured."""
        return self._api.configured and 0 < self._chunk_count <= 1000

    async def _ready(self, http: httpx2.AsyncClient, index_version: str) -> None:
        """Require exact publication metadata before returning data from this corpus generation."""
        document = await self._api.request(http, "GET", f"/points/{manifest_id(index_version)}", missing_ok=True)
        result = document.get("result") if document else None
        payload = result.get("payload") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("id") != manifest_id(index_version)
            or not isinstance(payload, dict)
            or type(payload.get("schema")) is not int
            or type(payload.get("chunk_count")) is not int
            or payload != manifest_payload(index_version, self._chunk_count)
        ):
            raise PublicationError("Park generation is not published")

    async def health(self, index_version: str) -> SemanticStatus:
        """Check the published generation without generating a query embedding or downloading passages."""
        if not self.configured:
            return "unconfigured"
        try:
            async with asyncio.timeout(PARK_SEARCH_SECONDS), self._factory() as http:
                await self._ready(http, index_version)
            return "ready"
        except PublicationError:
            return "index_mismatch"
        except (TimeoutError, httpx2.TimeoutException):
            return "timeout"
        except (ValueError, TypeError, KeyError):
            return "invalid_response"
        except Exception:
            return "unavailable"

    @staticmethod
    def _chunk(point: object, index_version: str) -> dict[str, Any]:
        """Validate full public source records and their content and metadata hashes before using them."""
        if not isinstance(point, dict) or not isinstance(point.get("payload"), dict):
            raise ValueError("Invalid park record")
        payload = point["payload"]
        item = ParkChunk.model_validate({name: payload[name] for name in ParkChunk.model_fields}).model_dump(
            mode="json"
        )
        digest = hashlib.sha256(to_embedding_text(item["title"], item["section"], item["text"]).encode()).hexdigest()
        if (
            item["content_hash"] != digest
            or point.get("id") != point_id(index_version, item["id"])
            or payload != chunk_payload(item, index_version)
        ):
            raise ValueError("Park record identity or content mismatch")
        return item

    async def search(
        self,
        query: str,
        *,
        index_version: str,
        park_id: str,
        destination_id: str,
        season: str | None,
        eligible: Mapping[str, str],
        method: SearchMethod = "semantic",
    ) -> SemanticResult:
        """Run one scoped branch, preserving its score scale for diagnostics and rank fusion."""
        if not self.configured:
            return SemanticResult("unconfigured")
        if not eligible:
            return SemanticResult("ready")
        if (
            len(eligible) > 1000
            or not query.strip()
            or len(query) > 2000
            or method not in {"semantic", "bm25"}
            or season not in {None, "winter", "spring", "summer", "fall"}
        ):
            return SemanticResult("invalid_response")
        try:
            async with asyncio.timeout(PARK_SEARCH_SECONDS), self._factory() as http:
                # ① Every branch requires the same published generation and hard scope before ranking.
                await self._ready(http, index_version)
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
                conditions.append({"has_id": [point_id(index_version, identity) for identity in sorted(eligible)]})
                body: dict[str, object] = {
                    "query": {"text": query, "model": PARK_MODEL} if method == "semantic" else {"text": query},
                    "filter": {"must": conditions},
                    "limit": min(DENSE_LIMIT, len(eligible)),
                    "with_payload": True,
                    "with_vector": False,
                }
                if method == "bm25":
                    body["using"] = BM25_FIELD
                response = await self._api.request(http, "POST", "/points/query", body)
                result = response.get("result") if response else None
                points = result.get("points") if isinstance(result, dict) else None
                if not isinstance(points, list) or len(points) > min(DENSE_LIMIT, len(eligible)):
                    raise ValueError("Invalid park candidates")
                # ② A remote score never changes the locally approved destination, season or content identity.
                scores: dict[str, float] = {}
                for point in points:
                    item = self._chunk(point, index_version)
                    identity, score = item["id"], point.get("score")
                    score_ok = (
                        type(score) in {int, float}
                        and (-1 <= score <= 1 if method == "semantic" else 0 <= score <= 1_000_000)
                        and math.isfinite(score)
                    )
                    if (
                        identity not in eligible
                        or identity in scores
                        or item["content_hash"] != eligible[identity]
                        or item["park_id"] != park_id
                        or destination_id not in item["destination_ids"]
                        or (season is not None and season not in item["seasons"] and "all" not in item["seasons"])
                        or not score_ok
                    ):
                        raise ValueError("Park candidate does not match scope")
                    scores[identity] = float(score)
                return SemanticResult("ready", scores)
        except PublicationError:
            return SemanticResult("index_mismatch")
        except (TimeoutError, httpx2.TimeoutException):
            return SemanticResult("timeout")
        except (ValueError, TypeError, KeyError):
            return SemanticResult("invalid_response")
        except Exception:
            return SemanticResult("unavailable")

    async def catalog(
        self,
        index_version: str,
        expected: Mapping[str, Mapping[str, Any]],
        *,
        with_vectors: bool = False,
    ) -> CatalogResult:
        """Read bounded pages, verifying every chunk against the compact release catalog before returning any."""
        if not self.configured:
            return CatalogResult("unconfigured")
        if not expected or len(expected) != self._chunk_count or len(expected) > 1000:
            return CatalogResult("index_mismatch")
        try:
            async with asyncio.timeout(PARK_CATALOG_SECONDS), self._factory() as http:
                # ① Publication is checked first; all pages must belong to that exact immutable generation.
                await self._ready(http, index_version)
                chunks: list[dict[str, Any]] = []
                seen: set[str] = set()
                offsets: set[str] = set()
                offset: str | int | None = None
                while True:
                    body: dict[str, object] = {
                        "filter": {
                            "must": [
                                {"key": "kind", "match": {"value": "chunk"}},
                                {"key": "index_version", "match": {"value": index_version}},
                                {"key": "profile", "match": {"value": PARK_PROFILE}},
                            ]
                        },
                        "limit": CATALOG_PAGE_SIZE,
                        "with_payload": True,
                        "with_vector": with_vectors,
                    }
                    if offset is not None:
                        body["offset"] = offset
                    document = await self._api.request(http, "POST", "/points/scroll", body)
                    result = document.get("result") if document else None
                    points = result.get("points") if isinstance(result, dict) else None
                    if not isinstance(result, dict) or not isinstance(points, list) or len(points) > CATALOG_PAGE_SIZE:
                        raise ValueError("Invalid park catalog page")
                    for point in points:
                        item = self._chunk(point, index_version)
                        identity = item["id"]
                        approved = expected.get(identity)
                        metadata = {key: value for key, value in item.items() if key != "text"}
                        metadata["record_hash"] = record_hash(item)
                        if identity in seen or approved is None or metadata != dict(approved):
                            raise ValueError("Catalog record is not approved")
                        vector = point.get("vector")
                        if with_vectors and not vector_ready(vector):
                            raise ValueError("Invalid hosted vector")
                        chunks.append({**item, "embedding": vector if with_vectors else []})
                        seen.add(identity)
                    # ② Reject loops, empty intermediate pages and excess records; never return partial data.
                    offset = result.get("next_page_offset")
                    if offset is None:
                        break
                    if (
                        not points
                        or type(offset) not in {str, int}
                        or len(str(offset)) > 100
                        or str(offset) in offsets
                        or len(seen) >= len(expected)
                    ):
                        raise ValueError("Invalid park catalog continuation")
                    offsets.add(str(offset))
                if seen != set(expected):
                    raise PublicationError("Park generation is incomplete")
                return CatalogResult("ready", sorted(chunks, key=lambda item: item["id"]))
        except PublicationError:
            return CatalogResult("index_mismatch")
        except (TimeoutError, httpx2.TimeoutException):
            return CatalogResult("timeout")
        except (ValueError, TypeError, KeyError):
            return CatalogResult("invalid_response")
        except Exception:
            return CatalogResult("unavailable")
