"""LangSmith's project and trace APIs, exercised offline at the HTTP boundary with realistic v2 responses."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

import httpx2
import pytest
from langsmith import utils as smith
from pydantic import SecretStr

from nimbus import trace_view
from nimbus.config import Settings
from nimbus.trace_view import TraceIssue, TraceRow, TraceView, read_trace

TRACE = UUID(int=101)
PROJECT = UUID(int=102)
OTHER = UUID(int=103)
PROJECTS = [{"id": str(PROJECT), "name": "weather"}]
PRIVATE = "private visitor text and credential"


@pytest.mark.parametrize(
    ("operation", "label"),
    [("read", "Mem0 read"), ("save", "Mem0 save"), ("delete", "Mem0 delete")],
)
@pytest.mark.parametrize("status", ["SUCCESS", "ERROR"])
def test_memory_roots_show_only_fixed_names_timings_and_outcomes(
    traced: Settings, operation: str, label: str, status: str
) -> None:
    """A memory-only request has its own safe trace, without fetching or exposing saved preferences."""
    result = with_runs(
        traced,
        span(
            name=f"mem0.{operation}",
            run_type="TOOL",
            status=status,
            inputs={"user_id": PRIVATE},
            outputs={"preferences": PRIVATE},
            metadata={"key": PRIVATE},
            error=PRIVATE,
        ),
    )
    assert result.status == "ready"
    row = result.rows[0]
    assert row.label == label
    assert row.kind == "Memory"
    assert row.elapsed_ms == 800
    assert row.parent_index is None
    assert row.status == ("Completed" if status == "SUCCESS" else "Failed")
    assert bool(row.error) == (status == "ERROR")
    assert PRIVATE not in str(result)


@pytest.mark.parametrize(("name", "kind"), [("mem0.read", "CHAIN"), ("mem0.save", "LLM"), ("mem0.search", "TOOL")])
def test_memory_root_allowlist_requires_exact_operation_and_run_type(traced: Settings, name: str, kind: str) -> None:
    """A similar name or a different run kind must not broaden access to arbitrary traces."""
    result = with_runs(traced, span(name=name, run_type=kind))
    assert result.status == "unavailable"
    assert result.issue == TraceIssue.WRONG_ROOT


def test_a_chat_request_root_shows_its_mem0_read_cache_steps_and_nested_agent(traced: Settings) -> None:
    """A chat request's trace holds Mem0, the weather answer cache and the agent's own calls under one root."""
    read, lookup, graph, model, tool, store = (UUID(int=value) for value in range(700, 706))
    inside = [str(TRACE), str(graph)]
    result = with_runs(
        traced,
        span(name="nimbus.chat"),
        span(read, name="mem0.read", run_type="TOOL", start_time="2026-11-05T12:00:00.010Z"),
        span(lookup, name="weather_cache.lookup", start_time="2026-11-05T12:00:00.050Z"),
        span(graph, start_time="2026-11-05T12:00:00.100Z"),
        span(
            model,
            name="ChatGoogleGenerativeAI",
            run_type="LLM",
            parent_run_ids=inside,
            start_time="2026-11-05T12:00:00.200Z",
        ),
        span(tool, name="get_forecast", run_type="TOOL", parent_run_ids=inside, start_time="2026-11-05T12:00:00.300Z"),
        span(store, name="weather_cache.store", start_time="2026-11-05T12:00:00.700Z"),
    )
    assert result.status == "ready"
    assert [(row.kind, row.label) for row in result.rows] == [
        ("Agent", "Chat request"),
        ("Memory", "Mem0 read"),
        ("Step", "Weather answer cache lookup"),
        ("Agent", "Nimbus agent"),
        ("Model", "Gemini"),
        ("Tool", "get_forecast"),
        ("Step", "Weather answer cache store"),
    ]
    assert [row.parent_index for row in result.rows] == [None, 0, 0, 0, 3, 3, 0]


@pytest.mark.parametrize("kind", ["TOOL", "LLM"])
def test_a_chat_request_root_requires_its_exact_run_type(traced: Settings, kind: str) -> None:
    """The request's name alone doesn't open a trace: it must be a chain, as Nimbus writes it."""
    result = with_runs(traced, span(name="nimbus.chat", run_type=kind))
    assert result.status == "unavailable"
    assert result.issue == TraceIssue.WRONG_ROOT


@pytest.mark.parametrize(
    ("name", "label"),
    [
        ("qdrant.exact_match", "Qdrant exact match"),
        ("qdrant.similarity_search", "Qdrant similarity search"),
        ("qdrant.remove_expired", "Qdrant remove expired"),
        ("qdrant.count", "Qdrant count"),
        ("qdrant.save", "Qdrant save"),
    ],
)
@pytest.mark.parametrize("status", ["SUCCESS", "ERROR"])
def test_qdrant_steps_keep_real_parents_safe_outcomes_and_errors(
    traced: Settings, name: str, label: str, status: str
) -> None:
    """Each provider operation stays below its cache step, without becoming a model or weather-tool call."""
    parent, child = UUID(int=740), UUID(int=741)
    view = with_runs(
        traced,
        span(name="nimbus.chat", metadata={"cache_outcome": "miss", "private": PRIVATE}),
        span(parent, name="weather_cache.lookup", start_time="2026-11-05T12:00:00.010Z"),
        span(
            child,
            name=name,
            parent_run_ids=[str(TRACE), str(parent)],
            start_time="2026-11-05T12:00:00.020Z",
            status=status,
            error=PRIVATE,
            metadata={"outcome": "error" if status == "ERROR" else "completed", "private": PRIVATE},
        ),
    )
    assert view.status == "ready"
    row = view.rows[-1]
    assert (row.kind, row.label, row.parent_index, row.depth) == ("Step", label, 1, 2)
    assert row.status == ("Failed" if status == "ERROR" else "Completed")
    assert row.outcome == ("Error" if status == "ERROR" else "Completed")
    assert bool(row.error) is (status == "ERROR")
    assert view.rows[0].outcome == "Miss"
    assert PRIVATE not in str(view)


def test_similarity_metrics_are_numeric_only_and_only_for_the_similarity_step(traced: Settings) -> None:
    """Unrelated runs cannot present arbitrary metadata as a cache decision or score."""
    metadata = {"outcome": "semantic_hit", "similarity_score": 0.87, "similarity_threshold": 0.8, "secret": PRIVATE}
    view = with_runs(
        traced,
        span(name="nimbus.chat", metadata={"cache_outcome": "semantic_hit"}),
        span(UUID(int=742), name="qdrant.similarity_search", metadata=metadata),
        span(UUID(int=743), name="qdrant.count", metadata=metadata),
        span(UUID(int=744), name="get_forecast", run_type="TOOL", metadata=metadata),
    )
    similarity, count, tool = view.rows[1:]
    assert (similarity.outcome, similarity.similarity_score, similarity.similarity_threshold) == (
        "Similarity hit",
        0.87,
        0.8,
    )
    assert count.similarity_score is count.similarity_threshold is None
    assert tool.outcome == ""
    assert tool.similarity_score is tool.similarity_threshold is None
    assert PRIVATE not in str(view)


@pytest.mark.parametrize("value", [True, "0.90", float("nan"), float("inf"), -1.1, 1.1, 10**400, {}, [0.9]])
def test_invalid_similarity_values_are_discarded_without_exposing_metadata(value: object) -> None:
    """Malformed, non-finite and excessively large values remain unavailable, never coerced into scores."""
    parsed = trace_view._Span.model_validate(
        span(
            UUID(int=745),
            name="qdrant.similarity_search",
            metadata={
                "outcome": PRIVATE,
                "similarity_score": value,
                "similarity_threshold": value,
                "browser_scope": PRIVATE,
            },
        )
    )
    assert parsed.metadata.outcome == ""
    assert parsed.metadata.similarity_score is parsed.metadata.similarity_threshold is None
    assert PRIVATE not in str(parsed)


def test_only_a_chat_root_can_display_allowlisted_cache_bypass_reasons(traced: Settings) -> None:
    """A request may explain a skipped cache check using a fixed reason, never a question or provider message."""
    metadata = {"cache_outcome": "bypass", "cache_bypass_reason": "unverified_history", "question": PRIVATE}
    view = with_runs(
        traced,
        span(name="nimbus.chat", metadata=metadata),
        span(UUID(int=746), name="weather_cache.lookup", metadata=metadata),
    )
    assert view.rows[0].outcome == "Bypassed"
    assert view.rows[0].cache_reason == "Conversation could not be verified"
    assert view.rows[1].cache_reason == ""
    assert PRIVATE not in str(view)
    unknown = with_runs(traced, span(name="nimbus.chat", metadata={**metadata, "cache_bypass_reason": PRIVATE}))
    assert unknown.rows[0].cache_reason == ""
    assert PRIVATE not in str(unknown)


@pytest.fixture
def traced(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(smith, "get_api_url", lambda _: "https://eu.api.smith.langchain.com/api/v1")
    monkeypatch.setattr(smith, "get_workspace_id", lambda _: str(OTHER))
    return settings.model_copy(
        update={
            "langsmith_api_key": SecretStr(" 'test-only' "),
            "langsmith_project": "weather",
            "langsmith_tracing": True,
            "langsmith_hide_inputs": True,
            "langsmith_hide_outputs": True,
        }
    )


def span(identifier: UUID = TRACE, /, **changes: object) -> dict[str, object]:
    return {
        "id": str(identifier),
        "trace_id": str(TRACE),
        "project_id": str(PROJECT),
        "parent_run_ids": [] if identifier == TRACE else [str(TRACE)],
        "name": "nimbus",
        "run_type": "CHAIN",
        "status": "SUCCESS",
        "start_time": "2026-11-05T12:00:00Z",
        "end_time": "2026-11-05T12:00:00.800Z",
        **changes,
    }


def ask(settings: Settings, handler: Callable[[httpx2.Request], httpx2.Response]) -> TraceView:
    return asyncio.run(read_trace(settings, TRACE, transport=httpx2.MockTransport(handler)))


def with_runs(settings: Settings, *spans: dict[str, object]) -> TraceView:
    return ask(
        settings,
        lambda req: httpx2.Response(
            200, json=PROJECTS if req.url.path.endswith("/sessions") else {"items": list(spans)}
        ),
    )


def test_one_trace_in_one_project_selects_only_operational_fields(traced: Settings) -> None:
    requests = []
    chain = span(OTHER, name="model")
    model = span(
        UUID(int=200),
        run_type="LLM",
        name="ChatGoogleGenerativeAI",
        parent_run_ids=[str(TRACE), str(OTHER)],
        start_time="2026-11-05T12:00:00.100Z",
    )
    tool = span(
        UUID(int=201),
        run_type="TOOL",
        name="get_forecast",
        status="ERROR",
        start_time="2026-11-05T12:00:00.660Z",
        end_time="2026-11-05T12:00:00.672Z",
        error=PRIVATE,
    )

    def recording(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/sessions"):
            return httpx2.Response(200, json=PROJECTS)
        return httpx2.Response(200, json={"items": [tool, model, chain, span()]})

    result = ask(traced, recording)
    project_request, trace_request = requests
    for request in requests:
        assert request.method == "GET"
        assert request.url.host == "eu.api.smith.langchain.com"
        assert request.headers["X-Api-Key"] == "test-only"
        assert request.headers["X-Tenant-Id"] == str(OTHER)
        assert "test-only" not in str(request.url)
    assert project_request.url.path == "/api/v1/sessions"
    assert dict(project_request.url.params) == {"name": "weather", "limit": "1"}
    assert trace_request.url.path == f"/api/v2/traces/{TRACE}/runs"
    params = trace_request.url.params
    assert params["project_id"] == str(PROJECT)
    assert datetime.fromisoformat(params["max_start_time"]) - datetime.fromisoformat(params["min_start_time"]) == (
        timedelta(days=7)
    )
    assert set(params.get_list("selects")) == {
        "ID",
        "NAME",
        "TRACE_ID",
        "PROJECT_ID",
        "PARENT_RUN_IDS",
        "RUN_TYPE",
        "STATUS",
        "START_TIME",
        "END_TIME",
        "METADATA",
    }
    assert result == TraceView(
        "ready",
        (
            TraceRow("Nimbus agent", "Agent", 800, 0, 0, "Completed"),
            TraceRow("Gemini", "Model", 700, 100, 1, "Completed", parent_index=0),
            TraceRow("get_forecast", "Tool", 12, 660, 1, "Failed", "Tool reported an error.", parent_index=0),
        ),
    )


def test_key_only_project_lookup_supplies_workspace_for_v2(traced: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """The v1 project resource authenticates a single-workspace key alone; v2 also needs its tenant header."""
    monkeypatch.setattr(smith, "get_workspace_id", lambda _: None)
    seen = []

    def langsmith(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("/sessions"):
            assert "x-tenant-id" not in request.headers
            return httpx2.Response(200, json=[{**PROJECTS[0], "tenant_id": str(OTHER)}])
        if request.headers.get("x-tenant-id") != str(OTHER):
            return httpx2.Response(400)
        assert request.url.params["project_id"] == str(PROJECT)
        return httpx2.Response(200, json={"items": [span()]})

    view = ask(traced, langsmith)
    assert view.status == "ready"
    assert view.rows[0].label == "Nimbus agent"
    assert seen == ["/api/v1/sessions", f"/api/v2/traces/{TRACE}/runs"]


@pytest.mark.parametrize("lowercase", [False, True])
def test_wire_enum_casing_preserves_model_tool_and_error_rows(traced: Settings, lowercase: bool) -> None:
    """Run types and statuses are enums; their casing must not reject a valid, scoped Nimbus trace."""
    runs = [
        span(),
        span(OTHER, run_type="LLM", name="ChatGoogleGenerativeAI", status="PENDING", end_time=None),
        span(UUID(int=200), run_type="TOOL", name="get_forecast", status="ERROR"),
        span(UUID(int=201), run_type="CHAIN", name="model", status="ERROR"),
    ]
    if lowercase:
        for run in runs:
            for field in ("run_type", "status"):
                run[field] = str(run[field]).lower()
    view = with_runs(traced, *runs)
    assert view.status == "ready"
    assert [(row.kind, row.label, row.status, row.error) for row in view.rows] == [
        ("Agent", "Nimbus agent", "Completed", None),
        ("Model", "Gemini", "Running", None),
        ("Tool", "get_forecast", "Failed", "Tool reported an error."),
        ("Step", "Model step", "Failed", "Step reported an error."),
    ]


def test_project_cannot_switch_configured_workspace(traced: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smith, "get_workspace_id", lambda _: None)
    traced = traced.model_copy(update={"langsmith_workspace_id": OTHER})

    def project_only(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/sessions")
        assert request.headers.get("x-tenant-id") == str(OTHER)
        return httpx2.Response(200, json=[{**PROJECTS[0], "tenant_id": str(UUID(int=999))}])

    assert ask(traced, project_only).status == "unavailable"


def test_missing_workspace_stops_before_v2(traced: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smith, "get_workspace_id", lambda _: None)

    def project_only(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/sessions")
        return httpx2.Response(200, json=PROJECTS)

    assert ask(traced, project_only).status == "unavailable"


def test_provider_text_is_never_a_public_label_status_or_error(traced: Settings) -> None:
    result = with_runs(
        traced,
        span(inputs=PRIVATE, outputs=PRIVATE, metadata={"location": PRIVATE}),
        span(OTHER, run_type="TOOL", name=PRIVATE, status=PRIVATE, end_time=None),
        span(UUID(int=200), run_type="CHAIN", name=PRIVATE, status="ERROR", error=f"secret: {PRIVATE}"),
        span(UUID(int=201), run_type="LLM", name=PRIVATE, status="PENDING", end_time=None),
    )
    assert PRIVATE not in repr(result)
    assert [(row.label, row.status, row.elapsed_ms) for row in result.rows[1:]] == [
        ("Tool call", "Unknown", None),
        ("Graph step", "Failed", 800),
        ("Model call", "Running", None),
    ]


@pytest.mark.parametrize("field", ["langsmith_tracing", "langsmith_hide_inputs", "langsmith_hide_outputs"])
def test_missing_privacy_setting_never_asks_langsmith(traced: Settings, field: str) -> None:
    assert ask(traced.model_copy(update={field: False}), lambda _: pytest.fail("Contacted LangSmith")) == (
        TraceView("disabled")
    )


def test_no_key_never_asks_langsmith(traced: Settings) -> None:
    assert ask(traced.model_copy(update={"langsmith_api_key": None}), lambda _: pytest.fail("Contacted LangSmith")) == (
        TraceView("disabled")
    )


@pytest.mark.parametrize(
    ("response", "issue"),
    [
        ([], TraceIssue.PROJECT_NOT_FOUND),
        ({}, TraceIssue.INVALID_RESPONSE),
        ([{"name": "different", "id": str(OTHER)}], TraceIssue.WRONG_SCOPE),
    ],
)
def test_no_verified_project_stops_before_the_trace_query(
    traced: Settings, response: object, issue: TraceIssue
) -> None:
    def project(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/sessions")
        return httpx2.Response(200, json=response)

    assert ask(traced, project) == TraceView("unavailable", issue=issue)


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        ({"trace_id": str(OTHER)}, TraceIssue.WRONG_SCOPE),
        ({"project_id": str(OTHER)}, TraceIssue.WRONG_SCOPE),
        ({"name": "different root"}, TraceIssue.WRONG_ROOT),
        ({"name": "Nimbus", "run_type": "chain"}, TraceIssue.WRONG_ROOT),
        ({"run_type": "tool"}, TraceIssue.WRONG_ROOT),
        ({"run_type": "llm"}, TraceIssue.WRONG_ROOT),
        ({"start_time": "bad"}, TraceIssue.INVALID_RESPONSE),
    ],
)
def test_mismatched_or_malformed_spans_are_unavailable(
    traced: Settings, changes: dict[str, object], issue: TraceIssue
) -> None:
    assert with_runs(traced, span(**changes)) == TraceView("unavailable", issue=issue)


@pytest.mark.parametrize(
    ("code", "issue"),
    [
        (302, TraceIssue.REQUEST_REJECTED),
        (401, TraceIssue.ACCESS_DENIED),
        (403, TraceIssue.ACCESS_DENIED),
        (429, TraceIssue.RATE_LIMITED),
        (500, TraceIssue.SERVICE_ERROR),
    ],
)
def test_http_errors_are_private_and_redirects_do_not_forward_the_key(
    traced: Settings, code: int, issue: TraceIssue
) -> None:
    def reject(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "eu.api.smith.langchain.com"
        return httpx2.Response(code, text=PRIVATE, headers={"Location": "https://unexpected.example/"})

    assert ask(traced, reject) == TraceView("denied" if code in (401, 403) else "unavailable", issue=issue)


def test_wait_for_root_when_trace_is_missing_or_still_arriving(traced: Settings) -> None:
    assert with_runs(traced) == TraceView("pending")
    assert with_runs(traced, span(OTHER)) == TraceView("pending")
    assert ask(
        traced,
        lambda req: httpx2.Response(200, json=PROJECTS) if req.url.path.endswith("/sessions") else httpx2.Response(404),
    ) == TraceView("pending")


def test_large_trace_is_labeled_when_display_rows_are_limited(
    traced: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(trace_view, "TRACE_MAX_ROWS", 1)
    result = with_runs(traced, span(), span(OTHER, run_type="LLM"))
    assert result == TraceView("ready", (TraceRow("Nimbus agent", "Agent", 800, 0, 0, "Completed"),), truncated=True)


def test_malformed_and_oversized_bodies_and_network_errors_are_unavailable(
    traced: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(PRIVATE, request=request)

    assert ask(traced, broken) == TraceView("unavailable", issue=TraceIssue.UNREACHABLE)
    assert ask(traced, lambda _: httpx2.Response(200, text="not JSON")) == TraceView(
        "unavailable", issue=TraceIssue.INVALID_RESPONSE
    )
    monkeypatch.setattr(trace_view, "TRACE_MAX_BYTES", 100)
    assert with_runs(traced, span()) == TraceView("unavailable", issue=TraceIssue.TOO_LARGE)


def test_deadline_cancels_the_request(traced: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_view, "TRACE_SECONDS", 0.02)
    cancelled = []

    async def slow(request: httpx2.Request) -> httpx2.Response:
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)
        return httpx2.Response(200, json=PROJECTS)

    assert asyncio.run(read_trace(traced, TRACE, transport=httpx2.MockTransport(slow))) == TraceView(
        "unavailable", issue=TraceIssue.TIMED_OUT
    )
    assert cancelled == [True]


def test_public_trace_messages_name_no_setting_or_server_detail() -> None:
    # The trace page is public: its messages speak to a visitor; the cause goes to the server's log by enum name.
    for issue in TraceIssue:
        assert "LANGSMITH" not in issue.value
        assert "log" not in issue.value.lower()
        assert "key" not in issue.value.lower()
    assert len({issue.value for issue in TraceIssue}) == len(TraceIssue)


def test_parent_indices_preserve_parallel_nested_spans_with_an_unordered_ancestor_array(traced: Settings) -> None:
    outer, sibling, inner, hidden = (UUID(int=value) for value in (500, 501, 502, 503))
    view = with_runs(
        traced,
        span(),
        span(outer, run_type="TOOL", name="get_forecast", start_time="2026-11-05T12:00:00.100Z"),
        span(sibling, run_type="TOOL", name="get_current_weather", start_time="2026-11-05T12:00:00.101Z"),
        span(hidden, name="tools", parent_run_ids=[str(TRACE), str(outer)]),
        span(
            inner,
            run_type="TOOL",
            name="get_forecast",
            parent_run_ids=[str(hidden), str(outer), str(TRACE)],
            start_time="2026-11-05T12:00:00.102Z",
        ),
    )
    assert [row.parent_index for row in view.rows] == [None, 0, 0, 1]
    assert [row.depth for row in view.rows] == [0, 1, 1, 2]
    assert view.rows[1].label == view.rows[3].label == "get_forecast"
    assert str(outer) not in repr(view)
    assert str(inner) not in repr(view)


def test_duplicate_provider_span_ids_cannot_create_ambiguous_public_relationships(traced: Settings) -> None:
    result = with_runs(traced, span(), span(OTHER, run_type="TOOL"), span(OTHER, run_type="LLM"))
    assert result.status == "unavailable"
    assert result.issue == TraceIssue.INVALID_RESPONSE


def test_direct_parent_links_cross_filtered_graph_wrappers(traced: Settings) -> None:
    hidden, model = UUID(int=600), UUID(int=601)
    result = with_runs(
        traced,
        span(),
        span(hidden, name="model", parent_run_ids=[str(TRACE)]),
        span(model, run_type="LLM", name="ChatGoogleGenerativeAI", parent_run_ids=[str(hidden)]),
    )
    assert len(result.rows) == 2
    assert result.rows[1].parent_index == 0
    assert result.rows[1].depth == 1


def test_cyclic_or_missing_ancestors_do_not_create_false_nesting(traced: Settings) -> None:
    a, b, absent = UUID(int=500), UUID(int=501), UUID(int=999)
    result = with_runs(
        traced,
        span(),
        span(a, run_type="TOOL", name="get_forecast", parent_run_ids=[str(TRACE), str(b)]),
        span(b, run_type="TOOL", name="get_current_weather", parent_run_ids=[str(TRACE), str(a)]),
        span(OTHER, run_type="LLM", parent_run_ids=[str(absent)]),
    )
    assert result.status == "ready"
    assert all(row.parent_index is None for row in result.rows)
    assert all(row.depth == 0 for row in result.rows)
