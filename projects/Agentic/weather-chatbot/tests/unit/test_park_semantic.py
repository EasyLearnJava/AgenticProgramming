"""Hosted park retrieval verifies scope, publication, bounds and privacy without contacting Qdrant."""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.park_semantic import (
    PARK_MODEL,
    PARK_PROFILE,
    QdrantParkSearch,
    SemanticResult,
    chunk_payload,
    manifest_id,
    manifest_payload,
    point_id,
)

KEY = "private-park-provider-key"
QUESTION = "private-preparation-question"
VERSION = "ab" * 8
CHUNK = {
    "id": "zion-narrows-spring-1",
    "content_hash": "a" * 64,
    "park_id": "zion",
    "destination_ids": ["zion-narrows"],
    "seasons": ["spring", "fall"],
}


def settings(**overrides: Any) -> Settings:
    """An isolated configuration whose only external service is replaced with an HTTP recording."""
    return Settings(
        _env_file=None,
        **{
            "qdrant_url": "https://parks.us-east-1.aws.cloud.qdrant.io",
            "qdrant_api_key": SecretStr(KEY),
            "qdrant_collection": "nimbus_weather_cache",
            "parks_qdrant_collection": "nimbus_park_guidance",
            "parks_semantic_provider": "qdrant",
            **overrides,
        },
    )


def answer(result: object, status: int = 200) -> httpx2.Response:
    """A valid Qdrant response envelope around a chosen body."""
    return httpx2.Response(status, content=json.dumps({"status": "ok", "result": result}).encode())


def ready(**overrides: object) -> httpx2.Response:
    """A public manifest confirming the model, index version and total chunk count."""
    return answer({"id": manifest_id(VERSION), "payload": {**manifest_payload(VERSION, 4), **overrides}})


def point(**overrides: object) -> dict[str, object]:
    """One valid dense result whose text stays in SQLite rather than the provider payload."""
    return {
        "id": point_id(VERSION, str(CHUNK["id"])),
        "score": 0.89,
        "payload": chunk_payload(CHUNK, VERSION),
        **overrides,
    }


class Provider:
    """Keep requests for assertions and supply queued responses with no live transport."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        """Record the prepared response sequence."""
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Capture each request before returning or raising the next response."""
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def search(provider: Callable[..., Any], **configuration: Any) -> SemanticResult:
    """Run the real adapter with a synthetic client and one known eligible local chunk."""
    service = QdrantParkSearch(
        settings(**configuration),
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)),
        chunk_count=4,
    )
    return asyncio.run(
        service.search(
            QUESTION,
            index_version=VERSION,
            park_id="zion",
            destination_id="zion-narrows",
            season="spring",
            eligible={str(CHUNK["id"]): str(CHUNK["content_hash"])},
        )
    )


def test_hosted_query_is_versioned_filtered_and_uses_header_credentials() -> None:
    """Every hard filter precedes ranking; a successful response returns only an ID and its numeric score."""
    provider = Provider(ready(), answer({"points": [point()]}))
    with capture_logs() as logs:
        result = search(provider)
    assert result == SemanticResult("ready", {str(CHUNK["id"]): 0.89})
    assert len(provider.requests) == 2
    manifest, query = provider.requests
    assert manifest.method == "GET"
    assert manifest.url.path.endswith(manifest_id(VERSION))
    assert query.url.path == "/collections/nimbus_park_guidance/points/query"
    body = json.loads(query.content)
    assert body["query"] == {"text": QUESTION, "model": PARK_MODEL}
    assert body["limit"] == 1
    filters = body["filter"]["must"]
    assert {"key": "index_version", "match": {"value": VERSION}} in filters
    assert {"key": "park_id", "match": {"value": "zion"}} in filters
    assert {"key": "destination_ids", "match": {"value": "zion-narrows"}} in filters
    assert {"key": "seasons", "match": {"any": ["spring", "all"]}} in filters
    assert {"has_id": [point_id(VERSION, str(CHUNK["id"]))]} in filters
    assert {"key": "profile", "match": {"value": PARK_PROFILE}} in filters
    assert "score_threshold" not in body
    assert all(request.headers["api-key"] == KEY for request in provider.requests)
    assert KEY not in str(query.url)
    assert QUESTION not in json.dumps(logs)
    assert KEY not in json.dumps(logs)
    assert QUESTION not in repr(result)
    assert KEY not in repr(result)


