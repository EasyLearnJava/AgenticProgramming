"""ColBERT reorders verified candidates without weakening scope, abstention or failure handling."""

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest

from nimbus.park_semantic import SemanticResult
from nimbus.parks import RERANK_CANDIDATES
from tests.park_fakes import FakeParkStore, knowledge_for
from tests.unit.test_parks import chunk


def test_reranker_uses_full_question_and_only_scoped_admitted_candidates(tmp_path: Path) -> None:
    question = "What clothing should I wear in spring?"
    service = knowledge_for(
        tmp_path,
        [
            chunk("keyword", "Clothing and footwear.", ["zion-narrows"]),
            chunk("meaning", "Neoprene insulation.", ["zion-narrows"], seasons=["spring"]),
            chunk("winter", "Winter clothing.", ["zion-narrows"], seasons=["winter"]),
            chunk("other", "Clothing.", ["yosemite"], park_id="yosemite", document_id="yosemite-guide"),
            chunk("weak", "Unrelated.", ["zion-narrows"]),
        ],
        keyword_scores={"keyword": 8},
        semantic_scores={"keyword": 0.7, "meaning": 0.8, "weak": 0.4},
        rerank_scores={"keyword": 6.0, "meaning": 11.5},
        rerank_enabled=True,
    )
    result = asyncio.run(service.search("zion-narrows", question, explain=True))
    assert [p["id"] for p in result["passages"]] == ["meaning", "keyword"]
    assert result["rerank_status"] == "ready"
    calls = cast(FakeParkStore, service.store).calls
    rerank = next(call for call in calls if call["method"] == "rerank")
    assert rerank["query"] == question
    assert rerank["season"] == "spring"
    assert set(rerank["eligible"]) == {"keyword", "meaning"}
    rows = {row["chunk"]["id"]: row for row in result["diagnostics"]["candidates"]}
    assert (rows["meaning"]["rrf_rank"], rows["meaning"]["rank"], rows["meaning"]["rerank_rank"]) == (2, 1, 1)
    assert rows["meaning"]["rerank_score"] == 11.5
    assert rows["meaning"]["final_score"] < rows["keyword"]["final_score"]
    assert rows["weak"]["rank"] is None
    assert rows["weak"]["rerank_score"] is None


@pytest.mark.parametrize("status", ["timeout", "unavailable", "invalid_response", "unconfigured", "index_mismatch"])
def test_reranker_failure_preserves_complete_rrf_order(tmp_path: Path, status: str) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("first", "Clothing.", ["zion"]), chunk("second", "Clothing.", ["zion"])],
        keyword_scores={"first": 9, "second": 2},
        rerank_status=status,
        rerank_scores={"second": 99, "first": 0},
        rerank_enabled=True,
    )
    result = asyncio.run(service.search("zion", "clothing", explain=True))
    assert result["status"] == "found"
    assert result["rerank_status"] == status
    assert [p["id"] for p in result["passages"]] == ["first", "second"]
    assert all(row["rerank_score"] is None for row in result["diagnostics"]["candidates"])


@pytest.mark.parametrize(
    "scores",
    [
        {"first": 1},
        {"first": 1, "second": 2, "foreign": 3},
        {"first": True, "second": 2},
        {"first": float("nan"), "second": 2},
        {"first": float("inf"), "second": 2},
        {"first": 10001, "second": 2},
    ],
)
def test_incomplete_or_invalid_rerank_scores_never_reorder_context(tmp_path: Path, scores: dict[str, Any]) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("first", "Clothing.", ["zion"]), chunk("second", "Clothing.", ["zion"])],
        keyword_scores={"first": 2, "second": 1},
        rerank_scores=scores,
        rerank_enabled=True,
    )
    result = asyncio.run(service.search("zion", "clothing"))
    assert result["rerank_status"] == "invalid_response"
    assert [p["id"] for p in result["passages"]] == ["first", "second"]


