"""Recorded Qdrant scores exercise real park ranking offline, with strict corpus, scope and privacy boundaries."""

import asyncio
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx2
import pytest

from nimbus.park_ingest import compact_chunk, load_prepared
from nimbus.park_models import ParkChunk
from nimbus.park_semantic import PARK_MODEL, PARK_PROFILE, CatalogResult, SemanticResult
from tools.eval_parks import PROJECT_ROOT
from tools.park_replay import (
    RecordedParkStore,
    RecordingParkStore,
    replay_park_cases,
    request_key,
)

PRIVATE = "private question must never appear in recording"


def recording(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    """Create a controlled score recording against the approved text-only corpus."""
    corpus = load_prepared(PROJECT_ROOT / "data/parks/prepared.json")
    item = next(chunk for chunk in corpus["chunks"] if "zion-narrows" in chunk["destination_ids"])
    scope = {
        "index_version": corpus["index_version"],
        "park_id": "zion",
        "destination_id": "zion-narrows",
        "season": None,
        "eligible": {item["id"]: item["content_hash"]},
        "method": "semantic",
    }
    cases = tmp_path / "cases.json"
    cases.write_text("[]", encoding="utf-8")
    document = {
        "schema_version": 1,
        "index_version": corpus["index_version"],
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "cases_sha256": hashlib.sha256(cases.read_bytes()).hexdigest(),
        "recorded_at": "2026-11-10T20:00:00Z",
        "records": {request_key(PRIVATE, scope): {"method": "semantic", "scores": {item["id"]: 0.8}}},
    }
    path = tmp_path / "recording.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path, cases, scope, document


def test_same_request_replays_scores_and_changed_question_fails_without_exposing_text(tmp_path: Path) -> None:
    """A miss in the recording catalog must not turn into an invented keyword or semantic match."""
    path, cases, scope, _ = recording(tmp_path)
    store = RecordedParkStore(path, cases_path=cases)
    expected_id = next(iter(scope["eligible"]))
    assert asyncio.run(store.search(PRIVATE, **scope)) == SemanticResult("ready", {expected_id: 0.8})
    assert asyncio.run(store.search("another question", **scope)).status == "index_mismatch"
    assert PRIVATE not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("park_id", "yosemite"),
        ("destination_id", "zion"),
        ("season", "winter"),
        ("index_version", "f" * 16),
        ("method", "bm25"),
        ("eligible", {}),
    ],
)
def test_every_scope_field_and_search_method_are_bound_to_the_recording(
    tmp_path: Path, field: str, value: object
) -> None:
    """The same words cannot reuse scores from another destination, season, method or corpus."""
    path, cases, scope, _ = recording(tmp_path)
    store = RecordedParkStore(path, cases_path=cases)
    assert asyncio.run(store.search(PRIVATE, **{**scope, field: value})).status == "index_mismatch"


@pytest.mark.parametrize("field", ["index_version", "model", "profile", "cases_sha256"])
def test_changed_contract_requires_reviewed_new_recordings(tmp_path: Path, field: str) -> None:
    """A stale corpus or suite cannot inherit a previous provider result silently."""
    path, cases, _, document = recording(tmp_path)
    document[field] = "changed"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="retrieval contract"):
        RecordedParkStore(path, cases_path=cases)


@pytest.mark.parametrize("score", [True, float("nan"), float("inf"), -1.1, 1.1])
def test_recorded_semantic_scores_have_real_finite_bounds(tmp_path: Path, score: object) -> None:
    """Corrupt scores cannot falsely improve a replay ranking."""
    path, cases, scope, document = recording(tmp_path)
    document["records"][request_key(PRIVATE, scope)]["scores"] = {next(iter(scope["eligible"])): score}
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="recorded park scores"):
        RecordedParkStore(path, cases_path=cases)


def test_catalog_returns_verified_public_text_but_never_fabricates_vectors(tmp_path: Path) -> None:
    """Replay source text has its full provenance; only the real Knowledge page may obtain hosted vectors."""
    path, cases, _, _ = recording(tmp_path)
    store = RecordedParkStore(path, cases_path=cases)
    expected = {item["id"]: compact_chunk(ParkChunk.model_validate(item)) for item in store.prepared["chunks"]}
    result = asyncio.run(store.catalog(store.prepared["index_version"], expected))
    assert result.status == "ready"
    assert len(result.chunks) == 40
    assert all(item["text"] and item["source_url"].startswith("https://www.nps.gov/") for item in result.chunks)
    assert all(item["embedding"] == [] for item in result.chunks)
    assert (
        asyncio.run(store.catalog(store.prepared["index_version"], expected, with_vectors=True)).status
        == "index_mismatch"
    )
    assert asyncio.run(store.catalog("wrong", expected)).status == "index_mismatch"


def test_recorder_keeps_only_successful_scores_and_no_question_text(tmp_path: Path) -> None:
    """Provider failures stay failures instead of becoming empty successful recordings."""
    _, _, scope, _ = recording(tmp_path)
    identity = next(iter(scope["eligible"]))

    class Source:
        """A fixed provider boundary independent of the recorder implementation."""

        configured = True

        async def catalog(
            self, version: str, expected: Mapping[str, Mapping[str, Any]], *, with_vectors: bool = False
        ) -> CatalogResult:
            """Supply a successful catalog boundary for the recorder test."""
            return CatalogResult("ready")

        async def search(self, query: str, **kwargs: Any) -> SemanticResult:
            """Return controlled scores or a failure without any real provider request."""
            return SemanticResult("ready", {identity: 0.8}) if query == PRIVATE else SemanticResult("timeout")

        async def health(self, version: str) -> str:
            """The test double is configured independently of a live cluster."""
            return "ready"

    store = RecordingParkStore(Source())
    assert asyncio.run(store.search(PRIVATE, **scope)).status == "ready"
    assert asyncio.run(store.search("provider timeout", **scope)).status == "timeout"
    assert len(store.records) == 1
    assert PRIVATE not in json.dumps(store.records)
    assert "provider timeout" not in json.dumps(store.records)


def test_approved_provider_recordings_replay_all_cases_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """This guards ranker regression on recorded real results; it is explicitly not a fresh Qdrant quality run."""

    async def no_http(*args: object, **kwargs: object) -> httpx2.Response:
        pytest.fail("Recorded park replay attempted a live request")

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", no_http)
    rows = asyncio.run(replay_park_cases())
    assert len(rows) == 47
    assert all(row["outcome"] == "pass" for row in rows)
    assert all(row["checks"] == ["recorded_qdrant_retrieval"] for row in rows)
