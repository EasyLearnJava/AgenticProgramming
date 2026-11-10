"""Activity links only recent, unambiguous Nimbus operations to a bounded, same-site trace view."""

import re
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.axiom_query import AxiomQuery, Row
from nimbus.config import Settings
from nimbus.observability import get_activity_trace_reader, to_activity_requests
from nimbus.trace_links import resolve_trace_link, trace_url
from nimbus.trace_view import TraceIssue, TraceView
from tests.fakes import AxiomRecordings


@pytest.fixture
def connected(settings: Settings) -> Settings:
    return settings.model_copy(update={"axiom_query_token": SecretStr("test-read"), "axiom_dataset": "nimbus"})


def test_handle_binds_project_dataset_trace_ref_and_expiry(connected: Settings) -> None:
    root, now = uuid4(), datetime.now(UTC)
    url = trace_url(connected, str(root), now, "abcd1234", now)
    assert url is not None
    handle = url.rsplit("/", 1)[-1]
    assert resolve_trace_link(connected, handle, now + timedelta(minutes=59)) == (root, "abcd1234")
    assert resolve_trace_link(connected, handle, now + timedelta(minutes=61)) is None
    for altered in (handle.replace(root.hex, uuid4().hex), handle.replace("abcd1234", "abcd1235"), str(root), "☁"):
        assert resolve_trace_link(connected, altered, now) is None
    for scope in ({"langsmith_project": "other"}, {"axiom_dataset": "other"}, {"axiom_query_token": None}):
        assert resolve_trace_link(connected.model_copy(update=scope), handle, now) is None
    assert resolve_trace_link(connected, handle, now + timedelta(days=7)) is None
    assert trace_url(connected, str(root), now - timedelta(days=7), "ref", now) is None


@pytest.mark.parametrize(
    ("event", "trace_id"),
    [("tool.call", str(uuid4())), ("chat.rejected", str(uuid4())), ("chat.done", ""), ("chat.failed", "../other")],
)
def test_only_traced_chat_endings_make_links(connected: Settings, event: str, trace_id: str) -> None:
    row: Row = {"requestId": "test", "_time": datetime.now(UTC).isoformat(), "event": event, "traceId": trace_id}
    [activity] = to_activity_requests(["test"], [dict(row, event="chat.request"), row], connected)
    assert activity.trace_url is None


def test_multiple_endings_are_ambiguous(connected: Settings) -> None:
    row: Row = {
        "requestId": "test",
        "_time": datetime.now(UTC).isoformat(),
        "event": "chat.done",
        "traceId": str(uuid4()),
    }
    [activity] = to_activity_requests(
        ["test"], [dict(row, event="chat.request"), row, dict(row, traceId=str(uuid4()))], connected
    )
    assert activity.trace_url is None


def test_link_ages_out_with_chat_start_even_if_ending_is_still_visible(connected: Settings) -> None:
    now = datetime.now(UTC)
    beginning: Row = {"requestId": "test", "_time": (now - timedelta(days=7)).isoformat(), "event": "chat.request"}
    end: Row = dict(beginning, event="chat.done", traceId=str(uuid4()), _time=(now - timedelta(days=6)).isoformat())
    [activity] = to_activity_requests(["test"], [beginning, end], connected)
    assert activity.trace_url is None


def playground_row(**changes: object) -> Row:
    """A synthetic standalone retrieval completion, with the same fields as the real Playground log."""
    return {
        "requestId": "retrieval-abcd1234",
        "_time": datetime.now(UTC).isoformat(),
        "event": "knowledge.call",
        "tool": "retrieval_playground",
        "status": "found",
        "ms": 350,
        "traceId": str(uuid4()),
        **changes,
    }


def test_standalone_playground_trace_is_linked_without_a_chat_ending(connected: Settings) -> None:
    row = playground_row()
    [activity] = to_activity_requests(["retrieval-abcd1234"], [row], connected)
    assert not activity.is_chat
    assert activity.trace_url is not None
    handle = activity.trace_url.rsplit("/", 1)[-1]
    assert resolve_trace_link(connected, handle, datetime.now(UTC)) == (UUID(str(row["traceId"])), "abcd1234")


