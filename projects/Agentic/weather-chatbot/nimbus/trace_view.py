"""Read a single Nimbus trace from LangSmith and reduce it to fields safe for the public Activity page."""

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from http import HTTPStatus
from typing import Final, Literal
from uuid import UUID

import httpx2
import structlog
from langsmith import utils as smith
from pydantic import AwareDatetime, BaseModel, TypeAdapter, field_validator

from nimbus.config import Settings
from nimbus.constants import AGENT_NAME, OBSERVABILITY_DAYS
from nimbus.memory.tracing import MEMORY_TRACE_NAMES
from nimbus.model import is_tracing_allowed
from nimbus.request_trace import CACHE_STEP_NAMES, REQUEST_TRACE_NAME
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
MEMORY_LABELS = {
    MEMORY_TRACE_NAMES[action]: f"Mem0 {label}"
    for action, label in (("read", "read"), ("save", "save"), ("forget", "delete"))
}
CACHE_LABELS = {
    CACHE_STEP_NAMES["lookup"]: "Weather answer cache lookup",
    CACHE_STEP_NAMES["store"]: "Weather answer cache store",
}
# Ask only for identifiers, nesting, names, status and timestamps. Even error text can contain the question.
SELECTS = ("ID", "PROJECT_ID", "TRACE_ID", "PARENT_RUN_IDS", "NAME", "RUN_TYPE", "START_TIME", "END_TIME", "STATUS")

type _Stage = Literal["project", "runs"]


class TraceIssue(StrEnum):
    """
    Fixed public messages, written for any visitor: never a setting's name, a key or the server's log, since the
    page is public. Each message is distinct, so its enum name stays a stable diagnostic code: the server log's
    langsmith.read_failed line records it, with the lookup stage and the HTTP status, for whoever runs Nimbus.
    """

    ACCESS_DENIED = "This trace can't be shown: Nimbus isn't allowed to read it."
    PROJECT_NOT_FOUND = "This trace can't be shown: its tracing project wasn't found."
    WORKSPACE_REQUIRED = "This trace can't be shown: reading traces isn't set up on this deployment."
    WORKSPACE_MISMATCH = "This trace can't be shown: its tracing project doesn't match this deployment."
    WRONG_SCOPE = "LangSmith returned data outside the requested trace or project. Nimbus withheld those calls."
    WRONG_ROOT = "This trace doesn't belong to a Nimbus chat or memory operation, so it isn't shown."
    RATE_LIMITED = "LangSmith reached its read limit. Wait a minute before refreshing the trace."
    SERVICE_ERROR = "LangSmith reported a service error. Try refreshing the trace later."
    REQUEST_REJECTED = "LangSmith rejected the lookup. Try refreshing the trace later."
    INVALID_RESPONSE = "Nimbus couldn't read what LangSmith returned. Try refreshing the trace later."
    TOO_LARGE = "The LangSmith response exceeds the size limit for this view. The Activity timeline is still available."
    TIMED_OUT = "The LangSmith lookup timed out. Try refreshing the trace."
    UNREACHABLE = "Nimbus could not reach LangSmith. Try refreshing the trace later."
    INVALID_ENDPOINT = "This trace can't be shown: reading traces is misconfigured on this deployment."


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
    parent_index: int | None = None


@dataclass(frozen=True)
class TraceView:
    """The result of one on-demand lookup; only these projected rows can reach the template."""

    status: Literal["ready", "pending", "unavailable", "disabled", "denied"]
    rows: tuple[TraceRow, ...] = ()
    truncated: bool = False
    issue: TraceIssue | None = None


def _failed(stage: _Stage, issue: TraceIssue, http_status: int | None = None) -> TraceView:
    """Report the failed operation using only fixed vocabulary and the numeric upstream status."""
    fields = {"httpStatus": http_status} if http_status is not None else {}
    structlog.get_logger().warning("langsmith.read_failed", stage=stage, reason=issue.name.lower(), **fields)
    return TraceView("denied" if issue == TraceIssue.ACCESS_DENIED else "unavailable", issue=issue)


class _ResponseTooLargeError(ValueError):
    """The decoded response exceeded the hard limit before JSON parsing."""


class _Project(BaseModel):
    id: UUID
    name: str
    tenant_id: UUID | None = None


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

    @field_validator("run_type", "status")
    @classmethod
    def normalize_enum(cls, value: str | None) -> str | None:
        """Accept wire enum casing without relaxing root identity or exposing unknown provider values."""
        return value.upper() if value is not None else None


