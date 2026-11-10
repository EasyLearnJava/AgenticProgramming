"""Hosted park retrieval verifies scope, publication, bounds and privacy without contacting Qdrant."""

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.park_semantic import (
    BM25_FIELD,
    COLBERT_MAX_TOKENS,
    COLBERT_MODEL,
    COLBERT_VECTOR,
    DENSE_VECTOR,
    PARK_DIMENSIONS,
    PARK_MODEL,
    PARK_PROFILE,
    QdrantParkSearch,
    SemanticResult,
    chunk_payload,
    manifest_id,
    manifest_payload,
    point_id,
)
from nimbus.park_text import record_hash, to_embedding_text

KEY = "private-park-provider-key"
QUESTION = "private-preparation-question"
VERSION = "ab" * 8
CHUNK = {
    "id": "zion-narrows-spring-1",
    "document_id": "narrows-guide",
    "park_id": "zion",
    "destination_ids": ["zion-narrows"],
    "seasons": ["spring", "fall"],
    "title": "Public Narrows safety",
    "section": "Spring and Fall",
    "text": "Wear suitable layers for cold river water.",
    "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
    "source_updated_at": "2026-09-17",
    "fetched_at": "2026-11-02T12:00:00Z",
}
CHUNK["content_hash"] = hashlib.sha256(
    to_embedding_text(str(CHUNK["title"]), str(CHUNK["section"]), str(CHUNK["text"])).encode()
).hexdigest()


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
    """One valid hosted result with full public text and protected provenance in its payload."""
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
    """Run the real adapter with a synthetic client and one approved chunk identity."""
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
    assert body["using"] == DENSE_VECTOR
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


@pytest.mark.parametrize(
    "changes",
    [
        {"text": "Different internally valid public passage."},
        {"park_id": "yosemite"},
        {"destination_ids": ["zion"]},
        {"seasons": ["winter"]},
    ],
)
def test_self_consistent_candidates_must_still_match_the_requested_scope(changes: dict[str, Any]) -> None:
    """A provider can return valid records from another scope; integrity alone does not authorize retrieval."""
    changed = {**CHUNK, **changes}
    changed["content_hash"] = hashlib.sha256(
        to_embedding_text(str(changed["title"]), str(changed["section"]), str(changed["text"])).encode()
    ).hexdigest()
    candidate = point(payload=chunk_payload(changed, VERSION))
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


def test_bm25_runs_native_text_scoring_without_embedding_model() -> None:
    """Lexical search shares the exact semantic scope but uses Qdrant's scored payload index."""
    provider = Provider(ready(), answer({"points": [point(score=8.5)]}))
    service = QdrantParkSearch(
        settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)), chunk_count=4
    )
    result = asyncio.run(
        service.search(
            "warm layer",
            index_version=VERSION,
            park_id="zion",
            destination_id="zion-narrows",
            season="spring",
            eligible={str(CHUNK["id"]): str(CHUNK["content_hash"])},
            method="bm25",
        )
    )
    assert result.scores == {CHUNK["id"]: 8.5}
    body = json.loads(provider.requests[-1].content)
    assert body["query"] == {"text": "warm layer"}
    assert body["using"] == BM25_FIELD
    assert body["params"] == {"idf": {"corpus": body["filter"]}}
    assert "model" not in body["query"]
    assert {"key": "seasons", "match": {"any": ["spring", "all"]}} in body["filter"]["must"]


def catalog(provider: Provider, *, vectors: bool = False) -> Any:
    """Read a one-record catalog through the real boundary using its separately approved metadata."""
    service = QdrantParkSearch(
        settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)), chunk_count=1
    )
    approved = {key: value for key, value in CHUNK.items() if key != "text"}
    approved["record_hash"] = record_hash(CHUNK)
    return asyncio.run(service.catalog(VERSION, {str(CHUNK["id"]): approved}, with_vectors=vectors))


def catalog_ready() -> httpx2.Response:
    """The one-chunk publication marker used by catalog reads."""
    return answer({"id": manifest_id(VERSION), "payload": manifest_payload(VERSION, 1)})


