"""Real LangSmith serialization of private-free park retrieval steps, nested chat work and fallback outcomes."""

import asyncio
import json
from typing import Any
from unittest.mock import Mock

import pytest
from langchain_core.tools import StructuredTool
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import tracing_context

from nimbus.park_tracing import PARK_RETRIEVAL_NAME, ParkTrace, park_retrieval_trace
from nimbus.request_trace import RequestTrace
from tests.unit.test_memory_tracing import tracer
from tests.unit.test_request_trace import ended, started

PRIVATE = "private-query-passage-key-and-browser-context"


def metadata(run: dict[str, Any]) -> dict[str, Any]:
    """Exclude only the SDK's automatic Git revision when asserting our operational metadata."""
    return {key: value for key, value in run["extra"]["metadata"].items() if key != "revision_id"}


def test_standalone_retrieval_has_three_nested_stages_and_flushes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Playground receives its own root with real stage timings and no external content."""
    tracing, client = tracer()
    flush = Mock()
    monkeypatch.setattr(type(tracing), "defer_flush", flush)
    with (
        tracing_context(metadata={"question": PRIVATE}, tags=[PRIVATE]),
        park_retrieval_trace(tracing) as retrieval,
    ):
        with retrieval.step("bm25") as keyword:
            keyword.outcome("ready", candidate_count=12)
        with retrieval.step("semantic") as semantic:
            semantic.outcome("ready", provider="qdrant", candidate_count=8)
        with retrieval.step("fusion") as fusion:
            fusion.outcome("found", mode="hybrid", selected_count=4)
        retrieval.outcome(
            "found", provider="qdrant", mode="hybrid", candidate_count=12, selected_count=4, season_source="query"
        )
    root, *children = started(client.kept_runs)
    assert root["name"] == PARK_RETRIEVAL_NAME
    assert root["trace_id"] == root["id"] == str(retrieval.trace_id)
    assert [child["name"] for child in children] == ["parks.bm25", "parks.semantic", "parks.fusion"]
    for child in children:
        assert child["parent_run_id"] == root["id"]
        assert child["trace_id"] == root["id"]
        assert child["dotted_order"].startswith(root["dotted_order"] + ".")
        finish = ended(client.kept_runs, child["id"])[0]
        assert child["start_time"] <= finish["end_time"]
        assert not finish.get("error")
    assert metadata(ended(client.kept_runs, root["id"])[0]) == {
        "retrieval_outcome": "found",
        "retrieval_provider": "qdrant",
        "retrieval_mode": "hybrid",
        "retrieval_season_source": "query",
        "retrieval_candidates": 12,
        "retrieval_selected": 4,
    }
    assert PRIVATE not in json.dumps(client.kept_runs)
    assert all(run.get("inputs", {}) == run.get("outputs", {}) == {} for run in client.kept_runs)
    flush.assert_called_once()


def test_real_langchain_tool_nests_retrieval_in_the_chat_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    """The active LangChain tool, not an invented independent trace, is the parent of park retrieval."""
    tracing, client = tracer()
    flush = Mock()
    monkeypatch.setattr(type(tracing), "defer_flush", flush)
    request = RequestTrace.begin(tracing)

    async def search(query: str) -> str:
        """A real LangChain tool whose body uses the production retrieval tracing context."""
        with park_retrieval_trace(tracing) as operation:
            with operation.step("bm25") as keyword:
                keyword.outcome("ready", candidate_count=2)
            operation.outcome("found", mode="lexical", selected_count=1)
        return "done"

    tool = StructuredTool.from_function(coroutine=search, name="search_park_guidance")
    with tracing_context(enabled=True, client=client, project_name=tracing.project, parent=request.run_tree()):
        asyncio.run(tool.ainvoke({"query": PRIVATE}))
    wait_for_all_tracers()
    runs = started(client.kept_runs)
    root = next(run for run in runs if run["name"] == "nimbus.chat")
    tool_run = next(run for run in runs if run["name"] == "search_park_guidance")
    operation = next(run for run in runs if run["name"] == PARK_RETRIEVAL_NAME)
    assert operation["parent_run_id"] == tool_run["id"]
    assert operation["trace_id"] == tool_run["trace_id"] == root["id"]
    assert PRIVATE not in json.dumps(client.kept_runs)
    flush.assert_not_called()
    request.end()
    flush.assert_called_once()


@pytest.mark.parametrize("status", ["timeout", "invalid_response", "index_mismatch", "index_not_ready", "error"])
def test_returned_semantic_failure_fails_only_its_stage(status: str) -> None:
    """A successful BM25 fallback has a successful root but a failed semantic operation."""
    tracing, client = tracer()
    with park_retrieval_trace(tracing) as retrieval:
        with retrieval.step("semantic") as semantic:
            semantic.outcome(status, provider="qdrant")
        retrieval.outcome("found", provider="qdrant", mode="lexical", selected_count=2)
    root, child = started(client.kept_runs)
    assert ended(client.kept_runs, child["id"])[0].get("error") == "hidden"
    assert metadata(ended(client.kept_runs, child["id"])[0])["retrieval_outcome"] == status
    assert not ended(client.kept_runs, root["id"])[0].get("error")


@pytest.mark.parametrize("status", ["disabled", "unconfigured", "not_needed"])
def test_expected_semantic_skips_do_not_claim_a_provider_failure(status: str) -> None:
    """An intentionally skipped stage remains distinct from an attempted semantic call that failed."""
    tracing, client = tracer()
    with park_retrieval_trace(tracing) as retrieval, retrieval.step("semantic") as semantic:
        semantic.outcome(status, provider="qdrant")
    _, child = started(client.kept_runs)
    finish = ended(client.kept_runs, child["id"])[0]
    assert not finish.get("error")
    assert metadata(finish)["retrieval_outcome"] == status


@pytest.mark.parametrize("value", [True, -1, 1001, 1.5, PRIVATE, {"key": PRIVATE}])
def test_unapproved_metadata_and_invalid_counts_are_never_serialized(value: Any) -> None:
    """The trace boundary retains safe defaults instead of coercing private values into operational fields."""
    tracing, client = tracer()
    with park_retrieval_trace(tracing) as operation:
        operation.outcome(
            PRIVATE, provider=PRIVATE, mode=PRIVATE, season_source=PRIVATE, candidate_count=value, selected_count=value
        )
    [root] = started(client.kept_runs)
    fields = metadata(ended(client.kept_runs, root["id"])[0])
    assert fields == {
        "retrieval_outcome": "error",
        "retrieval_provider": "none",
        "retrieval_mode": "none",
        "retrieval_season_source": "none",
    }
    assert PRIVATE not in json.dumps(client.kept_runs)


def test_cancellation_and_raised_errors_close_without_exposing_the_exception() -> None:
    """Both exception paths close their spans and preserve the original caller control flow."""
    for error in (asyncio.CancelledError(PRIVATE), ValueError(PRIVATE)):
        tracing, client = tracer()
        with pytest.raises(type(error)), park_retrieval_trace(tracing) as operation, operation.step("semantic"):
            raise error
        for root in started(client.kept_runs):
            [finish] = ended(client.kept_runs, root["id"])
            assert metadata(finish)["retrieval_outcome"] == (
                "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
            )
        assert PRIVATE not in json.dumps(client.kept_runs)


def test_trace_failure_never_creates_orphan_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unavailable tracing does not abort retrieval or create disconnected provider traces."""
    tracing, client = tracer()
    monkeypatch.setattr(client, "create_run", Mock(side_effect=RuntimeError(PRIVATE)))
    with park_retrieval_trace(tracing) as operation, operation.step("semantic") as child:
        child.outcome("ready", provider="qdrant")
    assert child.trace_id is operation.trace_id is None
    assert client.kept_runs == []


def test_disabled_tracing_and_repeated_close_are_harmless() -> None:
    """The same instrumentation can be used without a tracer, and root closure is idempotent."""
    with park_retrieval_trace(None) as operation, operation.step("bm25") as child:
        child.outcome("ready")
    assert operation.trace_id is child.trace_id is None
    tracing, client = tracer()
    root = ParkTrace(tracing, PARK_RETRIEVAL_NAME)
    root.start()
    root.close()
    root.close()
    assert len(client.kept_runs) == 2
