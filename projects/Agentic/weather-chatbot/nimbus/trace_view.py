"""Read a single Nimbus trace from LangSmith and reduce it to fields safe for the public Activity page."""

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Final, Literal
from uuid import UUID

import httpx2
from langsmith import utils as smith
from pydantic import AwareDatetime, BaseModel, TypeAdapter

from nimbus.config import Settings
from nimbus.constants import AGENT_NAME, OBSERVABILITY_DAYS
from nimbus.model import is_tracing_allowed
from nimbus.tools import WEATHER_TOOLS
from nimbus.utils import to_iso, to_ms

TRACE_SECONDS = 5
TRACE_MAX_BYTES = 512 * 1024
TRACE_MAX_ROWS = 100
TRACE_TOOL_NAMES: Final = frozenset(tool.name for tool in WEATHER_TOOLS) | {
    "resolve_destination",
    "search_park_guidance",
    "get_park_alerts",
    "search_flights",
    "search_hotels",
}
STEP_LABELS = {"model": "Model step", "tools": "Tool step", "route": "Route tools"}
STATUSES = {"SUCCESS": "Completed", "ERROR": "Failed", "PENDING": "Running"}
# Ask only for identifiers, nesting, names, status and timestamps. Even error text can contain the question.
SELECTS = ("ID", "PROJECT_ID", "TRACE_ID", "PARENT_RUN_IDS", "NAME", "RUN_TYPE", "START_TIME", "END_TIME", "STATUS")


@dataclass(frozen=True)
class TraceRow:
    """One public span. The upstream's name and status are mapped to known labels."""

    label: str
    kind: str
    elapsed_ms: int | None
    offset_ms: int
    depth: int
    status: str
    error: str | None = None


@dataclass(frozen=True)
class TraceView:
    """The result of one on-demand lookup; only these projected rows can reach the template."""

    status: Literal["ready", "pending", "unavailable", "disabled", "denied"]
    rows: tuple[TraceRow, ...] = ()
    truncated: bool = False


class _Project(BaseModel):
    id: UUID
    name: str


class _Span(BaseModel):
    id: UUID
    trace_id: UUID
    project_id: UUID
    parent_run_ids: list[UUID] | None = None
    name: str
    run_type: str
    start_time: AwareDatetime
    end_time: AwareDatetime | None = None
    status: str | None = None


class _Runs(BaseModel):
    items: list[_Span]


def _label(span: _Span, root_id: UUID) -> tuple[str, str] | None:
    """Include the graph, model and tool calls, plus any other step that explains a failure."""
    if span.id == root_id:
        return "Agent", "Nimbus agent"
    if span.run_type == "LLM":
        return "Model", "Gemini" if span.name == "ChatGoogleGenerativeAI" else "Model call"
    if span.run_type == "TOOL":
        return "Tool", span.name if span.name in TRACE_TOOL_NAMES else "Tool call"
    if span.status == "ERROR":
        return "Step", STEP_LABELS.get(span.name, "Graph step")
    return None


def _to_view(spans: list[_Span], trace_id: UUID, project_id: UUID) -> TraceView:
    if any(span.trace_id != trace_id or span.project_id != project_id for span in spans):
        return TraceView("unavailable")
    root = next((span for span in spans if span.id == trace_id), None)
    if root is None:
        return TraceView("pending")
    if root.name != AGENT_NAME or root.run_type != "CHAIN":
        return TraceView("unavailable")
    labels = {span.id: display for span in spans if (display := _label(span, trace_id)) is not None}
    visible = sorted(
        (span for span in spans if span.id in labels),
        key=lambda span: (span.id != trace_id, span.start_time, len(span.parent_run_ids or []), span.id),
    )
    rows = []
    for span in visible[:TRACE_MAX_ROWS]:
        kind, label = labels[span.id]
        elapsed = (span.end_time - span.start_time).total_seconds() if span.end_time else None
        rows.append(
            TraceRow(
                label=label,
                kind=kind,
                elapsed_ms=to_ms(elapsed) if elapsed is not None and elapsed >= 0 else None,
                offset_ms=max(0, to_ms((span.start_time - root.start_time).total_seconds())),
                depth=sum(ancestor in labels for ancestor in span.parent_run_ids or ()),
                status=STATUSES.get(span.status or "", "Unknown"),
                error=f"{kind} reported an error." if span.status == "ERROR" else None,
            )
        )
    return TraceView("ready", tuple(rows), truncated=len(visible) > TRACE_MAX_ROWS)


async def _read_json(
    http: httpx2.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: Mapping[str, str | list[str]],
) -> object:
    """Bound the response before parsing, including when the server omits Content-Length."""
    async with http.stream("GET", url, headers=headers, params=params, follow_redirects=False) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=8192):
            if len(body) + len(chunk) > TRACE_MAX_BYTES:
                raise ValueError("Trace response too large")
            body.extend(chunk)
    return json.loads(body)


async def read_trace(
    settings: Settings, trace_id: UUID, *, transport: httpx2.AsyncBaseTransport | None = None
) -> TraceView:
    """Query only the configured tracing project, within one deadline and without retrying a failed upstream."""
    if not is_tracing_allowed(settings) or settings.langsmith_api_key is None:
        return TraceView("disabled")
    key = smith.get_api_key(settings.langsmith_api_key.get_secret_value())
    if not key:
        return TraceView("disabled")
    headers = {"X-Api-Key": key, "Accept": "application/json"}
    if workspace := smith.get_workspace_id(None):
        headers["X-Tenant-Id"] = workspace
    project = settings.langsmith_project or smith.get_tracer_project() or "default"
    try:
        # The writer's endpoint may include the v1 suffix (e.g. a regional LangSmith installation).
        base = smith.get_api_url(None).removesuffix("/api/v1").removesuffix("/api")
        async with asyncio.timeout(TRACE_SECONDS), httpx2.AsyncClient(transport=transport) as http:
            result = await _read_json(http, f"{base}/api/v1/sessions", headers, {"name": project, "limit": "1"})
            projects = TypeAdapter(list[_Project]).validate_python(result)
            if len(projects) != 1 or projects[0].name != project:
                return TraceView("unavailable")
            project_id = projects[0].id
            now = datetime.now(UTC)
            result = await _read_json(
                http,
                f"{base}/api/v2/traces/{trace_id}/runs",
                headers,
                {
                    "project_id": str(project_id),
                    "min_start_time": to_iso(now - timedelta(days=OBSERVABILITY_DAYS)),
                    "max_start_time": to_iso(now),
                    "selects": list(SELECTS),
                },
            )
        return _to_view(_Runs.model_validate(result).items, trace_id, project_id)
    except httpx2.HTTPStatusError as exc:
        if exc.response.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            return TraceView("denied")
        if exc.response.status_code == HTTPStatus.NOT_FOUND and exc.request.url.path.endswith("/runs"):
            return TraceView("pending")
        return TraceView("unavailable")
    except (httpx2.HTTPError, TimeoutError, ValueError, RecursionError, smith.LangSmithUserError):
        return TraceView("unavailable")
