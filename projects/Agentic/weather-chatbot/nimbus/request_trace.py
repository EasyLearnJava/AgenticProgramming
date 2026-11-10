"""
nimbus/request_trace.py: one LangSmith root for each chat request, so the Mem0 read, the weather answer cache and the
agent's own runs sit in one trace, in the order they ran. Like every run of ours it holds no inputs or outputs: only
fixed names, workflow, allowlisted cache outcomes and bounded similarity measurements. Without a tracer, nothing is
traced and no line carries a trace ID.
"""

import asyncio
import math
from collections.abc import AsyncGenerator, Iterator
from contextlib import aclosing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal, get_args
from uuid import UUID, uuid4

import structlog
from langsmith.run_trees import RunTree

from nimbus.model import Tracer

REQUEST_TRACE_NAME: Final = "nimbus.chat"
CACHE_STEP_NAMES: Final = {"lookup": "weather_cache.lookup", "store": "weather_cache.store"}
CACHE_OPERATION_NAMES: Final = {
    "exact": "qdrant.exact_match",
    "similarity": "qdrant.similarity_search",
    "cleanup": "qdrant.remove_expired",
    "count": "qdrant.count",
    "save": "qdrant.save",
}
type Workflow = Literal["agent", "cached", "intake", "briefing", "memory"]
type QdrantAction = Literal["exact", "similarity", "cleanup", "count", "save"]
type CacheOutcome = Literal[
    "completed",
    "exact_hit",
    "semantic_hit",
    "miss",
    "shadow_hit",
    "error",
    "bypass",
    "saved",
    "not_reusable",
    "cache_full",
    "cancelled",
    # A write our deadline cut off: Qdrant may still have applied it, so it's neither saved nor an error.
    "timed_out",
]
type CacheBypassReason = Literal[
    "disabled",
    "unconfigured",
    "ineligible",
    "unverified_history",
    "incompatible_history",
    "workflow",
    "lane",
    "origin",
    "memory_unavailable",
    "not_evaluated",
]
# Which evidence check kept a finished answer out of the cache: a fixed word, never a place, a value or the question.
type CacheRejection = Literal[
    "answer",
    "tools",
    "forecast_missing",
    "place",
    "point",
    "time_zone",
    "units",
    "current",
    "forecast_day",
    "forecast_incomplete",
    "freshness",
    "malformed",
]
_CACHE_OUTCOMES: Final = frozenset(get_args(CacheOutcome.__value__))
_BYPASS_REASONS: Final = frozenset(get_args(CacheBypassReason.__value__))
CACHE_REJECTIONS: Final = frozenset(get_args(CacheRejection.__value__))


def _number(value: object, lower: float, upper: float) -> float | None:
    """A finite, bounded numeric measurement; never coerce strings, booleans or private object representations."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and lower <= number <= upper else None


def to_dotted_order(start: datetime, run_id: UUID) -> str:
    """LangSmith's sort key for one run: its UTC start, to the microsecond, then its ID."""
    return start.strftime("%Y%m%dT%H%M%S%fZ") + str(run_id)


@dataclass(frozen=True)
class TraceParent:
    """Where a child run hangs: the trace it belongs to, its parent run, and that parent's dotted order."""

    trace_id: UUID
    run_id: UUID
    dotted_order: str

    def child(self) -> tuple[UUID, str, datetime]:
        """A new child's ID, its dotted order under this parent, which LangSmith checks, and its start time."""
        run_id, start = uuid4(), datetime.now(UTC)
        return run_id, f"{self.dotted_order}.{to_dotted_order(start, run_id)}", start


