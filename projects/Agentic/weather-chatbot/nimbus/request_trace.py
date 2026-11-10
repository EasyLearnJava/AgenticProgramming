"""
nimbus/request_trace.py: one LangSmith root for each chat request, so the Mem0 read, the weather answer cache and the
agent's own runs sit in one trace, in the order they ran. Like every run of ours it holds no inputs or outputs: only
fixed names, the request's workflow and whether it failed. Without a tracer, nothing is traced and no line carries a
trace ID.
"""

from collections.abc import AsyncGenerator, Iterator
from contextlib import aclosing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal
from uuid import UUID, uuid4

import structlog
from langsmith.run_trees import RunTree

from nimbus.model import Tracer

REQUEST_TRACE_NAME: Final = "nimbus.chat"
CACHE_STEP_NAMES: Final = {"lookup": "weather_cache.lookup", "store": "weather_cache.store"}
type Workflow = Literal["agent", "cached", "intake", "briefing", "memory"]


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
    def step(self, action: Literal["lookup", "store"]) -> Iterator[None]:
        """One call to the weather answer cache, as a child run: its name, its time, and whether it raised."""
        child = self._start_child(CACHE_STEP_NAMES[action])
        failed = True
        try:
            yield
            failed = False
        finally:
            if child is not None:
                self._end_child(*child, failed=failed)

    def _start_child(self, name: str) -> tuple[UUID, str] | None:
        """Queue a child of the root; None when there's no root, or the child couldn't be written."""
        if self.tracer is None or self.parent is None:
            return None
        run_id, order, start = self.parent.child()
        try:
            self.tracer.client.create_run(
                id=run_id,
                trace_id=self.parent.trace_id,
                dotted_order=order,
                parent_run_id=self.parent.run_id,
                name=name,
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
            return None
        return run_id, order

    def _end_child(self, run_id: UUID, order: str, *, failed: bool) -> None:
        """Finish a child with no outputs; a raised call is an error, without its text."""
        if self.tracer is None or self.parent is None:
            return
        try:
            self.tracer.client.update_run(
                run_id,
                trace_id=self.parent.trace_id,
                dotted_order=order,
                parent_run_id=self.parent.run_id,
                end_time=datetime.now(UTC),
                inputs={},
                outputs={},
                error="Weather answer cache step failed" if failed else None,
            )
        except Exception:
            structlog.get_logger().warning("trace.request_write_failed", stage="step_finish")

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
                extra={"metadata": {"workflow": self.workflow}},
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
