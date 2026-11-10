"""Real LangSmith serialization of bounded cache outcomes, provider nesting and numeric-only similarity metadata."""

import asyncio
import json
from typing import Any, cast

import pytest
from langsmith import tracing_context
from structlog.testing import capture_logs

from nimbus.request_trace import CACHE_OPERATION_NAMES, CacheOutcome, RequestTrace
from tests.unit.test_memory_tracing import tracer
from tests.unit.test_request_trace import ended, started

PRIVATE = "private-question-answer-browser-context-credential"


def metadata_of(run: dict[str, Any]) -> dict[str, Any]:
    """Keep all operation metadata, excluding only the SDK's automatically attached Git revision."""
    return {key: value for key, value in run["extra"]["metadata"].items() if key != "revision_id"}


@pytest.mark.parametrize(
    "status",
    [
        "completed",
        "exact_hit",
        "semantic_hit",
        "miss",
        "shadow_hit",
        "error",
        "bypass",
        "saved",
        "not_reusable",
        "cache_full",
        "cancelled",
    ],
)
def test_returned_cache_outcomes_are_recorded_and_only_errors_fail(status: CacheOutcome) -> None:
    """A provider error returned as a value still appears failed without failing the successful chat root."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("lookup") as step:
        step.outcome(status)
    trace.end()
    root, child = started(client.kept_runs)
    [finish] = ended(client.kept_runs, child["id"])
    assert metadata_of(finish) == {"outcome": status}
    assert bool(finish.get("error")) is (status == "error")
    assert finish["inputs"] == finish["outputs"] == {}
    assert not ended(client.kept_runs, root["id"])[0].get("error")


def test_every_qdrant_operation_nests_under_its_cache_operation_in_one_trace() -> None:
    """Exact/similarity belong to lookup and cleanup/count/save to store, with no independent trace roots."""
    tracing, client = tracer()
    with tracing_context(metadata={"private": PRIVATE}, tags=[PRIVATE]):
        trace = RequestTrace.begin(tracing)
        with trace.step("lookup") as lookup:
            with lookup.step("exact") as exact:
                exact.outcome("miss")
            with lookup.step("similarity") as similarity:
                similarity.similarity(0.92, 0.8)
                similarity.outcome("semantic_hit")
            lookup.outcome("semantic_hit")
        with trace.step("store") as store:
            for action in ("cleanup", "count", "save"):
                with store.step(action):
                    pass
            store.outcome("saved")
        trace.cache_outcome("semantic_hit")
        trace.end()
    runs = started(client.kept_runs)
    assert len(runs) == 8
    root = runs[0]
    by_name = {run["name"]: run for run in runs}
    for name, parent_name in (
        ("weather_cache.lookup", "nimbus.chat"),
        ("qdrant.exact_match", "weather_cache.lookup"),
        ("qdrant.similarity_search", "weather_cache.lookup"),
        ("weather_cache.store", "nimbus.chat"),
        ("qdrant.remove_expired", "weather_cache.store"),
        ("qdrant.count", "weather_cache.store"),
        ("qdrant.save", "weather_cache.store"),
    ):
        child, parent = by_name[name], by_name[parent_name]
        assert child["trace_id"] == root["id"]
        assert child["parent_run_id"] == parent["id"]
        assert child["dotted_order"].startswith(parent["dotted_order"] + ".")
        assert child["run_type"] == "chain"
        assert child["inputs"] == {}
        [finish] = ended(client.kept_runs, child["id"])
        assert finish["parent_run_id"] == parent["id"]
        assert finish["outputs"] == {}
        assert child["start_time"] <= finish["end_time"]
    similarity_end = ended(client.kept_runs, by_name["qdrant.similarity_search"]["id"])[0]
    assert metadata_of(similarity_end) == {
        "outcome": "semantic_hit",
        "similarity_score": 0.92,
        "similarity_threshold": 0.8,
    }
    assert PRIVATE not in json.dumps(client.kept_runs)


@pytest.mark.parametrize("score", [None, PRIVATE, True, False, float("nan"), float("inf"), -1.1, 1.1, 10**500])
def test_similarity_drops_non_numeric_nonfinite_and_out_of_range_scores(score: object) -> None:
    """A malformed provider score never becomes a string, an unbounded value or a leaked object representation."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("lookup") as lookup, lookup.step("similarity") as child:
        child.similarity(score, 0.8)
    trace.end()
    run = next(run for run in started(client.kept_runs) if run["name"] == CACHE_OPERATION_NAMES["similarity"])
    metadata = metadata_of(ended(client.kept_runs, run["id"])[0])
    assert metadata == {"outcome": "completed", "similarity_threshold": 0.8}
    assert PRIVATE not in json.dumps(client.kept_runs)


