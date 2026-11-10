"""Contracts for Qdrant-backed park routing, scoped hybrid ranks, integrity and unavailable states."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from nimbus.parks import Destination, ParkChunk, ParkKnowledge
from tests.park_fakes import FakeParkStore, fixture_knowledge, knowledge_for


def destination(identity: str, name: str, aliases: list[str], park: str = "zion") -> dict[str, Any]:
    """A checked reference location used only in the test index."""
    return {
        "id": identity,
        "park_id": park,
        "name": name,
        "aliases": aliases,
        "latitude": 37.3,
        "longitude": -112.9,
        "time_zone": "America/Denver",
        "forecast_reference": "Test trailhead reference, not the whole trail",
        "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
    }


def chunk(identity: str, text: str, destinations: list[str], **changes: Any) -> dict[str, Any]:
    """A passage whose scope and provenance can be varied independently."""
    return {
        "id": identity,
        "document_id": "narrows-guide",
        "park_id": "zion",
        "destination_ids": destinations,
        "title": "Narrows guide",
        "section": "Preparation",
        "text": text,
        "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
        "source_updated_at": "2026-09-17",
        "fetched_at": "2026-11-02T12:00:00Z",
        "content_hash": "a" * 64,
        "seasons": ["all"],
        **changes,
    }


def write_index(path: Path, passages: list[dict[str, Any]]) -> Path:
    """Prepare test metadata; tests inject the corresponding provider instead of opening a database."""
    knowledge_for(path.parent, passages or [chunk("item", "Clothing guidance.", ["zion"])])
    return path.parent / "catalog.json"


def test_resolution_prefers_named_trail_and_preserves_ambiguity() -> None:
    knowledge = fixture_knowledge()
    assert knowledge.resolve("Zion Narrows tomorrow")["destination"]["id"] == "zion-narrows"
    assert knowledge.resolve("Zion or Yosemite")["status"] == "ambiguous"
    assert knowledge.resolve("Yellowstone")["status"] == "unsupported"
    assert knowledge.resolve("horizon")["status"] == "unsupported"


def test_scope_filters_precede_both_qdrant_rankers(tmp_path: Path) -> None:
    knowledge = knowledge_for(
        tmp_path,
        [
            chunk("right", "Warm clothing and layers for cold water.", ["zion-narrows"]),
            chunk("wrong", "Warm clothing.", ["yosemite"], park_id="yosemite", document_id="other"),
            chunk("other-zion", "Warm clothing.", ["zion"]),
        ],
    )
    result = asyncio.run(knowledge.search("zion-narrows", "What clothing should I pack?"))
    assert result["status"] == "found"
    assert [item["id"] for item in result["passages"]] == ["right"]
    assert result["passages"][0]["source_updated_at"] == "2026-09-17"
    calls = cast(FakeParkStore, knowledge.store).calls
    assert [call["method"] for call in calls] == ["catalog", "bm25", "semantic"]
    assert all(set(call["eligible"]) == {"right"} for call in calls if "eligible" in call)
    assert result["keyword_provider"] == result["semantic_provider"] == "qdrant"


def test_season_filters_both_rankers_and_retains_year_round_guidance(tmp_path: Path) -> None:
    knowledge = knowledge_for(
        tmp_path,
        [
            chunk("winter", "Winter clothing layers drysuit.", ["zion-narrows"], seasons=["winter"]),
            chunk("summer", "Summer clothing layers.", ["zion-narrows"], seasons=["summer"]),
            chunk("always", "Clothing stays dry in waterproof bags.", ["zion-narrows"]),
        ],
    )
    result = asyncio.run(knowledge.search("zion-narrows", "clothing", date(2027, 1, 10)))
    assert {item["id"] for item in result["passages"]} == {"winter", "always"}
    assert all(call["season"] == "winter" for call in cast(FakeParkStore, knowledge.store).calls if "eligible" in call)


def test_irrelevant_and_unsupported_queries_return_no_evidence(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("pack", "Warm clothing.", ["zion-narrows"])])
    assert asyncio.run(knowledge.search("zion-narrows", "restaurant menu"))["status"] == "not_found"
    store = cast(FakeParkStore, knowledge.store)
    store.calls.clear()
    assert asyncio.run(knowledge.search("invented", "clothing"))["status"] == "unsupported"
    assert not store.calls


def test_missing_corrupt_and_incompatible_catalogs_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert ParkKnowledge(missing).resolve("Zion")["status"] == "unavailable"
    assert not missing.exists()
    missing.write_text("not JSON", encoding="utf-8")
    assert asyncio.run(ParkKnowledge(missing).search("zion", "clothing"))["status"] == "unavailable"
    path = write_index(tmp_path / "catalog.json", [chunk("item", "Clothing.", ["zion"])])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema_version"] = 999
    path.write_text(json.dumps(data), encoding="utf-8")
    assert ParkKnowledge(path).resolve("Zion")["status"] == "unavailable"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("text", "Substituted unreviewed instructions."),
        ("source_url", "https://www.nps.gov/zion/fake.htm"),
        ("source_updated_at", "2026-10-01"),
    ],
)
def test_remote_text_and_provenance_must_match_approved_record_hash(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Warm clothing.", ["zion"])])
    store = cast(FakeParkStore, knowledge.store)
    store.chunks[0][field] = value
    result = asyncio.run(knowledge.search("zion", "clothing"))
    assert result["status"] == "unavailable"
    assert result["keyword_status"] == "invalid_response"
    assert result["passages"] == []
    assert [call["method"] for call in store.calls] == ["catalog"]


def test_missing_remote_record_is_an_index_mismatch(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])
    cast(FakeParkStore, knowledge.store).chunks.clear()
    assert asyncio.run(knowledge.inspection())["status"] == "index_mismatch"


@pytest.mark.parametrize("stage", ["catalog", "keyword"])
def test_qdrant_outage_cannot_silently_use_local_text_or_keyword_scores(tmp_path: Path, stage: str) -> None:
    knowledge = knowledge_for(
        tmp_path,
        [chunk("item", "Clothing.", ["zion"])],
        catalog_status="timeout" if stage == "catalog" else "ready",
        keyword_status="timeout" if stage == "keyword" else "ready",
    )
    result = asyncio.run(knowledge.search("zion", "clothing"))
    assert result["status"] == "unavailable"
    assert result["retrieval_mode"] == "none"
    assert result["passages"] == []
    assert all(call["method"] != "semantic" for call in cast(FakeParkStore, knowledge.store).calls)


def test_semantic_failure_keeps_successful_qdrant_bm25_results(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])], semantic_status="timeout")
    result = asyncio.run(knowledge.search("zion", "clothing"))
    assert result["status"] == "found"
    assert result["keyword_status"] == "ready"
    assert result["semantic_status"] == "timeout"
    assert result["retrieval_mode"] == "lexical"


def test_cumulative_remote_delays_keep_bm25_before_the_chat_tool_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real awaited delays cover the residual budget, not an immediately returned timeout status."""
    from nimbus import park_tools, parks

    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])
    store = cast(FakeParkStore, knowledge.store)
    catalog, search = store.catalog, store.search
    semantic_cancelled = False
    monkeypatch.setattr(parks, "RETRIEVAL_SECONDS", 0.3)
    # Resetting the semantic budget after 0.2 seconds would overrun this outer deadline.
    monkeypatch.setattr(park_tools, "PARK_TOOL_SECONDS", 0.45)

    async def delayed_catalog(*args: Any, **kwargs: Any) -> Any:
        """Spend some of the shared budget reading the source records."""
        await asyncio.sleep(0.1)
        return await catalog(*args, **kwargs)

    async def delayed_search(*args: Any, **kwargs: Any) -> Any:
        """Finish BM25, then require the optional hosted semantic work to be cancelled."""
        nonlocal semantic_cancelled
        if kwargs["method"] == "bm25":
            await asyncio.sleep(0.1)
            return await search(*args, **kwargs)
        try:
            await asyncio.sleep(2)
        finally:
            semantic_cancelled = True
        return await search(*args, **kwargs)

    monkeypatch.setattr(store, "catalog", delayed_catalog)
    monkeypatch.setattr(store, "search", delayed_search)
    content, _record = asyncio.run(
        park_tools._run_knowledge("search_park_guidance", lambda: knowledge.search("zion", "clothing"))
    )
    result = json.loads(content)
    assert semantic_cancelled
    assert result["status"] == "found"
    assert result["retrieval_mode"] == "lexical"
    assert result["semantic_status"] == "timeout"
    assert [item["id"] for item in result["passages"]] == ["item"]


