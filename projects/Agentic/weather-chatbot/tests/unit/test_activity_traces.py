"""Activity links only recent, traced Nimbus chats to a bounded, same-site trace view."""

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
