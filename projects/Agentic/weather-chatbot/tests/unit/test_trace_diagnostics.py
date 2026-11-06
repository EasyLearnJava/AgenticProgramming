"""Trace reader failures distinguish the operation that failed without publishing private upstream details."""

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langsmith import utils as smith
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.observability import get_activity_trace_reader
from nimbus.trace_links import trace_url
from nimbus.trace_view import TraceIssue, TraceView, read_trace

PRIVATE = "private upstream error with visitor input"


@pytest.mark.parametrize(
    ("stage", "status", "issue"),
    [
        ("project", 429, TraceIssue.RATE_LIMITED),
        ("runs", 503, TraceIssue.SERVICE_ERROR),
        ("runs", 422, TraceIssue.REQUEST_REJECTED),
        ("runs", 403, TraceIssue.ACCESS_DENIED),
    ],
)
def test_logs_only_the_stage_fixed_reason_and_upstream_status(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, stage: str, status: int, issue: TraceIssue
) -> None:
    project, workspace, trace = uuid4(), uuid4(), uuid4()
    monkeypatch.setattr(smith, "get_workspace_id", lambda _: str(workspace))
    settings = settings.model_copy(
        update={
            "langsmith_tracing": True,
            "langsmith_api_key": SecretStr("synthetic-key"),
            "langsmith_hide_inputs": True,
            "langsmith_hide_outputs": True,
            "langsmith_project": "private-project",
        }
    )

    def respond(request: httpx2.Request) -> httpx2.Response:
        if stage == "runs" and request.url.path.endswith("/sessions"):
            return httpx2.Response(
                200, json=[{"id": str(project), "tenant_id": str(workspace), "name": "private-project"}]
            )
        return httpx2.Response(status, text=PRIVATE)

    with capture_logs() as logs:
        result = asyncio.run(read_trace(settings, trace, transport=httpx2.MockTransport(respond)))
    assert result.issue == issue
    assert PRIVATE not in repr(result)
    [failure] = [record for record in logs if record["event"] == "langsmith.read_failed"]
    assert failure == {
        "event": "langsmith.read_failed",
        "stage": stage,
        "reason": issue.name.lower(),
        "httpStatus": status,
        "log_level": "warning",
    }


def test_trace_page_renders_the_fixed_diagnosis_without_upstream_text(client: TestClient, settings: Settings) -> None:
    app = cast(FastAPI, client.app)
    settings = settings.model_copy(update={"axiom_query_token": SecretStr("test-read")})
    app.state.settings = settings
    now = datetime.now(UTC)
    url = trace_url(settings, str(uuid4()), now, "abcdef", now)
    assert url is not None

    async def failed(_settings: Settings, _trace_id: UUID) -> TraceView:
        return TraceView("unavailable", issue=TraceIssue.RATE_LIMITED)

    app.dependency_overrides[get_activity_trace_reader] = lambda: failed
    page = client.get(url)
    assert page.status_code == 200
    assert TraceIssue.RATE_LIMITED.value in page.text
    assert "could not read the trace" not in page.text
    assert page.headers["cache-control"] == "no-store"
