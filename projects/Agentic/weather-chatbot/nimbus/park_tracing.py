"""Private operational traces for park retrieval: BM25, semantic lookup and rank fusion, never query or passage text."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal, get_args
from uuid import UUID, uuid4

import structlog
from langsmith import get_current_run_tree
from langsmith import utils as smith

from nimbus.model import Tracer
from nimbus.request_trace import TraceParent, to_dotted_order

PARK_RETRIEVAL_NAME: Final = "parks.retrieval"
PARK_TRACE_NAMES: Final = {
    "bm25": "parks.bm25",
    "semantic": "parks.semantic",
    "fusion": "parks.fusion",
}
type ParkTraceAction = Literal["bm25", "semantic", "fusion"]
type RetrievalStatus = Literal[
    "completed",
    "ready",
    "found",
    "not_found",
    "not_needed",
    "disabled",
    "unconfigured",
    "index_not_ready",
    "index_mismatch",
    "timeout",
    "busy",
    "error",
    "cancelled",
    "missing_dependencies",
    "missing_weights",
    "incompatible_model",
    "failed",
    "invalid_response",
    "unavailable",
    "unsupported",
]
type RetrievalProvider = Literal["none", "local", "qdrant"]
type RetrievalMode = Literal["none", "lexical", "hybrid"]
type SeasonSource = Literal["none", "date", "explicit", "query"]

RETRIEVAL_STATUSES: Final = frozenset(get_args(RetrievalStatus.__value__))
RETRIEVAL_PROVIDERS: Final = frozenset(get_args(RetrievalProvider.__value__))
RETRIEVAL_MODES: Final = frozenset(get_args(RetrievalMode.__value__))
SEASON_SOURCES: Final = frozenset(get_args(SeasonSource.__value__))
_FAILED: Final = frozenset(
    {
        "index_not_ready",
        "index_mismatch",
        "timeout",
        "error",
        "incompatible_model",
        "failed",
        "invalid_response",
        "unavailable",
        "missing_dependencies",
        "missing_weights",
    }
)


def _parent(tracer: Tracer | None) -> TraceParent | None:
    """Use only IDs from this client's current tool run; unrelated tracing context cannot acquire our child spans."""
    if tracer is None:
        return None
    current = get_current_run_tree()
    project = tracer.project or smith.get_tracer_project() or "default"
    if current is None or current.ls_client is not tracer.client or current.session_name != project:
        return None
    if current.trace_id is None or not current.dotted_order:
        return None
    return TraceParent(current.trace_id, current.id, current.dotted_order)


@dataclass
class ParkTrace:
    """One explicitly serialized span whose metadata is restricted to operational enums and bounded counts."""

    tracer: Tracer | None = field(repr=False)
    name: str
    upstream: TraceParent | None = None
    parent: TraceParent | None = None
    _metadata: dict[str, str | int] = field(default_factory=lambda: {"retrieval_outcome": "completed"})
    _closed: bool = False
    _root: bool = False

    @property
    def trace_id(self) -> UUID | None:
        """The chat trace ID for nested work, or this retrieval's own root for the Playground."""
        return self.parent.trace_id if self.parent else None

    def start(self) -> None:
        """Create a known-name root or child without inheriting ambient tags, inputs, outputs or metadata."""
        if self.tracer is None or self.name not in {PARK_RETRIEVAL_NAME, *PARK_TRACE_NAMES.values()}:
            return
        if self.upstream is None:
            if self.name != PARK_RETRIEVAL_NAME:
                return
            root = run = uuid4()
            start = datetime.now(UTC)
            order = to_dotted_order(start, run)
            self._root = True
        else:
            run, order, start = self.upstream.child()
            root = self.upstream.trace_id
        try:
            self.tracer.client.create_run(
                id=run,
                trace_id=root,
                dotted_order=order,
                parent_run_id=self.upstream.run_id if self.upstream else None,
                name=self.name,
                run_type="chain",
                project_name=self.tracer.project,
                start_time=start,
                inputs={},
                outputs={},
                tags=[],
                extra={"metadata": {}},
            )
        except Exception:
            structlog.get_logger().warning("trace.park_write_failed", stage="start")
        else:
            self.parent = TraceParent(root, run, order)

    def outcome(
        self,
        status: str,
        *,
        provider: str = "none",
        mode: str = "none",
        candidate_count: int | None = None,
        selected_count: int | None = None,
        season_source: str = "none",
    ) -> None:
        """Record approved values even when a dependency returns failures instead of raising exceptions."""
        self._metadata = {
            "retrieval_outcome": status if isinstance(status, str) and status in RETRIEVAL_STATUSES else "error",
            "retrieval_provider": provider if isinstance(provider, str) and provider in RETRIEVAL_PROVIDERS else "none",
            "retrieval_mode": mode if isinstance(mode, str) and mode in RETRIEVAL_MODES else "none",
            "retrieval_season_source": season_source
            if isinstance(season_source, str) and season_source in SEASON_SOURCES
            else "none",
        }
        for key, value in (("retrieval_candidates", candidate_count), ("retrieval_selected", selected_count)):
            if type(value) is int and 0 <= value <= 1000:
                self._metadata[key] = value

    @contextmanager
    def step(self, action: ParkTraceAction) -> Iterator["ParkTrace"]:
        """Keep each retrieval stage under the same operation, and never create orphans after a trace-write failure."""
        with _operation(self.tracer if self.parent else None, PARK_TRACE_NAMES[action], self.parent) as child:
            yield child

    def close(self) -> None:
        """End once, fail only failed operations, and flush only a standalone retrieval root."""
        if self._closed:
            return
        self._closed = True
        if self.tracer is None or self.parent is None:
            return
        try:
            self.tracer.client.update_run(
                self.parent.run_id,
                trace_id=self.parent.trace_id,
                dotted_order=self.parent.dotted_order,
                parent_run_id=self.upstream.run_id if self.upstream else None,
                end_time=datetime.now(UTC),
                inputs={},
                outputs={},
                error="Park retrieval step failed" if self._metadata["retrieval_outcome"] in _FAILED else None,
                extra={"metadata": self._metadata},
            )
        except Exception:
            structlog.get_logger().warning("trace.park_write_failed", stage="finish")
        if self._root:
            try:
                self.tracer.defer_flush()
            except Exception:
                structlog.get_logger().warning("trace.park_write_failed", stage="flush")


@contextmanager
def _operation(tracer: Tracer | None, name: str, parent: TraceParent | None) -> Iterator[ParkTrace]:
    """Always close runs, preserving cancellation and replacing all raised error text with a fixed outcome."""
    operation = ParkTrace(tracer, name, parent)
    operation.start()
    try:
        yield operation
    except (asyncio.CancelledError, GeneratorExit):
        operation.outcome("cancelled")
        raise
    except BaseException:
        operation.outcome("error")
        raise
    finally:
        operation.close()


@contextmanager
def park_retrieval_trace(tracer: Tracer | None, parent: TraceParent | None = None) -> Iterator[ParkTrace]:
    """Trace a retrieval under the configured client's current tool, or independently outside a traced chat."""
    with _operation(tracer, PARK_RETRIEVAL_NAME, parent or _parent(tracer)) as operation:
        yield operation