@pytest.mark.parametrize("score", [-1, 0, 0.4, 1])
def test_bounded_low_scores_remain_available_for_fusion_diagnostics(score: float) -> None:
    """The caller decides its relevance threshold; below-cutoff candidates still have honest numeric scores."""
    result = search(Provider(ready(), answer({"points": [point(score=score)]})))
    assert result.scores == {str(CHUNK["id"]): score}


def test_empty_results_are_a_ready_semantic_miss_after_verified_publication() -> None:
    """A genuine no-match response is distinct from an unpublished corpus."""
    assert search(Provider(ready(), answer({"points": []}))) == SemanticResult("ready")


@pytest.mark.parametrize(
    "changes",
    [
        {"index_version": "another-version"},
        {"model": "another-model"},
        {"profile": "another-profile"},
        {"chunk_count": 3},
        {"chunk_count": True},
        {"schema": True},
    ],
)
def test_wrong_readiness_contract_stops_before_any_embedding(changes: dict[str, object]) -> None:
    provider = Provider(ready(**changes))
    assert search(provider).status == "index_mismatch"
    assert len(provider.requests) == 1


def test_missing_readiness_marker_stops_before_any_embedding() -> None:
    provider = Provider(httpx2.Response(404))
    assert search(provider).status == "index_mismatch"
    assert len(provider.requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"index_version": "wrong"},
        {"model": "wrong"},
        {"profile": "wrong"},
        {"content_hash": "b" * 64},
        {"park_id": "yosemite"},
        {"destination_ids": ["zion"]},
        {"destination_ids": "zion-narrows"},
        {"seasons": ["winter"]},
        {"seasons": "spring"},
        {"chunk_id": "unrecognized"},
    ],
)
def test_remote_candidates_cannot_override_local_scope(payload: dict[str, object]) -> None:
    candidate = point(payload={**chunk_payload(CHUNK, VERSION), **payload})
    assert search(Provider(ready(), answer({"points": [candidate]}))).status == "invalid_response"


@pytest.mark.parametrize("score", [True, "0.99", None, float("inf"), float("nan"), -1.1, 1.1, 10**400])
def test_remote_scores_must_be_finite_bounded_numbers(score: object) -> None:
    assert search(Provider(ready(), answer({"points": [point(score=score)]}))).status == "invalid_response"


def test_duplicate_or_wrong_point_ids_are_not_accepted() -> None:
    assert search(Provider(ready(), answer({"points": [point(id="wrong")]}))).status == "invalid_response"
    assert search(Provider(ready(), answer({"points": [point(), point()]}))).status == "invalid_response"


@pytest.mark.parametrize("status", [301, 401, 403, 429, 503])
def test_provider_errors_and_redirects_are_safe_fallbacks(status: int) -> None:
    provider = Provider(httpx2.Response(status, text=KEY + QUESTION, headers={"location": "https://example.com"}))
    with capture_logs() as logs:
        result = search(provider)
    assert result.status == "unavailable"
    assert len(provider.requests) == 1
    assert KEY not in json.dumps(logs)
    assert QUESTION not in json.dumps(logs)


def test_invalid_and_oversized_bodies_are_bounded_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    assert search(Provider(httpx2.Response(200, text="not-json"))).status == "invalid_response"
    monkeypatch.setattr("nimbus.park_semantic.MAX_RESPONSE_BYTES", 100)
    assert search(Provider(httpx2.Response(200, text="x" * 101))).status == "invalid_response"


def test_unconfigured_or_weather_cache_collection_never_contacts_qdrant() -> None:
    provider = Provider()
    assert search(provider, qdrant_api_key=None).status == "unconfigured"
    assert search(provider, parks_qdrant_collection="nimbus_weather_cache").status == "unconfigured"
    assert provider.requests == []


def test_separate_read_credential_takes_precedence() -> None:
    provider = Provider(ready(), answer({"points": []}))
    assert search(provider, parks_qdrant_api_key=SecretStr("park-read-key")).status == "ready"
    assert all(request.headers["api-key"] == "park-read-key" for request in provider.requests)


def test_timeout_and_cancellation_remain_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    """A timed-out optional provider falls back; cancelling the parent request is never swallowed."""
    monkeypatch.setattr("nimbus.park_semantic.PARK_SEARCH_SECONDS", 0.01)

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return ready()

    assert search(slow).status == "timeout"

    async def cancel(_request: httpx2.Request) -> httpx2.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        search(cancel)