@dataclass
class CacheTraceStep:
    """One bounded cache span, carrying only a fixed outcome and approved numeric similarity measurements."""

    tracer: Tracer | None = field(repr=False)
    name: str
    _upstream: TraceParent | None = field(repr=False)
    parent: TraceParent | None = None
    _status: str = "completed"
    _rejection: str = ""
    _measurements: dict[str, float] = field(default_factory=dict, repr=False)
    _closed: bool = False

    def start(self) -> None:
        """Queue this child only when its immediate parent exists; a failed trace write creates no orphan."""
        if self.tracer is None or self._upstream is None:
            return
        if self.name not in {*CACHE_STEP_NAMES.values(), *CACHE_OPERATION_NAMES.values()}:
            return
        run_id, order, start = self._upstream.child()
        try:
            self.tracer.client.create_run(
                id=run_id,
                trace_id=self._upstream.trace_id,
                dotted_order=order,
                parent_run_id=self._upstream.run_id,
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
            structlog.get_logger().warning("trace.request_write_failed", stage="step_start")
        else:
            self.parent = TraceParent(self._upstream.trace_id, run_id, order)

    def outcome(self, status: CacheOutcome, rejection: CacheRejection | None = None) -> None:
        """
        Record a fixed operational status even when the service returns an error instead of raising it, and, for an
        answer kept out of the cache, the check that kept it out.
        """
        self._status = status if isinstance(status, str) and status in _CACHE_OUTCOMES else "error"
        self._rejection = ""
        if self._status == "not_reusable" and isinstance(rejection, str) and rejection in CACHE_REJECTIONS:
            self._rejection = rejection

    def similarity(self, score: object, threshold: object) -> None:
        """Capture only bounded cosine score and threshold on the similarity operation, never its query or vector."""
        if self.name != CACHE_OPERATION_NAMES["similarity"]:
            return
        self._measurements = {}
        for key, number in (
            ("similarity_score", _number(score, -1, 1)),
            ("similarity_threshold", _number(threshold, 0, 1)),
        ):
            if number is not None:
                self._measurements[key] = number

    @contextmanager
    def step(self, action: QdrantAction) -> Iterator["CacheTraceStep"]:
        """Time one Qdrant operation under this span, retaining the chat request's trace ID."""
        with _cache_step(self.tracer, self.parent, CACHE_OPERATION_NAMES[action]) as child:
            yield child

    def close(self) -> None:
        """Finish once with safe metadata; failures in tracing never change the cache or chat outcome."""
        if self._closed:
            return
        self._closed = True
        if self.tracer is None or self.parent is None or self._upstream is None:
            return
        metadata: dict[str, str | float] = {"outcome": self._status, **self._measurements}
        if self._rejection:
            metadata["rejection"] = self._rejection
        try:
            self.tracer.client.update_run(
                self.parent.run_id,
                trace_id=self.parent.trace_id,
                dotted_order=self.parent.dotted_order,
                parent_run_id=self._upstream.run_id,
                end_time=datetime.now(UTC),
                inputs={},
                outputs={},
                error="Weather answer cache step failed" if self._status == "error" else None,
                extra={"metadata": metadata},
            )
        except Exception:
            structlog.get_logger().warning("trace.request_write_failed", stage="step_finish")


@contextmanager
def _cache_step(tracer: Tracer | None, parent: TraceParent | None, name: str) -> Iterator[CacheTraceStep]:
    """Close cache spans on every exit; preserve explicit timeout errors while marking real cancellation distinctly."""
    step = CacheTraceStep(tracer, name, parent)
    step.start()
    try:
        yield step
    except (asyncio.CancelledError, GeneratorExit):
        if step._status != "error":
            step.outcome("cancelled")
        raise
    except BaseException:
        step.outcome("error")
        raise
    finally:
        step.close()


@dataclass
class RequestTrace:
    """
    A chat request's root run: begun before its first step, ended once, however its response ends. A failure to write
    it is a warning line, never the request's failure: the answer goes on untraced.
    """

    tracer: Tracer | None = field(repr=False)
    workflow: Workflow = "agent"
    failed: bool = False
    parent: TraceParent | None = None
    started: datetime | None = None
    ended: bool = False
    _cache_status: str = ""
    _cache_reason: str = ""

    @classmethod
    def begin(cls, tracer: Tracer | None) -> "RequestTrace":
        """The request's root, with a tracer: queued with both IDs, without which the SDK may send it at once."""
        trace = cls(tracer)
        if tracer is None:
            return trace
        root, start = uuid4(), datetime.now(UTC)
        order = to_dotted_order(start, root)
        try:
            tracer.client.create_run(
                id=root,
                trace_id=root,
                dotted_order=order,
                parent_run_id=None,
                name=REQUEST_TRACE_NAME,
                run_type="chain",
                project_name=tracer.project,
                start_time=start,
                inputs={},
                outputs={},
                tags=[],
                extra={"metadata": {}},
            )
        except Exception:
            structlog.get_logger().warning("trace.request_write_failed", stage="start")
        else:
            trace.parent, trace.started = TraceParent(root, root, order), start
        return trace

    @property
    def trace_id(self) -> UUID | None:
        """The root's ID, which is its trace's, once it's queued."""
        return self.parent.trace_id if self.parent is not None else None

    def fields(self) -> dict[str, str]:
        """What an ending line holds to find the trace: its ID, when there is one."""
        return {"traceId": str(self.parent.trace_id)} if self.parent is not None else {}

    def run_tree(self) -> RunTree | None:
        """The root as LangChain finds a parent, so the agent's runs nest under it; it's never sent from here."""
        if self.tracer is None or self.parent is None or self.started is None:
            return None
        project = {"project_name": self.tracer.project} if self.tracer.project else {}
        return RunTree(
            id=self.parent.run_id,
            trace_id=self.parent.trace_id,
            dotted_order=self.parent.dotted_order,
            name=REQUEST_TRACE_NAME,
            run_type="chain",
            start_time=self.started,
            inputs={},
            ls_client=self.tracer.client,
            **project,
        )

    @contextmanager
    def step(self, action: Literal["lookup", "store"]) -> Iterator[CacheTraceStep]:
        """Time cache lookup or storage while accepting its explicit outcome and nested provider operations."""
        with _cache_step(self.tracer, self.parent, CACHE_STEP_NAMES[action]) as child:
            yield child

    def cache_outcome(self, status: CacheOutcome, reason: CacheBypassReason | Literal[""] = "") -> None:
        """Record fixed cache routing facts on the root, including requests that create no cache child span."""
        self._cache_status = status if isinstance(status, str) and status in _CACHE_OUTCOMES else "error"
        self._cache_reason = reason if isinstance(reason, str) and reason in _BYPASS_REASONS else ""

    def end(self) -> None:
        """Finish the root once, with its workflow and whether it failed; then send it, after Vercel's response."""
        if self.ended:
            return
        self.ended = True
        if self.tracer is None or self.parent is None:
            return
        try:
            self.tracer.client.update_run(
                self.parent.run_id,
                trace_id=self.parent.trace_id,
                dotted_order=self.parent.dotted_order,
                parent_run_id=None,
                end_time=datetime.now(UTC),
                inputs={},
                outputs={},
                error="Chat request failed" if self.failed else None,
                extra={
                    "metadata": {
                        "workflow": self.workflow,
                        **({"cache_outcome": self._cache_status} if self._cache_status else {}),
                        **({"cache_bypass_reason": self._cache_reason} if self._cache_reason else {}),
                    }
                },
            )
        except Exception:
            structlog.get_logger().warning("trace.request_write_failed", stage="finish")
        try:
            self.tracer.defer_flush()
        except Exception:
            structlog.get_logger().warning("trace.request_write_failed", stage="flush")

    async def wrap(self, events: AsyncGenerator[str]) -> AsyncGenerator[str]:
        """A response's events as they are; the root ends when they do, whether they finish, fail or are closed."""
        try:
            async with aclosing(events) as items:
                async for item in items:
                    yield item
        except Exception:
            # A browser that went (cancellation, or the stream closed) isn't a failure; an error that escapes is.
            self.failed = True
            raise
        finally:
            self.end()
