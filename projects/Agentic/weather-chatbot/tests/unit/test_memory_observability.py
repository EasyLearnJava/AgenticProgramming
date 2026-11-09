"""Memory appears on Activity as safe operations, with honest outcomes and no preference contents."""

import re
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nimbus.axiom_query import AxiomQuery, Row
from nimbus.config import Settings
from nimbus.observability import (
    ACTIVITY_VIEWS,
    TIMELINE_EVENTS,
    TIMELINE_FIELDS,
    get_activity_trace_reader,
    to_activity_line,
    to_activity_requests,
    to_narrowing,
    to_timeline_query,
)
from nimbus.trace_links import resolve_trace_link
from nimbus.trace_view import TraceRow, TraceView
from tests.fakes import AxiomRecordings

REQUEST_ID = "memory-synthetic-12345678"


def event(name: str = "memory.operation", **fields: object) -> Row:
    """Use the real runtime's public metadata shape, with no visitor data needed to render a timeline."""
    return {
        "_time": datetime.now(UTC).isoformat(),
        "requestId": REQUEST_ID,
        "event": name,
        "ms": 120,
        "tool": "memory_preferences",
        **fields,
    }


@pytest.mark.parametrize(
    ("action", "status", "phrase", "tone"),
    [
        ("save", "ready", "save confirmed", "ok"),
        ("forget", "empty", "deletion confirmed", "ok"),
        ("read", "empty", "no saved preferences", "idle"),
        ("pause", "ready", "saved preferences retained", "idle"),
        ("resume", "ready", "preference use resumed", "ok"),
        ("save", "pending", "awaiting confirmation", "warn"),
        ("forget", "pending", "awaiting confirmation", "warn"),
        ("save", "conflict", "needs review", "warn"),
        ("read", "unavailable", "unavailable", "bad"),
        ("forget", "unavailable", "unavailable", "bad"),
    ],
)
def test_memory_operation_outcomes_distinguish_confirmed_uncertain_and_unavailable(
    action: str, status: str, phrase: str, tone: str
) -> None:
    """HTTP success never turns an unconfirmed save or deletion into a successful memory operation."""
    rows = [event(action=action, status=status), event("http.request", status=200)]
    item = to_activity_requests([REQUEST_ID], rows)[0]
    assert phrase in item.summary.detail
    assert "120 ms" in item.summary.detail
    assert item.summary.tone == tone
    assert not item.is_chat
    assert item.trace_url is None
    assert all("token" not in line.detail for _, line in item.steps)


def test_failed_memory_lookup_warns_on_a_chat_that_otherwise_answers() -> None:
    """The model answer can succeed while its unavailable preferences remain visible in the same timeline."""
    rows = [
        event("chat.request", lane="rest-open"),
        event(action="read", status="unavailable", reason="authentication_failed"),
        event("chat.done", workflow="agent", toolCalls=0),
    ]
    item = to_activity_requests([REQUEST_ID], rows)[0]
    assert item.summary.what == "Answered"
    assert item.summary.tone == "warn"
    assert "1 line went wrong" in item.summary.detail
    assert any("authentication failed" in line.detail for _, line in item.steps)


def test_memory_preview_is_not_reported_as_a_save_or_model_answer() -> None:
    """An explicit preview remains distinguishable from the later user-authorized write."""
    rows = [event("chat.request"), event("chat.done", workflow="intake", memoryIntake=True, toolCalls=0)]
    item = to_activity_requests([REQUEST_ID], rows)[0]
    assert item.summary.what == "Preference review"
    assert "token" not in item.summary.detail
    assert "without a model call" in item.trace_note
    assert "did not save" in item.trace_note


def test_unknown_metadata_and_private_record_content_never_reach_activity() -> None:
    """Even an unexpectedly contaminated event cannot make arbitrary provider or profile text public."""
    private = "private-airport-key-cookie-question-record"
    row = event(
        action=private,
        status=private,
        reason=private,
        tool=private,
        preferences={"origin": private},
        user_id=private,
        memory_ids=[private],
        cookie=private,
        question=private,
        api_key=private,
    )
    line = to_activity_line(row)
    assert line is not None
    assert line.what == "Preference memory"
    assert line.tone == "warn"
    assert "outcome unavailable" in line.detail
    assert private not in str(line)
    assert not {"preferences", "user_id", "memory_ids", "cookie", "question", "api_key"} & set(TIMELINE_FIELDS)


