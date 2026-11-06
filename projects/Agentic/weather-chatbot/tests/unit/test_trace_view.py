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
from nimbus.trace_view import TraceRow, TraceView, read_trace

TRACE = UUID(int=101)
PROJECT = UUID(int=102)
OTHER = UUID(int=103)
PROJECTS = [{"id": str(PROJECT), "name": "weather"}]
PRIVATE = "private visitor text and credential"


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
    }
    assert result == TraceView(
        "ready",
        (
            TraceRow("Nimbus agent", "Agent", 800, 0, 0, "Completed"),
            TraceRow("Gemini", "Model", 700, 100, 1, "Completed"),
            TraceRow("get_forecast", "Tool", 12, 660, 1, "Failed", "Tool reported an error."),
        ),
    )


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


@pytest.mark.parametrize("response", [[], {}, [{"name": "different", "id": str(OTHER)}]])
def test_no_verified_project_stops_before_the_trace_query(traced: Settings, response: object) -> None:
    def project(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/sessions")
        return httpx2.Response(200, json=response)

    assert ask(traced, project) == TraceView("unavailable")


@pytest.mark.parametrize(
    "changes", [{"trace_id": str(OTHER)}, {"project_id": str(OTHER)}, {"name": "different root"}, {"start_time": "bad"}]
)
def test_mismatched_or_malformed_spans_are_unavailable(traced: Settings, changes: dict[str, object]) -> None:
    assert with_runs(traced, span(**changes)) == TraceView("unavailable")


@pytest.mark.parametrize("code", [302, 401, 403, 429, 500])
def test_http_errors_are_private_and_redirects_do_not_forward_the_key(traced: Settings, code: int) -> None:
    def reject(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "eu.api.smith.langchain.com"
        return httpx2.Response(code, text=PRIVATE, headers={"Location": "https://unexpected.example/"})

    assert ask(traced, reject) == TraceView("denied" if code in (401, 403) else "unavailable")


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

    assert ask(traced, broken) == TraceView("unavailable")
    assert ask(traced, lambda _: httpx2.Response(200, text="not JSON")) == TraceView("unavailable")
    monkeypatch.setattr(trace_view, "TRACE_MAX_BYTES", 100)
    assert with_runs(traced, span()) == TraceView("unavailable")


def test_deadline_cancels_the_request(traced: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_view, "TRACE_SECONDS", 0.02)
    cancelled = []

    async def slow(request: httpx2.Request) -> httpx2.Response:
        try:
            await asyncio.sleep(5)
        finally:
            cancelled.append(True)
        return httpx2.Response(200, json=PROJECTS)

    assert asyncio.run(read_trace(traced, TRACE, transport=httpx2.MockTransport(slow))) == TraceView("unavailable")
    assert cancelled == [True]