@pytest.mark.parametrize("threshold", [None, PRIVATE, True, float("nan"), float("inf"), -0.1, 1.1])
def test_similarity_threshold_is_a_bounded_number(threshold: object) -> None:
    """Thresholds cannot carry arbitrary strings or values outside the normalized similarity range."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("lookup") as lookup, lookup.step("similarity") as child:
        child.similarity(0.9, threshold)
    trace.end()
    run = next(run for run in started(client.kept_runs) if run["name"] == CACHE_OPERATION_NAMES["similarity"])
    assert metadata_of(ended(client.kept_runs, run["id"])[0]) == {
        "outcome": "completed",
        "similarity_score": 0.9,
    }


@pytest.mark.parametrize(("score", "threshold"), [(-1, 0), (1, 1), (0, 0.8)])
def test_similarity_numeric_boundaries_are_retained(score: float, threshold: float) -> None:
    """Boundary values are legitimate cosine measurements, not private payloads."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("lookup") as lookup, lookup.step("similarity") as child:
        child.similarity(score, threshold)
    trace.end()
    run = next(run for run in started(client.kept_runs) if run["name"] == CACHE_OPERATION_NAMES["similarity"])
    metadata = metadata_of(ended(client.kept_runs, run["id"])[0])
    assert metadata["similarity_score"] == score
    assert metadata["similarity_threshold"] == threshold


def test_only_similarity_steps_accept_similarity_measurements() -> None:
    """A generic cache step or another provider call cannot acquire unrelated measurement metadata."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("store") as store, store.step("count") as child:
        store.similarity(0.9, 0.8)
        child.similarity(0.9, 0.8)
    trace.end()
    for run in started(client.kept_runs)[1:]:
        assert metadata_of(ended(client.kept_runs, run["id"])[0]) == {"outcome": "completed"}


def test_bypass_reason_is_available_on_root_without_a_cache_child() -> None:
    """Skipped requests retain a clear fixed explanation even though no Qdrant work happened."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    trace.cache_outcome("bypass", "unverified_history")
    trace.end()
    [root] = started(client.kept_runs)
    [finish] = ended(client.kept_runs, root["id"])
    assert metadata_of(finish) == {
        "workflow": "agent",
        "cache_outcome": "bypass",
        "cache_bypass_reason": "unverified_history",
    }
    assert not finish.get("error")


def test_unknown_statuses_and_reasons_are_never_serialized() -> None:
    """Runtime allowlists remain enforced even when a caller ignores the Literal type contracts."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    trace.cache_outcome(cast(Any, PRIVATE), cast(Any, PRIVATE))
    with trace.step("store") as store:
        store.outcome(cast(Any, {PRIVATE: PRIVATE}))
    trace.end()
    root, child = started(client.kept_runs)
    assert metadata_of(ended(client.kept_runs, root["id"])[0]) == {
        "workflow": "agent",
        "cache_outcome": "error",
    }
    assert metadata_of(ended(client.kept_runs, child["id"])[0]) == {"outcome": "error"}
    assert PRIVATE not in json.dumps(client.kept_runs)


@pytest.mark.parametrize("timeout", [False, True])
def test_cancelled_steps_close_and_preserve_an_explicit_timeout_error(timeout: bool) -> None:
    """Actual cancellation remains distinct from a timeout deliberately classified as provider failure."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)

    def cancel() -> None:
        """Exit nested spans through task cancellation, optionally preceded by an explicit timeout outcome."""
        with trace.step("lookup") as lookup, lookup.step("exact") as child:
            if timeout:
                child.outcome("error")
            raise asyncio.CancelledError(PRIVATE)

    with pytest.raises(asyncio.CancelledError):
        cancel()
    trace.end()
    root, lookup_run, operation = started(client.kept_runs)
    finish = ended(client.kept_runs, operation["id"])[0]
    assert finish["extra"]["metadata"]["outcome"] == ("error" if timeout else "cancelled")
    assert bool(finish.get("error")) is timeout
    assert ended(client.kept_runs, lookup_run["id"])[0]["extra"]["metadata"]["outcome"] == "cancelled"
    assert not ended(client.kept_runs, root["id"])[0].get("error")
    assert PRIVATE not in json.dumps(client.kept_runs)


def test_failed_step_creation_never_creates_orphan_provider_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed trace write is optional instrumentation; cache work can continue and no provider span becomes a root."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)

    def broken(*_args: object, **_kwargs: object) -> None:
        """Stand in for a broken tracing service without disclosing its response."""
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(client, "create_run", broken)
    with capture_logs() as logs:
        with trace.step("lookup") as lookup, lookup.step("exact") as child:
            assert lookup.parent is child.parent is None
            child.outcome("miss")
        trace.end()
    assert len(started(client.kept_runs)) == 1
    assert PRIVATE not in json.dumps([client.kept_runs, logs])


def test_tracing_disabled_does_not_start_nested_provider_runs() -> None:
    """The same caller API is harmless when no LangSmith client is configured."""
    trace = RequestTrace.begin(None)
    with trace.step("lookup") as lookup, lookup.step("similarity") as child:
        child.similarity(0.9, 0.8)
        child.outcome("semantic_hit")
        assert lookup.parent is child.parent is None
    trace.cache_outcome("semantic_hit")
    trace.end()
    assert trace.fields() == {}
