"""Scope decisions are observable without exposing the question, answer, classifier response or credentials."""

import asyncio
import json
from typing import Any
from unittest.mock import Mock

import pytest
from langsmith import tracing_context
from structlog.testing import capture_logs

from nimbus.observability import ACTIVITY_VIEWS, TIMELINE_EVENTS, to_activity_line
from nimbus.request_trace import RequestTrace
from nimbus.scope_tracing import ScopeTrace, scope_trace
from tests.unit.test_memory_tracing import tracer
from tests.unit.test_request_trace import ended, started

PRIVATE = "private-question-response-provider-message-api-key"


def test_scope_checks_nest_under_request_and_exclude_all_private_content(monkeypatch: pytest.MonkeyPatch) -> None:
    tracing, client = tracer()
    flush = Mock()
    monkeypatch.setattr(type(tracing), "defer_flush", flush)
    request = RequestTrace.begin(tracing)
    with capture_logs() as logs, tracing_context(metadata={"question": PRIVATE}, tags=[PRIVATE]):
        with scope_trace(request, "input") as check:
            check.outcome("allowed", "supported_task")
        with scope_trace(request, "output") as check:
            check.outcome("blocked", "output_mismatch")
    root, first, second = started(client.kept_runs)
    assert [first["name"], second["name"]] == ["scope.input", "scope.output"]
    for child in (first, second):
        assert child["parent_run_id"] == root["id"]
        assert child["trace_id"] == root["id"]
        assert child["dotted_order"].startswith(root["dotted_order"] + ".")
        finish = ended(client.kept_runs, child["id"])[0]
        assert not finish.get("error")
        assert finish["end_time"] >= child["start_time"]
    assert ended(client.kept_runs, second["id"])[0]["extra"]["metadata"]["scope_outcome"] == "blocked"
    assert PRIVATE not in json.dumps([client.kept_runs, logs])
    assert all(run.get("inputs", {}) == run.get("outputs", {}) == {} for run in client.kept_runs)
    assert [(row["action"], row["status"], row["reason"]) for row in logs] == [
        ("input", "allowed", "supported_task"),
        ("output", "blocked", "output_mismatch"),
    ]
    flush.assert_not_called()
    request.end()
    flush.assert_called_once()


@pytest.mark.parametrize("reason", ["timeout", "invalid_response", "provider_error", "unconfigured", "oversized"])
def test_checker_unavailability_fails_its_span_but_deliberate_blocks_do_not(reason: str) -> None:
    tracing, client = tracer()
    request = RequestTrace.begin(tracing)
    with scope_trace(request, "output") as check:
        check.outcome("unavailable", reason)
    child = started(client.kept_runs)[1]
    finish = ended(client.kept_runs, child["id"])[0]
    assert finish.get("error") == "hidden"
    assert finish["extra"]["metadata"]["scope_reason"] == reason


@pytest.mark.parametrize("value", [PRIVATE, {}, [], True, None])
def test_scope_metadata_rejects_unknown_or_nonstring_values(value: Any) -> None:
    tracing, client = tracer()
    request = RequestTrace.begin(tracing)
    with capture_logs() as logs, scope_trace(request, "input") as check:
        check.outcome(value, value)
    child = started(client.kept_runs)[1]
    finish = ended(client.kept_runs, child["id"])[0]
    assert finish["extra"]["metadata"]["scope_outcome"] == "error"
    assert finish["extra"]["metadata"]["scope_reason"] == ""
    assert logs[0]["status"] == "error"
    assert logs[0]["reason"] == ""
    assert PRIVATE not in json.dumps([client.kept_runs, logs])


@pytest.mark.parametrize("cancelled", [True, False])
def test_scope_cancellation_and_exceptions_close_once_and_propagate(cancelled: bool) -> None:
    tracing, client = tracer()
    request = RequestTrace.begin(tracing)
    error = asyncio.CancelledError(PRIVATE) if cancelled else ValueError(PRIVATE)
    with capture_logs() as logs, pytest.raises(type(error)), scope_trace(request, "output"):
        raise error
    child = started(client.kept_runs)[1]
    [finish] = ended(client.kept_runs, child["id"])
    assert finish["extra"]["metadata"]["scope_outcome"] == ("cancelled" if cancelled else "error")
    assert bool(finish.get("error")) is not cancelled
    assert PRIVATE not in json.dumps([client.kept_runs, logs])


def test_unavailable_tracing_never_creates_orphans_or_suppresses_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    tracing, client = tracer()
    monkeypatch.setattr(client, "create_run", Mock(side_effect=RuntimeError(PRIVATE)))
    with capture_logs() as logs:
        request = RequestTrace.begin(tracing)
        with scope_trace(request, "input") as check:
            check.outcome("blocked", "creative_request")
    assert client.kept_runs == []
    assert request.parent is None
    assert check.parent is None
    assert any(row["event"] == "guardrail.check" and row["status"] == "blocked" for row in logs)
    assert PRIVATE not in json.dumps(logs)


def test_disabled_tracing_records_one_private_safe_activity_event() -> None:
    check = ScopeTrace(RequestTrace.begin(None), "input")
    with capture_logs() as logs:
        check.start()
        check.outcome("clarify", "unclear_task")
        check.close()
        check.close()
    assert len(logs) == 1
    assert logs[0]["status"] == "clarify"
    assert "traceId" not in logs[0]


@pytest.mark.parametrize(
    ("status", "reason", "tone", "detail"),
    [
        ("allowed", "supported_task", "ok", "Allowed"),
        ("blocked", "creative_request", "warn", "Creative writing request"),
        ("unavailable", "timeout", "bad", "Scope check timed out"),
        ("clarify", "unclear_task", "idle", "Clarification needed"),
        ("cancelled", "", "idle", "Cancelled"),
        (PRIVATE, PRIVATE, "idle", "Unknown outcome"),
    ],
)
def test_activity_projects_scope_outcomes_and_failures_with_fixed_words(
    status: str, reason: str, tone: str, detail: str
) -> None:
    assert "guardrail.check" in TIMELINE_EVENTS
    assert 'event == "guardrail.check"' in ACTIVITY_VIEWS["errors"]
    row = to_activity_line(
        {
            "_time": "2026-11-10T12:00:00Z",
            "event": "guardrail.check",
            "status": status,
            "reason": reason,
            "action": "output",
            "ms": 9,
            "question": PRIVATE,
        }
    )
    assert row is not None
    assert row.what == "Answer scope check"
    assert row.tone == tone
    assert detail in row.detail
    assert PRIVATE not in str(row)