def test_catalog_reads_the_hosted_text_and_optionally_the_actual_hosted_vector() -> None:
    """Knowledge displays the actual Qdrant record; no legacy embedding is manufactured or loaded."""
    provider = Provider(
        catalog_ready(),
        answer({"points": [point(vector={DENSE_VECTOR: [0.5] * PARK_DIMENSIONS})], "next_page_offset": None}),
    )
    result = catalog(provider, vectors=True)
    assert result.status == "ready"
    assert result.chunks == [{**CHUNK, "embedding": [0.5] * PARK_DIMENSIONS}]
    body = json.loads(provider.requests[-1].content)
    assert body["with_vector"] == [DENSE_VECTOR]
    assert body["filter"]["must"] == [
        {"key": "kind", "match": {"value": "chunk"}},
        {"key": "index_version", "match": {"value": VERSION}},
        {"key": "profile", "match": {"value": PARK_PROFILE}},
    ]
    without = catalog(Provider(catalog_ready(), answer({"points": [point()], "next_page_offset": None})))
    assert without.status == "ready"
    assert without.chunks[0]["embedding"] == []


@pytest.mark.parametrize(
    ("field", "value"), [("text", "Unapproved treatment advice"), ("source_url", "https://example.com")]
)
def test_changed_source_text_or_citation_cannot_reach_the_knowledge_pages(field: str, value: str) -> None:
    """Remote source content must match the reviewed record, not merely its displayed chunk ID."""
    candidate = point(payload={**chunk_payload(CHUNK, VERSION), field: value})
    result = catalog(Provider(catalog_ready(), answer({"points": [candidate], "next_page_offset": None})))
    assert result.status == "invalid_response"
    assert result.chunks == []


def test_valid_but_unapproved_metadata_also_fails_closed() -> None:
    """An internally consistent changed source record still cannot override release-approved provenance."""
    changed = {**CHUNK, "source_updated_at": "2026-10-01"}
    candidate = point(payload=chunk_payload(changed, VERSION))
    assert catalog(Provider(catalog_ready(), answer({"points": [candidate]}))).status == "invalid_response"


@pytest.mark.parametrize(("field", "value"), [("bm25_text", "invented indexed keywords"), ("record_hash", "a" * 64)])
def test_search_rejects_changed_derived_fields_even_when_source_text_is_unchanged(field: str, value: str) -> None:
    """A valid passage cannot carry a forged keyword representation or full-record integrity marker."""
    candidate = point(payload={**chunk_payload(CHUNK, VERSION), field: value})
    result = search(Provider(ready(), answer({"points": [candidate]})))
    assert result.status == "invalid_response"
    assert result.scores == {}


@pytest.mark.parametrize("vector", [[1.0], [0.0] * PARK_DIMENSIONS, [float("nan")] * PARK_DIMENSIONS])
def test_knowledge_vector_preview_rejects_invalid_remote_vectors(vector: object) -> None:
    result = catalog(
        Provider(catalog_ready(), answer({"points": [point(vector={DENSE_VECTOR: vector})]})), vectors=True
    )
    assert result.status == "invalid_response"
    assert result.chunks == []


@pytest.mark.parametrize(
    ("page", "status"),
    [
        ({"points": [], "next_page_offset": None}, "index_mismatch"),
        ({"points": [], "next_page_offset": "next"}, "invalid_response"),
        ({"points": [point(), point()]}, "invalid_response"),
        ({"points": [point()], "next_page_offset": "next"}, "invalid_response"),
    ],
)
def test_incomplete_duplicate_and_overlong_catalogs_are_never_returned(page: dict[str, Any], status: str) -> None:
    result = catalog(Provider(catalog_ready(), answer(page)))
    assert result.status == status
    assert result.chunks == []


