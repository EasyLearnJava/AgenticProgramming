"""Hosted park publication is isolated, verified and never announces an incomplete index as ready."""

import asyncio
import json
from typing import Any

import httpx2
import pytest

from nimbus.config import Settings
from nimbus.park_embeddings import to_embedding_text
from nimbus.park_semantic import PARK_DIMENSIONS, PARK_MODEL, manifest_id
from tests.unit.test_park_semantic import CHUNK, VERSION, answer, settings
from tools import setup_park_search as publish

PUBLIC_CHUNK: dict[str, Any] = {
    **CHUNK,
    "title": "Public Narrows safety",
    "section": "Spring and Fall",
    "text": "Wear suitable layers for cold river water.",
    "embedding": [0.5] * PARK_DIMENSIONS,
}


class Collection:
    """An in-memory Qdrant collection supporting only the explicit setup command's wire operations."""

    def __init__(self) -> None:
        """Start with no collection or points, and opt-in protocol failures for publication tests."""
        self.exists = False
        self.points: dict[str, dict[str, Any]] = {}
        self.requests: list[httpx2.Request] = []
        self.failure = ""

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Apply writes and generate hosted vectors without credentials, external calls or local ML."""
        self.requests.append(request)
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        path = request.url.path.removeprefix("/collections/nimbus_park_guidance")
        if path == "" and request.method == "GET":
            if not self.exists:
                return httpx2.Response(404)
            size = 100 if self.failure == "dimensions" else PARK_DIMENSIONS
            return answer({"config": {"params": {"vectors": {"size": size, "distance": "Cosine"}}}})
        if path == "" and request.method == "PUT":
            self.exists = True
            return answer(True)
        if path.startswith("/points/") and request.method == "GET":
            point = self.points.get(path.removeprefix("/points/"))
            return answer(point) if point else httpx2.Response(404)
        if path == "/index":
            return answer({"status": "completed"})
        if path == "/points" and request.method == "PUT":
            for point in body["points"]:
                if isinstance(point["vector"], dict):
                    if self.failure == "upload":
                        return httpx2.Response(503, text="private provider error")
                    point["vector"] = publish.MARKER_VECTOR.copy()
                self.points[point["id"]] = point
            return answer({"status": "acknowledged" if self.failure == "ack" else "completed"})
        if path == "/points" and request.method == "POST":
            result = [dict(self.points[key]) for key in body["ids"] if key in self.points]
            if self.failure == "missing":
                result = []
            elif self.failure == "vector":
                result[0]["vector"] = [0.5] * 2
            elif self.failure == "payload":
                result[0] = {**result[0], "payload": {**result[0]["payload"], "content_hash": "wrong"}}
            return answer(result)
        if path == "/points/count":
            selected = list(self.points.values())
            for condition in body.get("filter", {}).get("must", []):
                selected = [
                    point for point in selected if point["payload"].get(condition["key"]) == condition["match"]["value"]
                ]
            count = len(selected)
            if body.get("filter") and self.failure == "count":
                count += 1
            return answer({"count": count})
        raise AssertionError(f"Unexpected setup operation: {request.method} {path}")


@pytest.fixture
def public_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use one approved synthetic chunk so the tests check provider contracts rather than corpus size."""
    monkeypatch.setattr(publish, "read_public_chunks", lambda _settings: (VERSION, [PUBLIC_CHUNK]))


def run(provider: Collection, config: Settings | None = None) -> tuple[str, int]:
    """Run publication with the real HTTP adapter and an isolated synthetic transport."""
    return asyncio.run(
        publish.setup(config or settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)))
    )