class _Runs(BaseModel):
    items: list[_Span]


def _label(span: _Span, root_id: UUID) -> tuple[str, str] | None:
    """
    Include the chat request, the graph, Mem0, the weather answer cache, model and tool calls, plus any other step
    that explains a failure. Mem0 and the graph are named wherever they sit: a root, or a step of a chat request.
    """
    if span.name in MEMORY_LABELS and span.run_type == "TOOL":
        return "Memory", MEMORY_LABELS[span.name]
    if span.id == root_id:
        return "Agent", "Chat request" if span.name == REQUEST_TRACE_NAME else "Nimbus agent"
    if span.name == AGENT_NAME and span.run_type == "CHAIN":
        return "Agent", "Nimbus agent"
    if span.name in CACHE_LABELS and span.run_type == "CHAIN":
        return "Step", CACHE_LABELS[span.name]
    if span.run_type == "LLM":
        return "Model", "Gemini" if span.name == "ChatGoogleGenerativeAI" else "Model call"
    if span.run_type == "TOOL":
        return "Tool", span.name if span.name in TRACE_TOOL_NAMES else "Tool call"
    if span.status == "ERROR":
        return "Step", STEP_LABELS.get(span.name, "Graph step")
    return None


def _to_view(spans: list[_Span], trace_id: UUID, project_id: UUID) -> TraceView:
    if any(span.trace_id != trace_id or span.project_id != project_id for span in spans):
        return _failed("runs", TraceIssue.WRONG_SCOPE)
    if len({span.id for span in spans}) != len(spans):
        return _failed("runs", TraceIssue.INVALID_RESPONSE)
    root = next((span for span in spans if span.id == trace_id), None)
    if root is None:
        return TraceView("pending")
    # A chat request's root since it began nesting its steps; the graph's own root and a Mem0 root, as before.
    is_request = root.name == REQUEST_TRACE_NAME and root.run_type == "CHAIN"
    is_agent = root.name == AGENT_NAME and root.run_type == "CHAIN"
    is_memory = root.name in MEMORY_LABELS and root.run_type == "TOOL"
    if not (is_request or is_agent or is_memory):
        return _failed("runs", TraceIssue.WRONG_ROOT)
    labels = {span.id: display for span in spans if (display := _label(span, trace_id)) is not None}
    visible = sorted(
        (span for span in spans if span.id in labels),
        key=lambda span: (span.id != trace_id, span.start_time, len(span.parent_run_ids or []), span.id),
    )
    retained = visible[:TRACE_MAX_ROWS]
    parents = _visible_parents(retained, spans, trace_id)
    rows = []
    for index, span in enumerate(retained):
        kind, label = labels[span.id]
        elapsed = (span.end_time - span.start_time).total_seconds() if span.end_time else None
        rows.append(
            TraceRow(
                label=label,
                kind=kind,
                elapsed_ms=to_ms(elapsed) if elapsed is not None and elapsed >= 0 else None,
                offset_ms=max(0, to_ms((span.start_time - root.start_time).total_seconds())),
                depth=len(_ancestors(index, parents)),
                status=STATUSES.get(span.status or "", "Unknown"),
                error=f"{kind} reported an error." if span.status == "ERROR" else None,
                parent_index=parents[index],
            )
        )
    return TraceView("ready", tuple(rows), truncated=len(visible) > TRACE_MAX_ROWS)


def _visible_parents(spans: list[_Span], all_spans: list[_Span], root_id: UUID) -> list[int | None]:
    """Keep nearest displayed ancestors; malformed cycles and absent parents never become invented nesting."""
    positions = {span.id: index for index, span in enumerate(spans)}
    by_id = {span.id: span for span in all_spans}

    def ancestors(identifier: UUID) -> set[UUID]:
        """Cross omitted graph wrappers using declared links, without requiring a full or ordered ancestor array."""
        pending = list(by_id[identifier].parent_run_ids or ())
        seen: set[UUID] = set()
        while pending:
            ancestor = pending.pop()
            if ancestor in seen or ancestor not in by_id:
                continue
            seen.add(ancestor)
            pending.extend(by_id[ancestor].parent_run_ids or ())
        return seen - {identifier}

    ancestry = {span.id: ancestors(span.id) for span in spans}
    parents: list[int | None] = []
    for span in spans:
        candidates = [positions[ancestor] for ancestor in ancestry[span.id] if ancestor in positions]
        # Compare known ancestor depth rather than trusting the upstream array's order.
        depths = {index: len(ancestry[spans[index].id] & positions.keys()) for index in candidates}
        deepest = [index for index, depth in depths.items() if depth == max(depths.values(), default=-1)]
        parent = deepest[0] if len(deepest) == 1 else None
        parents.append(None if span.id == root_id else parent)
    return safe_parent_indices(parents)