def test_shortlist_is_bounded_and_ties_preserve_rrf_order(tmp_path: Path) -> None:
    items = [chunk(f"item{i:02}", "Clothing.", ["zion"]) for i in range(16)]
    service = knowledge_for(
        tmp_path,
        items,
        keyword_scores={item["id"]: float(16 - i) for i, item in enumerate(items)},
        rerank_scores={item["id"]: 7.0 for item in items[:RERANK_CANDIDATES]},
        rerank_enabled=True,
    )
    result = asyncio.run(service.search("zion", "clothing", explain=True))
    assert result["rerank_status"] == "ready"
    assert [p["id"] for p in result["passages"]] == [item["id"] for item in items[:4]]
    calls = cast(FakeParkStore, service.store).calls
    assert len(next(call for call in calls if call["method"] == "rerank")["eligible"]) == 12
    assert [row["rank"] for row in result["diagnostics"]["candidates"]] == list(range(1, 17))
    assert all(row["rerank_score"] is None for row in result["diagnostics"]["candidates"][12:])


@pytest.mark.parametrize(
    ("enabled", "mode", "scores", "status"),
    [
        (False, "hybrid", {"a": 2, "b": 1}, "disabled"),
        (True, "lexical", {"a": 2, "b": 1}, "disabled"),
        (True, "hybrid", {"a": 2}, "not_needed"),
        (True, "hybrid", {}, "not_needed"),
    ],
)
def test_disabled_or_unnecessary_reranking_makes_no_provider_call(
    tmp_path: Path, enabled: bool, mode: Any, scores: dict[str, float], status: str
) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("a", "Clothing.", ["zion"]), chunk("b", "Clothing.", ["zion"])],
        keyword_scores=scores,
        rerank_enabled=enabled,
        mode=mode,
    )
    result = asyncio.run(service.search("zion", "clothing"))
    assert result["rerank_status"] == status
    assert not any(call["method"] == "rerank" for call in cast(FakeParkStore, service.store).calls)
    assert bool(result["passages"]) == bool(scores)


def test_rerank_deadline_keeps_rrf_evidence_and_cancels_work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("first", "Clothing.", ["zion"]), chunk("second", "Clothing.", ["zion"])],
        keyword_scores={"first": 2, "second": 1},
        rerank_enabled=True,
    )
    cancelled = False

    async def slow(*args: Any, **kwargs: Any) -> SemanticResult:
        nonlocal cancelled
        try:
            await asyncio.sleep(5)
        finally:
            cancelled = True
        return SemanticResult("ready")

    monkeypatch.setattr("nimbus.parks.RETRIEVAL_SECONDS", 0.03)
    monkeypatch.setattr(service.store, "rerank", slow)
    result = asyncio.run(service.search("zion", "clothing"))
    assert result["rerank_status"] == "timeout"
    assert [p["id"] for p in result["passages"]] == ["first", "second"]
    assert cancelled


def test_rerank_external_cancellation_is_not_a_successful_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("first", "Clothing.", ["zion"]), chunk("second", "Clothing.", ["zion"])],
        rerank_enabled=True,
    )

    async def cancelled(*args: Any, **kwargs: Any) -> SemanticResult:
        raise asyncio.CancelledError

    monkeypatch.setattr(service.store, "rerank", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.search("zion", "clothing"))


def test_rerank_uses_remaining_budget_after_slower_prior_stages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = knowledge_for(
        tmp_path,
        [chunk("first", "Clothing.", ["zion"]), chunk("second", "Clothing.", ["zion"])],
        keyword_scores={"first": 2, "second": 1},
        rerank_enabled=True,
    )
    store = cast(FakeParkStore, service.store)
    original = store.catalog

    async def delayed_catalog(*args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(0.2)
        return await original(*args, **kwargs)

    async def delayed_rerank(*args: Any, **kwargs: Any) -> SemanticResult:
        await asyncio.sleep(0.2)
        return SemanticResult("ready", {"first": 1, "second": 2})

    monkeypatch.setattr("nimbus.parks.RETRIEVAL_SECONDS", 0.3)
    monkeypatch.setattr(store, "catalog", delayed_catalog)
    monkeypatch.setattr(store, "rerank", delayed_rerank)

    async def run() -> dict[str, Any]:
        async with asyncio.timeout(0.38):
            return await service.search("zion", "clothing")

    result = asyncio.run(run())
    assert result["rerank_status"] == "timeout"
    assert [p["id"] for p in result["passages"]] == ["first", "second"]