def test_parent_cancellation_during_semantic_search_still_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only our own optional-stage deadline is recovered; a cancelled request remains cancelled."""
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])
    store = cast(FakeParkStore, knowledge.store)
    search = store.search

    async def cancelled_semantic(*args: Any, **kwargs: Any) -> Any:
        """Cancel after the required ranker has already produced reusable evidence."""
        if kwargs["method"] == "semantic":
            raise asyncio.CancelledError
        return await search(*args, **kwargs)

    monkeypatch.setattr(store, "search", cancelled_semantic)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(knowledge.search("zion", "clothing"))


def test_explicit_lexical_mode_uses_qdrant_without_embedding_a_query(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])], mode="lexical")
    result = asyncio.run(knowledge.search("zion", "clothing"))
    assert result["semantic_status"] == "disabled"
    assert result["retrieval_mode"] == "lexical"
    assert [call["method"] for call in cast(FakeParkStore, knowledge.store).calls] == ["catalog", "bm25"]


def test_no_credentials_never_produces_a_local_bm25_answer() -> None:
    knowledge = ParkKnowledge(Path("data/parks/catalog.json"))
    assert knowledge.resolve("Zion")["status"] == "resolved"
    result = asyncio.run(knowledge.search("zion", "clothing"))
    assert result["status"] == "unavailable"
    assert result["keyword_status"] == "unconfigured"


def test_cancellation_is_not_swallowed_as_provider_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])

    async def cancelled(*_args: Any, **_kwargs: Any) -> Any:
        """A cancelled remote call must remain cancellation rather than a fallback success."""
        raise asyncio.CancelledError

    monkeypatch.setattr(knowledge.store, "catalog", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(knowledge.search("zion", "clothing"))


def test_passage_count_and_context_size_are_bounded(tmp_path: Path) -> None:
    data = [chunk(f"item-{n}", "Clothing and equipment.", ["zion"]) for n in range(8)]
    knowledge = knowledge_for(tmp_path, data)
    result = asyncio.run(knowledge.search("zion", "clothing", explain=True))
    assert len(result["passages"]) == 4
    assert sum(row["selection"] == "result_limit" for row in result["diagnostics"]["candidates"]) == 4
    long = knowledge_for(
        tmp_path,
        [
            chunk("long-a", "clothing " + "a" * 7000, ["zion"]),
            chunk("long-b", "clothing " + "b" * 7000, ["zion"]),
        ],
    )
    result = asyncio.run(long.search("zion", "clothing", explain=True))
    assert len(result["passages"]) == 1
    assert result["diagnostics"]["context_chars"] <= 10000
    assert any(row["selection"] == "context_limit" for row in result["diagnostics"]["candidates"])


def test_inspection_uses_actual_provider_text_and_returns_detached_records(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])
    result = asyncio.run(knowledge.inspection())
    assert result["provider"] == "qdrant"
    assert len(result["chunks"][0]["embedding"]) == 384
    result["chunks"][0]["text"] = "changed"
    assert asyncio.run(knowledge.inspection())["chunks"][0]["text"] == "Clothing."
    assert asyncio.run(knowledge.inspection(with_vectors=False))["chunks"][0]["embedding"] == []


def test_private_question_is_absent_from_operational_logs(tmp_path: Path) -> None:
    knowledge = knowledge_for(tmp_path, [chunk("item", "Clothing.", ["zion"])])
    question = "private-marker clothing"
    with capture_logs() as logs:
        asyncio.run(knowledge.search("zion", question))
    assert question not in json.dumps(logs)


def test_models_reject_unapproved_urls_and_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        Destination.model_validate(destination("zion", "Zion", ["Zion"]) | {"latitude": 100})
    with pytest.raises(ValidationError):
        ParkChunk.model_validate(chunk("x", "Text", ["zion"], source_url="https://example.com/fake"))