def safe_parent_indices(values: Sequence[int | None]) -> list[int | None]:
    """Validate page-local relationships once for projection and presentation; cycles become unlinked spans."""
    parents = [
        parent if type(parent) is int and 0 <= parent < len(values) and parent != index else None
        for index, parent in enumerate(values)
    ]
    for index in range(len(values)):
        path: list[int] = []
        current: int | None = index
        while current is not None and current not in path:
            path.append(current)
            current = parents[current]
        if current is not None:
            for member in path[path.index(current) :]:
                parents[member] = None
    return parents


def _ancestors(index: int, parents: list[int | None]) -> tuple[int, ...]:
    """Walk a validated finite parent chain without exposing upstream identifiers."""
    result = []
    current = parents[index]
    while current is not None:
        result.append(current)
        current = parents[current]
    return tuple(reversed(result))


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
                raise _ResponseTooLargeError
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
    workspace = settings.langsmith_workspace_id
    if workspace is None and (sdk_workspace := smith.get_workspace_id(None)):
        try:
            workspace = UUID(sdk_workspace)
        except ValueError:
            return _failed("project", TraceIssue.WORKSPACE_REQUIRED)
    if workspace is not None:
        headers["X-Tenant-Id"] = str(workspace)
    project = settings.langsmith_project or smith.get_tracer_project() or "default"
    stage: _Stage = "project"
    try:
        # The writer's endpoint may include the v1 suffix (e.g. a regional LangSmith installation).
        base = smith.get_api_url(None).removesuffix("/api/v1").removesuffix("/api")
        async with asyncio.timeout(TRACE_SECONDS), httpx2.AsyncClient(transport=transport) as http:
            result = await _read_json(http, f"{base}/api/v1/sessions", headers, {"name": project, "limit": "1"})
            projects = TypeAdapter(list[_Project]).validate_python(result)
            if not projects:
                return _failed(stage, TraceIssue.PROJECT_NOT_FOUND)
            if len(projects) != 1 or projects[0].name != project:
                return _failed(stage, TraceIssue.WRONG_SCOPE)
            project_id = projects[0].id
            # The project lookup accepts a key alone. The v2 trace read requires the key AND the workspace.
            tenant = projects[0].tenant_id
            if tenant is not None and workspace is not None and tenant != workspace:
                return _failed(stage, TraceIssue.WORKSPACE_MISMATCH)
            tenant = tenant or workspace
            if tenant is None:
                return _failed(stage, TraceIssue.WORKSPACE_REQUIRED)
            headers["X-Tenant-Id"] = str(tenant)
            stage = "runs"
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
        status = exc.response.status_code
        if status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
            return _failed(stage, TraceIssue.ACCESS_DENIED, status)
        if status == HTTPStatus.NOT_FOUND and stage == "runs":
            return TraceView("pending")
        if status == HTTPStatus.TOO_MANY_REQUESTS:
            return _failed(stage, TraceIssue.RATE_LIMITED, status)
        if 500 <= status < 600:
            return _failed(stage, TraceIssue.SERVICE_ERROR, status)
        return _failed(stage, TraceIssue.REQUEST_REJECTED, status)
    except (TimeoutError, httpx2.TimeoutException):
        return _failed(stage, TraceIssue.TIMED_OUT)
    except _ResponseTooLargeError:
        return _failed(stage, TraceIssue.TOO_LARGE)
    except (httpx2.InvalidURL, smith.LangSmithUserError):
        return _failed(stage, TraceIssue.INVALID_ENDPOINT)
    except httpx2.HTTPError:
        return _failed(stage, TraceIssue.UNREACHABLE)
    except (ValueError, RecursionError):
        return _failed(stage, TraceIssue.INVALID_RESPONSE)
