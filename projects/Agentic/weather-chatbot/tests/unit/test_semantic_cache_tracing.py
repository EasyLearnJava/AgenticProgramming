"""Real LangSmith serialization of Qdrant stages and outcomes, with private payloads kept out of every span."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import httpx2
import pytest

from nimbus.request_trace import RequestTrace
from nimbus.semantic_cache.models import CacheLookup, CacheStore
from nimbus.semantic_cache.service import MAX_POINTS
from tests.unit.test_memory_tracing import tracer
from tests.unit.test_request_trace import ended, started
from tests.unit.test_semantic_cache_service import (
    CONTEXT,
    KEY,
    NOW,
    QUESTION,
    SCOPE,
    RecordingQdrant,
    entry,
    point,
    points,
    service,
)

type Handler = Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]]


def lookup_trace(handler: Handler, **overrides: Any) -> tuple[CacheLookup, list[dict[str, Any]]]:
    """Run the actual cache adapter beneath a real SDK request and cache-step pair."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("lookup") as step:
        result = asyncio.run(service(handler, **overrides).lookup(QUESTION, SCOPE, CONTEXT, entry().policy, trace=step))
        step.outcome(result.status)
    trace.cache_outcome(result.status)
    trace.end()
    return result, client.kept_runs


def store_trace(handler: Handler, **overrides: Any) -> tuple[CacheStore, list[dict[str, Any]]]:
    """A safe cache parent reports the returned status instead of equating return with success."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("store") as step:
        result = asyncio.run(service(handler, **overrides).store(QUESTION, entry(), trace=step))
        step.outcome(result.status)
    trace.end()
    return result, client.kept_runs


def end_named(runs: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Find one child by its fixed service name, then its actual serialized ending."""
    [run] = [run for run in started(runs) if run["name"] == name]
    [ending] = ended(runs, run["id"])
    return ending


def assert_private(runs: list[dict[str, Any]]) -> None:
    """No operation writes provider payloads, identifiers, visitor text or credentials."""
    payload = json.dumps(runs, default=str)
    for private in (QUESTION, QUESTION.lower(), KEY, SCOPE, CONTEXT, entry().answer, entry().label, "test-point"):
        assert private not in payload
    for run in runs:
        assert run.get("inputs", {}) == {}
        assert run.get("outputs", {}) == {}


@pytest.mark.parametrize("kind", ["exact", "semantic", "miss", "shadow", "error"])
def test_lookup_outcomes_and_nested_provider_spans_are_truthful(kind: str) -> None:
    """Hits, misses, swallowed outages and shadow decisions remain distinct in the serialized trace."""
    responses = {
        "exact": [points(point(entry()))],
        "semantic": [points(), points(point(entry()))],
        "miss": [points(), points()],
        "shadow": [points(point(entry()))],
        "error": [httpx2.Response(503, text=KEY + QUESTION)],
    }
    result, runs = lookup_trace(
        RecordingQdrant(*responses[kind]), semantic_cache_mode="shadow" if kind == "shadow" else "on"
    )
    expected = {"exact": "exact_hit", "semantic": "semantic_hit", "shadow": "shadow_hit"}.get(kind, kind)
    assert result.status == expected
    root, cache, *children = started(runs)
    assert cache["parent_run_id"] == root["id"]
    assert [child["name"] for child in children] == [
        "qdrant.exact_match",
        *(["qdrant.similarity_search"] if kind in {"semantic", "miss"} else []),
    ]
    for child in children:
        assert child["trace_id"] == root["id"]
        assert child["parent_run_id"] == cache["id"]
        assert child["dotted_order"].startswith(cache["dotted_order"] + ".")
        assert child["start_time"] <= end_named(runs, child["name"])["end_time"]
    ending = end_named(runs, "weather_cache.lookup")
    assert ending["extra"]["metadata"]["outcome"] == expected
    assert bool(ending.get("error")) is (kind == "error")
    assert not end_named(runs, "nimbus.chat").get("error")  # Optional cache failure does not fail the answer.
    assert end_named(runs, "nimbus.chat")["extra"]["metadata"]["cache_outcome"] == expected
    assert_private(runs)


@pytest.mark.parametrize("score", [0.96, 0.89, -1, None, True, "private-score", float("nan"), float("inf"), 2])
def test_similarity_spans_record_only_bounded_numeric_metrics(score: object) -> None:
    """The score is useful even below the cutoff; untrusted nonnumeric or nonfinite metadata is discarded."""
    response = httpx2.Response(
        200, content=json.dumps({"status": "ok", "result": {"points": [point(entry(), score)]}}).encode()
    )
    _result, runs = lookup_trace(RecordingQdrant(points(), response))
    metadata = end_named(runs, "qdrant.similarity_search")["extra"]["metadata"]
    assert metadata["similarity_threshold"] == 0.9
    if type(score) in {int, float} and -1 <= score <= 1:  # type: ignore[operator]
        assert metadata.get("similarity_score") == score
    else:
        assert "similarity_score" not in metadata
    assert "private-score" not in str(runs)
    assert_private(runs)


def test_similarity_failure_retains_threshold_but_no_invented_score() -> None:
    """A failed inference request records the attempted threshold without fabricating a candidate score."""
    result, runs = lookup_trace(RecordingQdrant(points(), httpx2.Response(429, text=KEY)))
    assert result.status == "error"
    ending = end_named(runs, "qdrant.similarity_search")
    assert ending["error"]
    assert ending["extra"]["metadata"]["similarity_threshold"] == 0.9
    assert "similarity_score" not in ending["extra"]["metadata"]
    assert_private(runs)