def test_publication_uses_hosted_embeddings_and_marks_ready_only_after_verification(public_index: None) -> None:
    provider = Collection()
    assert run(provider) == (VERSION, 1)
    writes = [json.loads(request.content) for request in provider.requests if request.method == "PUT"]
    point_writes = [body for body in writes if "points" in body]
    hosted = point_writes[1]["points"][0]
    assert hosted["vector"] == {
        "text": to_embedding_text(PUBLIC_CHUNK["title"], PUBLIC_CHUNK["section"], PUBLIC_CHUNK["text"]),
        "model": PARK_MODEL,
    }
    assert hosted["vector"] != PUBLIC_CHUNK["embedding"]
    assert "text" not in hosted["payload"]
    assert "expires_at" not in hosted["payload"]
    assert point_writes[-1]["points"][0]["id"] == manifest_id(VERSION)
    assert provider.requests[-1].url.path.endswith(manifest_id(VERSION))
    assert all(request.method != "DELETE" for request in provider.requests)
    assert all("weather_cache" not in str(request.url) for request in provider.requests)
    # Repeating setup retains one public chunk and its two separate metadata points, without accumulating duplicates.
    assert run(provider) == (VERSION, 1)
    assert len(provider.points) == 3


@pytest.mark.parametrize("failure", ["upload", "ack", "missing", "vector", "payload", "count"])
def test_failed_publication_never_publishes_readiness(public_index: None, failure: str) -> None:
    provider = Collection()
    provider.failure = failure
    with pytest.raises((ValueError, httpx2.HTTPStatusError)):
        run(provider)
    assert manifest_id(VERSION) not in provider.points


@pytest.mark.parametrize("failure", ["dimensions", "unmanaged", "ownership"])
def test_existing_unmanaged_or_incompatible_collections_are_not_modified(public_index: None, failure: str) -> None:
    provider = Collection()
    provider.exists = True
    if failure == "dimensions":
        provider.failure = failure
    elif failure == "unmanaged":
        provider.points["another-app"] = {"payload": {"kind": "private"}}
    else:
        provider.points[publish.OWNER_ID] = {"payload": {"kind": "foreign"}}
    with pytest.raises(ValueError, match="collection"):
        run(provider)
    assert not any(request.method == "PUT" for request in provider.requests)


def test_cache_collection_collision_is_rejected_before_any_provider_request(public_index: None) -> None:
    provider = Collection()
    with pytest.raises(ValueError, match="Configure a dedicated park collection"):
        run(provider, settings(parks_qdrant_collection="nimbus_weather_cache"))
    assert provider.requests == []


def test_real_local_artifact_is_tokenizer_prepared_for_hosted_reembedding() -> None:
    """The committed artifact can publish without fetching weights or loading sentence-transformers."""
    version, chunks = publish.read_public_chunks(settings())
    assert len(version) == 16
    assert len(chunks) > 1
    assert all(len(chunk["embedding"]) == PARK_DIMENSIONS for chunk in chunks)


@pytest.mark.parametrize("change", ["model", "dimensions", "vectors", "missing"])
def test_setup_refuses_artifacts_without_the_tokenizer_preparation_contract(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    """A lexical-only artifact is not silently truncated by a hosted model with a bounded token context."""
    catalog: dict[str, Any] = {
        "available": True,
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2@revision",
        "dimensions": PARK_DIMENSIONS,
        "index_version": VERSION,
        "chunks": [PUBLIC_CHUNK],
    }
    if change == "model":
        catalog["embedding_model"] = "another-model"
    elif change == "dimensions":
        catalog["dimensions"] = 10
    elif change == "vectors":
        catalog["chunks"] = [{**PUBLIC_CHUNK, "embedding": []}]
    else:
        catalog["available"] = False

    class Knowledge:
        """Return only the synthetic ingestion contract under review."""

        def inspection(self) -> dict[str, Any]:
            return catalog

    monkeypatch.setattr(publish, "ParkKnowledge", lambda _path: Knowledge())
    with pytest.raises(ValueError, match="tokenizer-prepared MiniLM"):
        publish.read_public_chunks(settings())


def test_setup_deadline_stops_work_without_publishing_a_marker(
    public_index: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publish, "SETUP_SECONDS", 0.01)

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return answer(True)

    with pytest.raises(TimeoutError):
        asyncio.run(publish.setup(settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(slow))))
