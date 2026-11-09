"""Memory appears on Activity as safe operations, with honest outcomes and no preference contents."""

from datetime import UTC, datetime
from typing import cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nimbus.axiom_query import AxiomQuery, Row
from nimbus.observability import (
    ACTIVITY_VIEWS,
    TIMELINE_EVENTS,
    TIMELINE_FIELDS,
    to_activity_line,
    to_activity_requests,
    to_narrowing,
    to_timeline_query,
)
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