@pytest.mark.parametrize("failure_stage", [None, 0, 1, 2])
def test_store_traces_each_provider_stage_and_stops_at_the_actual_failure(failure_stage: int | None) -> None:
    """Cleanup, capacity and embedding/write have separate durations and fail only where work failed."""
    responses = [
        httpx2.Response(200, json={"status": "ok", "result": {}}),
        httpx2.Response(200, json={"status": "ok", "result": {"count": 0}}),
        httpx2.Response(200, json={"status": "ok", "result": {}}),
    ]
    if failure_stage is not None:
        responses[failure_stage] = httpx2.Response(503, text=QUESTION + KEY)
    result, runs = store_trace(RecordingQdrant(*responses))
    assert result.status == ("saved" if failure_stage is None else "error")
    root, cache, *children = started(runs)
    names = ["qdrant.remove_expired", "qdrant.count", "qdrant.save"]
    assert [child["name"] for child in children] == names[: 3 if failure_stage is None else failure_stage + 1]
    for index, child in enumerate(children):
        assert child["trace_id"] == root["id"]
        assert child["parent_run_id"] == cache["id"]
        assert bool(end_named(runs, child["name"]).get("error")) is (index == failure_stage)
    end = end_named(runs, "weather_cache.store")
    assert end["extra"]["metadata"]["outcome"] == result.status
    assert bool(end.get("error")) is (failure_stage is not None)
    assert_private(runs)


@pytest.mark.parametrize("count", [MAX_POINTS, None, True, -1, "private-count"])
def test_capacity_and_malformed_count_are_distinct_trace_outcomes(count: object) -> None:
    """A real full collection is expected; malformed provider data is a failed count operation."""
    provider = RecordingQdrant(
        httpx2.Response(200, json={"status": "ok", "result": {}}),
        httpx2.Response(200, json={"status": "ok", "result": {"count": count}}),
    )
    result, runs = store_trace(provider)
    full = count == MAX_POINTS
    assert result.status == ("cache_full" if full else "error")
    assert len(provider.requests) == 2
    count_end = end_named(runs, "qdrant.count")
    assert bool(count_end.get("error")) is not full
    assert count_end["extra"]["metadata"]["outcome"] == ("cache_full" if full else "error")
    assert "private-count" not in str(runs)
    assert_private(runs)


def test_deadline_marks_provider_and_parent_failed_while_preserving_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Our operation deadline is an outage, not a completed or visitor-cancelled provider span."""
    monkeypatch.setattr("nimbus.semantic_cache.service.TIMEOUT_SECONDS", 0.01)

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        """Remain in the actual HTTP adapter until its operation deadline interrupts it."""
        await asyncio.sleep(1)
        return points()

    result, runs = lookup_trace(slow)
    assert result.status == "error"
    for name in ("weather_cache.lookup", "qdrant.exact_match"):
        ending = end_named(runs, name)
        assert ending.get("error")
        assert ending["extra"]["metadata"]["outcome"] == "error"


def test_visitor_cancellation_stays_cancelled_and_propagates() -> None:
    """A disconnected request closes its nested spans without turning cancellation into a cache miss."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)

    async def cancelled(_request: httpx2.Request) -> httpx2.Response:
        """Simulate task cancellation rather than a provider HTTP failure."""
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError), trace.step("lookup") as step:
        asyncio.run(service(cancelled).lookup(QUESTION, SCOPE, CONTEXT, entry().policy, trace=step))
    trace.end()
    for name in ("weather_cache.lookup", "qdrant.exact_match"):
        ending = end_named(client.kept_runs, name)
        assert ending["extra"]["metadata"]["outcome"] == "cancelled"
        assert not ending.get("error")


def test_disabled_store_has_no_provider_children() -> None:
    """A disabled optimization is a bypass, never a saved entry or a fake provider call."""
    provider = RecordingQdrant()
    result, runs = store_trace(provider, semantic_cache_mode="off")
    assert result.status == "bypass"
    assert not provider.requests
    assert [run["name"] for run in started(runs)] == ["nimbus.chat", "weather_cache.store"]


def test_expired_store_is_not_reusable_without_provider_requests() -> None:
    """Expiry during response generation remains distinct from provider failure or capacity."""
    provider = RecordingQdrant()
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("store") as step:
        result = asyncio.run(service(provider).store(QUESTION, entry(expires_at=NOW), trace=step))
        step.outcome(result.status, result.reason)
    trace.end()
    assert result.status == "not_reusable"
    assert result.reason == "freshness"
    assert not provider.requests
    end = end_named(client.kept_runs, "weather_cache.store")
    assert end["extra"]["metadata"]["outcome"] == "not_reusable"
    assert end["extra"]["metadata"]["rejection"] == "freshness"
    assert not end.get("error")


@pytest.mark.parametrize(("status", "rejection"), [("saved", "units"), ("not_reusable", "private visitor text")])
def test_a_store_step_records_only_a_fixed_rejection_on_a_not_reusable_outcome(status: str, rejection: str) -> None:
    """A rejection word cannot ride along on another outcome, and an unknown one is never written to LangSmith."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    with trace.step("store") as step:
        step.outcome(status, rejection)  # type: ignore[arg-type]
    trace.end()
    assert "rejection" not in end_named(client.kept_runs, "weather_cache.store")["extra"]["metadata"]
