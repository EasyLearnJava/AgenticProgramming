"""Native BM25/dense publication is verified, isolated and idempotent without any local embedding model."""

import asyncio
import json
from typing import Any

import httpx2
import pytest

from nimbus.config import Settings
from nimbus.park_semantic import BM25_FIELD, PARK_DIMENSIONS, PARK_MODEL, manifest_id
from nimbus.park_text import to_embedding_text
from tests.unit.test_park_semantic import CHUNK, VERSION, answer, settings
from tools import setup_park_search as publish

PUBLIC_CHUNK: dict[str, Any] = dict(CHUNK)


class Collection:
    """An in-memory transport supports setup's real wire operations and explicit independent failure cases."""

    def __init__(self) -> None:
        """Start empty and retain writes and generated-vector count to prove repeat publication is cheap."""
        self.exists = False
        self.points: dict[str, dict[str, Any]] = {}
        self.indexes: dict[str, dict[str, Any]] = {}
        self.requests: list[httpx2.Request] = []
        self.failure = ""
        self.embeddings = 0

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Apply only the publisher operations; no model, network or secret handling is simulated by app code."""
        self.requests.append(request)
        body: dict[str, Any] = json.loads(request.content) if request.content else {}
        path = request.url.path.removeprefix("/collections/nimbus_park_guidance")
        if path == "" and request.method == "GET":
            if not self.exists:
                return httpx2.Response(404)
            size = 100 if self.failure == "dimensions" else PARK_DIMENSIONS
            return answer(
                {
                    "config": {"params": {"vectors": {"size": size, "distance": "Cosine"}}},
                    "payload_schema": self.indexes,
                }
            )
        if path == "" and request.method == "PUT":
            self.exists = True
            return answer(True)
        if path.startswith("/points/") and request.method == "GET":
            point = self.points.get(path.removeprefix("/points/"))
            return answer(point) if point else httpx2.Response(404)
        if path == "/index":
            schema = body["field_schema"]
            if isinstance(schema, dict):
                self.indexes[body["field_name"]] = {"data_type": "text", "params": dict(schema)}
                self.indexes[body["field_name"]]["params"]["scoring"] = {"type": "bm25"}
                if self.failure == "filter_only":
                    self.indexes[body["field_name"]]["params"]["scoring"] = False
            else:
                self.indexes[body["field_name"]] = {"data_type": "keyword"}
            return answer({"status": "completed"})
        if path == "/points" and request.method == "PUT":
            hosted = False
            for point in body["points"]:
                if isinstance(point["vector"], dict):
                    hosted = True
                    if self.failure == "upload":
                        return httpx2.Response(503, text="private provider error")
                    self.embeddings += 1
                    point["vector"] = publish.MARKER_VECTOR.copy()
                self.points[point["id"]] = point
            status = "acknowledged" if hosted and self.failure == "chunk_ack" else "completed"
            return answer({"status": status})
        if path == "/points" and request.method == "POST":
            result = [dict(self.points[key]) for key in body["ids"] if key in self.points]
            if self.failure == "missing":
                result = []
            elif result and self.failure == "vector":
                result[0]["vector"] = [0.5] * 2
            elif result and self.failure == "payload":
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
        if path == "/points/query":
            assert body["using"] == BM25_FIELD
            assert "model" not in body["query"]
            rows = [point for point in self.points.values() if point["payload"].get("kind") == "chunk"]
            if self.failure == "query":
                return httpx2.Response(400)
            return answer({"points": [{"id": rows[0]["id"], "score": 1.0}] if rows else []})
        raise AssertionError(f"Unexpected setup operation: {request.method} {path}")


@pytest.fixture
def public_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """One approved synthetic chunk lets tests inspect publication contracts without embedding the real corpus."""
    monkeypatch.setattr(publish, "read_public_chunks", lambda _settings: (VERSION, [PUBLIC_CHUNK]))


def run(provider: Collection, config: Settings | None = None) -> tuple[str, int]:
    """Run the real publisher and HTTP boundary against a deterministic collection transport."""
    return asyncio.run(
        publish.setup(config or settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)))
    )


def test_publication_stores_text_and_one_dense_embedding_then_enables_bm25(public_index: None) -> None:
    provider = Collection()
    assert run(provider) == (VERSION, 1)
    writes = [json.loads(request.content) for request in provider.requests if request.method == "PUT"]
    point_writes = [body for body in writes if "points" in body]
    hosted = point_writes[1]["points"][0]
    assert hosted["vector"] == {
        "text": to_embedding_text(PUBLIC_CHUNK["title"], PUBLIC_CHUNK["section"], PUBLIC_CHUNK["text"]),
        "model": PARK_MODEL,
    }
    assert hosted["payload"]["text"] == PUBLIC_CHUNK["text"]
    assert hosted["payload"]["source_url"] == PUBLIC_CHUNK["source_url"]
    assert hosted["payload"]["bm25_text"] == "spring fall spring fall wear suitable layer cold river water"
    assert "embedding" not in hosted["payload"]
    assert "expires_at" not in hosted["payload"]
    assert provider.indexes[BM25_FIELD]["params"]["scoring"] == {"type": "bm25"}
    assert point_writes[-1]["points"][0]["id"] == manifest_id(VERSION)
    assert provider.requests[-1].url.path.endswith(manifest_id(VERSION))
    assert all(request.method != "DELETE" for request in provider.requests)
    assert all("weather_cache" not in str(request.url) for request in provider.requests)
    assert provider.embeddings == 1


def test_repeating_verified_setup_does_not_regenerate_embeddings_or_rewrite_records(public_index: None) -> None:
    provider = Collection()
    run(provider)
    provider.requests.clear()
    assert run(provider) == (VERSION, 1)
    assert provider.embeddings == 1
    assert len(provider.points) == 3
    assert not any(request.method == "PUT" for request in provider.requests)


@pytest.mark.parametrize(
    "failure", ["upload", "chunk_ack", "missing", "vector", "payload", "count", "filter_only", "query"]
)
def test_failed_publication_never_publishes_readiness(public_index: None, failure: str) -> None:
    provider = Collection()
    provider.failure = failure
    with pytest.raises((ValueError, httpx2.HTTPStatusError)):
        run(provider)
    assert manifest_id(VERSION) not in provider.points


def test_retry_after_unconfirmed_upload_reuses_the_verified_hosted_vector(public_index: None) -> None:
    provider = Collection()
    provider.failure = "chunk_ack"
    with pytest.raises(ValueError, match="not confirmed"):
        run(provider)
    assert provider.embeddings == 1
    provider.failure = ""
    run(provider)
    assert provider.embeddings == 1
    assert manifest_id(VERSION) in provider.points


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


def test_published_generation_cannot_be_repaired_silently_after_data_loss(public_index: None) -> None:
    provider = Collection()
    run(provider)
    for identity in list(provider.points):
        if provider.points[identity]["payload"].get("kind") == "chunk":
            del provider.points[identity]
    provider.requests.clear()
    with pytest.raises(ValueError, match="published park generation is incomplete"):
        run(provider)
    assert not any(request.method == "PUT" for request in provider.requests)


def test_real_prepared_corpus_contains_text_without_local_vectors() -> None:
    version, chunks = publish.read_public_chunks(settings())
    assert len(version) == 16
    assert len(chunks) > 1
    assert all(chunk["text"] and "embedding" not in chunk for chunk in chunks)


def test_publication_requires_the_release_catalog_and_prepared_text_to_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publish, "load_prepared", lambda _path: {"index_version": "a", "chunks": []})
    monkeypatch.setattr(publish, "load_catalog", lambda _path: {"index_version": "b"})
    with pytest.raises(ValueError, match="versions differ"):
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