@pytest.mark.parametrize(
    "changes",
    [
        {"tool": "search_park_guidance"},
        {"tool": "unapproved"},
        {"traceId": "../other"},
        {"traceId": ""},
        {"ms": True},
        {"ms": -1},
        {"ms": 60_001},
        {"ms": float("nan")},
        {"ms": "350"},
        {"ms": None},
        {"_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    ],
)
def test_only_valid_bounded_playground_operations_get_links(connected: Settings, changes: dict[str, object]) -> None:
    [activity] = to_activity_requests(["retrieval-abcd1234"], [playground_row(**changes)], connected)
    assert activity.trace_url is None


@pytest.mark.parametrize("extra", ["duplicate", "other_retrieval", "chat.request", "chat.done", "reused_trace"])
def test_ambiguous_or_mixed_playground_operations_are_not_linked(connected: Settings, extra: str) -> None:
    row = playground_row()
    additional = dict(row)
    if extra == "other_retrieval":
        additional["traceId"] = str(uuid4())
    elif extra in {"chat.request", "chat.done"}:
        additional["event"] = extra
        additional["traceId"] = ""
    elif extra == "reused_trace":
        additional["requestId"] = "other-request"
    [activity] = to_activity_requests(["retrieval-abcd1234"], [row, additional], connected)
    assert activity.trace_url is None


def test_playground_trace_ages_out_with_its_start_time(connected: Settings) -> None:
    row = playground_row(_time=(datetime.now(UTC) - timedelta(days=7) + timedelta(seconds=30)).isoformat(), ms=60_000)
    [activity] = to_activity_requests(["retrieval-abcd1234"], [row], connected)
    assert activity.trace_url is None


@pytest.mark.parametrize(
    ("workflow", "has_trace", "expected"),
    [
        ("briefing", False, "Nimbus built this park briefing directly without a model call."),
        ("intake", False, "Nimbus handled this clarification directly without a model call."),
        ("agent", False, "No linked LangSmith trace for this request."),
        ("", False, "No linked LangSmith trace for this request."),
        ("briefing", True, "View LangSmith trace"),
        ("intake", True, "View LangSmith trace"),
    ],
)
def test_missing_trace_explanation_requires_explicit_direct_workflow(
    client: TestClient, connected: Settings, workflow: str, has_trace: bool, expected: str
) -> None:
    app = cast(FastAPI, client.app)
    app.state.settings = connected
    ending: Row = {
        "requestId": "test-direct",
        "_time": datetime.now(UTC).isoformat(),
        "event": "chat.done",
        "workflow": workflow,
        # Legacy flags alone must not assert that a model trace was never created.
        "tripForm": False,
        "traceId": str(uuid4()) if has_trace else "",
    }
    recording = AxiomRecordings(
        {
            "summarize started": [ending],
            "where requestId in": [dict(ending, event="chat.request", traceId=""), ending],
        }
    )
    app.state.axiom_query = AxiomQuery(
        SecretStr("test-read"), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(recording))
    )
    response = client.get("/activity")
    assert response.status_code == 200
    assert expected in response.text
    if has_trace:
        assert 'href="/activity/trace/' in response.text
        assert "no LangSmith model trace was created" not in response.text
        assert "No LangSmith model trace was created" not in response.text
    elif workflow in {"briefing", "intake"}:
        assert "No linked LangSmith trace for this request." not in response.text
    else:
        assert "without a model call" not in response.text


def test_ambiguous_workflows_do_not_explain_trace_absence(connected: Settings) -> None:
    ending: Row = {
        "requestId": "test",
        "_time": datetime.now(UTC).isoformat(),
        "event": "chat.done",
        "workflow": "intake",
    }
    [activity] = to_activity_requests(
        ["test"], [dict(ending, event="chat.request"), ending, dict(ending, workflow="agent")], connected
    )
    assert activity.trace_note == ""


def test_unlinkable_recorded_trace_does_not_claim_it_was_never_created(connected: Settings) -> None:
    ending: Row = {
        "requestId": "test",
        "_time": (datetime.now(UTC) - timedelta(days=7)).isoformat(),
        "event": "chat.done",
        "workflow": "intake",
        "traceId": str(uuid4()),
    }
    [activity] = to_activity_requests(["test"], [dict(ending, event="chat.request"), ending], connected)
    assert activity.trace_url is None
    assert activity.trace_note == ""


def test_activity_reads_one_trace_only_after_click_and_limits_refreshes(
    client: TestClient, connected: Settings
) -> None:
    app = cast(FastAPI, client.app)
    app.state.settings = connected
    now, root = datetime.now(UTC).isoformat(), uuid4()
    endings = [
        {"requestId": "private-12345678", "_time": now, "event": "chat.failed", "traceId": str(root)},
        {"requestId": "private-old", "_time": now, "event": "chat.done"},
    ]
    recording = AxiomRecordings(
        {
            "summarize started": endings,
            "where requestId in": [dict(row, event="chat.request", traceId="") for row in endings] + endings,
        }
    )
    app.state.axiom_query = AxiomQuery(
        SecretStr("test-read"), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(recording))
    )
    calls: list[UUID] = []

    async def read(_settings: Settings, trace_id: UUID) -> TraceView:
        calls.append(trace_id)
        return TraceView("denied", issue=TraceIssue.ACCESS_DENIED)

    app.dependency_overrides[get_activity_trace_reader] = lambda: read
    activity = client.get("/activity")
    assert activity.status_code == 200
    [url] = re.findall(r'href="(/activity/trace/[^"]+)"', activity.text)
    assert "private-" not in activity.text
    assert not calls
    for invalid in (url.replace(root.hex, uuid4().hex), f"/activity/trace/{root}"):
        refused = client.get(invalid)
        assert refused.status_code == 404
        assert refused.headers["cache-control"] == "no-store"
    assert not calls
    with capture_logs() as events:
        result = client.get(url)
    assert result.status_code == 200
    assert TraceIssue.ACCESS_DENIED.value.replace("'", "&#39;") in result.text
    assert result.headers["cache-control"] == "no-store"
    assert [e["path"] for e in events if e["event"] == "http.request"] == ["/activity/trace"]
    assert calls == [root]
    for _ in range(11):
        assert client.get(url).status_code == 200
    busy = client.get(url)
    assert busy.status_code == 429
    assert busy.headers["retry-after"] == "60"
    assert busy.headers["cache-control"] == "no-store"
    assert "text/html" in busy.headers["content-type"]
    assert calls == [root] * 12