def test_catalog_deadline_discards_partial_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catalog reads have a whole-operation bound, independent of per-request timeouts."""
    monkeypatch.setattr("nimbus.park_semantic.PARK_CATALOG_SECONDS", 0.01)

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return catalog_ready()

    service = QdrantParkSearch(
        settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(slow)), chunk_count=1
    )
    approved = {key: value for key, value in CHUNK.items() if key != "text"}
    approved["record_hash"] = record_hash(CHUNK)
    result = asyncio.run(service.catalog(VERSION, {str(CHUNK["id"]): approved}))
    assert result.status == "timeout"
    assert result.chunks == []


def test_health_checks_publication_without_embedding_or_reading_text() -> None:
    provider = Provider(ready())
    service = QdrantParkSearch(
        settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)), chunk_count=4
    )
    assert asyncio.run(service.health(VERSION)) == "ready"
    assert len(provider.requests) == 1
    assert provider.requests[0].method == "GET"


def rerank(provider: Callable[..., Any], **overrides: Any) -> SemanticResult:
    """Exercise the actual reranker against a strictly admitted source shortlist."""
    service = QdrantParkSearch(
        settings(), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)), chunk_count=4
    )
    scope: dict[str, Any] = {
        "index_version": VERSION,
        "park_id": "zion",
        "destination_id": "zion-narrows",
        "season": "spring",
        "eligible": {str(CHUNK["id"]): str(CHUNK["content_hash"])},
        **overrides,
    }
    return asyncio.run(service.rerank(QUESTION, **scope))


def test_colbert_rerank_uses_only_the_admitted_shortlist_and_private_query_stays_out_of_logs() -> None:
    provider = Provider(ready(), answer({"points": [point(score=24.5)]}))
    with capture_logs() as logs:
        result = rerank(provider)
    assert result == SemanticResult("ready", {str(CHUNK["id"]): 24.5})
    body = json.loads(provider.requests[-1].content)
    assert body["query"] == {"text": QUESTION, "model": COLBERT_MODEL}
    assert body["using"] == COLBERT_VECTOR
    assert body["limit"] == 1
    assert {"has_id": [point_id(VERSION, str(CHUNK["id"]))]} in body["filter"]["must"]
    assert {"key": "seasons", "match": {"any": ["spring", "all"]}} in body["filter"]["must"]
    assert not body["with_vector"]
    assert "params" not in body
    assert QUESTION not in json.dumps(logs) + repr(result)
    assert KEY not in json.dumps(logs) + repr(result)


@pytest.mark.parametrize("score", [True, "20", None, float("inf"), float("nan"), -513, 513, 10**400])
def test_colbert_scores_are_finite_bounded_numbers(score: object) -> None:
    assert rerank(Provider(ready(), answer({"points": [point(score=score)]}))).status == "invalid_response"


@pytest.mark.parametrize("score", [-COLBERT_MAX_TOKENS, -0.1, 0, 30.5, COLBERT_MAX_TOKENS])
def test_colbert_scores_are_maxsim_not_cosine_probabilities(score: float) -> None:
    assert rerank(Provider(ready(), answer({"points": [point(score=score)]}))).scores == {str(CHUNK["id"]): score}


@pytest.mark.parametrize("points", [[], [point(), point()], [point(id="unknown")]])
def test_colbert_requires_the_exact_complete_candidate_set(points: list[dict[str, object]]) -> None:
    result = rerank(Provider(ready(), answer({"points": points})))
    assert result.status == "invalid_response"
    assert result.scores == {}


def test_colbert_never_ranks_an_unbounded_shortlist() -> None:
    provider = Provider()
    assert rerank(provider, eligible={str(i): "a" * 64 for i in range(33)}).status == "invalid_response"
    assert provider.requests == []


def test_colbert_rejects_internally_valid_but_out_of_scope_records() -> None:
    changed = {**CHUNK, "park_id": "yosemite"}
    candidate = point(payload=chunk_payload(changed, VERSION), score=20)
    assert rerank(Provider(ready(), answer({"points": [candidate]}))).status == "invalid_response"


def test_colbert_timeout_cancels_work_and_parent_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nimbus.park_semantic.PARK_SEARCH_SECONDS", 0.01)
    cancelled = False

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        finally:
            cancelled = True
        return ready()

    assert rerank(slow).status == "timeout"
    assert cancelled

    async def cancel(_request: httpx2.Request) -> httpx2.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        rerank(cancel)