def test_memory_filter_names_operations_and_projects_only_safe_fields() -> None:
    """Settings-page requests belong to memory operations, rather than to questions that called a chat tool."""
    narrowing = to_narrowing({"tool": "memory_preferences"})
    assert narrowing is not None
    assert narrowing.words == "Preference memory operations"
    assert '"memory.operation"' in narrowing.where
    query = " ".join(to_timeline_query([REQUEST_ID]))
    assert "memory.operation" in TIMELINE_EVENTS
    assert "action = column_ifexists('action', '')" in query
    assert "memoryIntake = column_ifexists('memoryIntake', '')" in query
    assert '"unavailable", "pending", "conflict"' in ACTIVITY_VIEWS["errors"]


@pytest.mark.parametrize("address", ["/activity?show=memory", "/activity?tool=memory_preferences"])
def test_real_activity_page_shows_memory_timeline_without_private_fields(client: TestClient, address: str) -> None:
    """Exercise both navigation and narrowing through the real Axiom query adapter and rendered page."""
    private = "private-airport-key-cookie-question-record"
    rows = [
        event(action="save", status="pending", reason="pending_confirmation", preferences=private, user_id=private),
        event("http.request", status=409),
    ]
    recording = AxiomRecordings(
        {
            "summarize started": [{"requestId": REQUEST_ID}],
            "| project": rows,
        }
    )
    app = cast(FastAPI, client.app)
    token = SecretStr("synthetic-query-token")
    app.state.settings = app.state.settings.model_copy(
        update={"axiom_query_token": token, "axiom_dataset": "synthetic"}
    )
    app.state.axiom_query = AxiomQuery(token, lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(recording)))
    response = client.get(address)
    assert response.status_code == 200
    assert "Save preferences" in response.text
    assert "awaiting confirmation" in response.text
    assert 'data-tone="warn"' in response.text
    assert private not in response.text
    assert "Questions that called memory_preferences" not in response.text
    assert len(recording.queries) == 2
    assert 'event == "memory.operation"' in recording.queries[0] or '"memory.operation"' in recording.queries[0]
    if "show=memory" in address:
        assert 'href="/activity?show=memory" aria-current="page"' in response.text
        assert "Saved values, browser identities and conversation text are never shown here." in response.text
    else:
        assert "Preference memory operations" in response.text


@pytest.mark.parametrize(
    ("action", "label"), [("read", "Read preferences"), ("save", "Save preferences"), ("forget", "Delete preferences")]
)
def test_memory_operation_links_its_own_signed_root(settings: Settings, action: str, label: str) -> None:
    """Every provider operation can be opened independently without requiring a model call or chat ending."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    root = uuid4()
    [item] = to_activity_requests([REQUEST_ID], [event(action=action, status="ready", traceId=str(root))], connected)
    assert item.trace_url is None
    [link] = item.memory_traces
    assert link.label == label
    assert resolve_trace_link(connected, link.url.rsplit("/", 1)[-1], datetime.now(UTC)) == (root, item.ref)


def test_chat_read_and_model_trace_have_distinct_links(settings: Settings) -> None:
    """A memory read before the agent is visible without pretending the two roots are nested."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    memory_root, agent_root = uuid4(), uuid4()
    rows = [
        event("chat.request", lane="rest-open"),
        event(action="read", status="ready", traceId=str(memory_root)),
        event("chat.done", workflow="agent", traceId=str(agent_root)),
    ]
    [item] = to_activity_requests([REQUEST_ID], rows, connected)
    assert item.trace_url is not None
    assert agent_root.hex in item.trace_url
    [link] = item.memory_traces
    assert memory_root.hex in link.url
    assert link.url != item.trace_url


@pytest.mark.parametrize("action", ["pause", "resume", "private-action", ""])
def test_local_or_unknown_actions_cannot_issue_mem0_trace_links(settings: Settings, action: str) -> None:
    """A minted-looking ID is insufficient without a recognized provider operation."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    [item] = to_activity_requests([REQUEST_ID], [event(action=action, traceId=str(uuid4()))], connected)
    assert not item.memory_traces


@pytest.mark.parametrize("root", ["", "../private", "00000000-0000-0000-0000-000000000000", uuid4().hex])
def test_malformed_or_legacy_memory_roots_do_not_make_links(settings: Settings, root: str) -> None:
    """Only the exact canonical UUID4 format generated by Nimbus reaches the trace reader."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    [item] = to_activity_requests([REQUEST_ID], [event(action="read", traceId=root)], connected)
    assert not item.memory_traces


@pytest.mark.parametrize("second_event", ["memory.operation", "chat.done"])
def test_reused_memory_root_is_withheld(settings: Settings, second_event: str) -> None:
    """Conflicting evidence must not attach the same recorded root to unrelated operations."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    root = str(uuid4())
    rows = [event(action="read", traceId=root), event(second_event, action="save", traceId=root)]
    [item] = to_activity_requests([REQUEST_ID], rows, connected)
    assert not item.memory_traces


def test_distinct_memory_operations_keep_separate_ordered_links(settings: Settings) -> None:
    """A request containing more than one operation does not silently drop a save or deletion trace."""
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    read_root, save_root = uuid4(), uuid4()
    rows = [event(action="read", traceId=str(read_root)), event(action="save", traceId=str(save_root))]
    [item] = to_activity_requests([REQUEST_ID], rows, connected)
    assert [link.label for link in item.memory_traces] == ["Read preferences", "Save preferences"]
    assert read_root.hex in item.memory_traces[0].url
    assert save_root.hex in item.memory_traces[1].url


def test_memory_links_need_signing_configuration_and_recent_operation_start(settings: Settings) -> None:
    """An ending still inside the seven-day window cannot make an older operation readable."""
    row = event(action="read", traceId=str(uuid4()))
    assert not to_activity_requests([REQUEST_ID], [row], settings)[0].memory_traces
    assert not to_activity_requests([REQUEST_ID], [row])[0].memory_traces
    connected = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    row.update(_time=(datetime.now(UTC) - timedelta(days=7) + timedelta(seconds=1)).isoformat(), ms=2000)
    assert not to_activity_requests([REQUEST_ID], [row], connected)[0].memory_traces


def test_activity_opens_memory_trace_only_on_click_and_keeps_preview_explanation(client: TestClient) -> None:
    """The real HTML links separate operations while explaining that reviewing a preference did not save it."""
    app = cast(FastAPI, client.app)
    root = uuid4()
    private = "private-preference-key-record"
    rows = [
        event("chat.request"),
        event(action="read", status="ready", traceId=str(root), preferences=private, user_id=private),
        event("chat.done", workflow="intake", memoryIntake=True, toolCalls=0),
    ]
    recording = AxiomRecordings({"summarize started": [{"requestId": REQUEST_ID}], "| project": rows})
    token = SecretStr("synthetic-query-token")
    app.state.settings = app.state.settings.model_copy(
        update={"axiom_query_token": token, "axiom_dataset": "synthetic"}
    )
    app.state.axiom_query = AxiomQuery(token, lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(recording)))
    calls: list[UUID] = []

    async def read(_settings: Settings, trace_id: UUID) -> TraceView:
        """Return only the fixed public label; no provider payload is needed to render the trace."""
        calls.append(trace_id)
        return TraceView("ready", rows=(TraceRow("Mem0 read", "Memory", 120, 0, 0, "Completed"),))

    app.dependency_overrides[get_activity_trace_reader] = lambda: read
    response = client.get("/activity?show=memory")
    assert response.status_code == 200
    assert "Read preferences · Mem0 trace" in response.text
    assert "without a model call" in response.text
    assert "did not save any preferences" in response.text
    assert "No linked LangSmith trace for this request" not in response.text
    assert private not in response.text
    assert calls == []
    [url] = re.findall(r'href="(/activity/trace/[^"]+)"', response.text)
    result = client.get(url)
    assert result.status_code == 200
    assert "Mem0 read" in result.text
    assert result.headers["cache-control"] == "no-store"
    assert calls == [root]
