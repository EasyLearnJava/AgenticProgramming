"""
Mem0 operation traces with empty payloads and a fixed, nonpersonal outcome vocabulary: a chat's read is a step in the
chat request's trace (nimbus/request_trace.py); an operation from My preferences is a trace of its own.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal, get_args
from uuid import UUID, uuid4

import structlog

from nimbus.memory.models import MemoryReason, MemoryStatus
from nimbus.model import Tracer
from nimbus.request_trace import TraceParent, to_dotted_order

type MemoryAction = Literal["read", "save", "forget"]

MEMORY_TRACE_NAMES: Final = {"read": "mem0.read", "save": "mem0.save", "forget": "mem0.delete"}
_STATUSES = frozenset(get_args(MemoryStatus.__value__))
_REASONS = frozenset(get_args(MemoryReason.__value__))


@dataclass
class MemoryTrace:
    """One request-local operation; it never receives a profile, credential, identity or provider exception."""

    tracer: Tracer | None = field(repr=False)
    action: MemoryAction
    parent: TraceParent | None = None
    started: float = field(default_factory=time.monotonic)
    status: MemoryStatus = "unavailable"
    reason: MemoryReason = "unavailable"
    trace_id: UUID | None = None
    run_id: UUID | None = None
    dotted_order: str = ""

    def start(self) -> None:
        """
        Queue an explicit run: a root of its own, or a child of the given chat request's root. Ambient LangSmith
        parents, tags, metadata and input capture are ignored either way.
        """
        if self.tracer is None:
            return
        if self.parent is None:
            root = run = uuid4()
            start_time = datetime.now(UTC)
            order = to_dotted_order(start_time, run)
        else:
            run, order, start_time = self.parent.child()
            root = self.parent.trace_id
        try:
            # Both identifiers are mandatory: without them the SDK may use synchronous HTTP instead of its queue.
            self.tracer.client.create_run(
                id=run,
                trace_id=root,
                dotted_order=order,
                parent_run_id=self.parent.run_id if self.parent is not None else None,
                name=MEMORY_TRACE_NAMES[self.action],
                run_type="tool",
                project_name=self.tracer.project,
                start_time=start_time,
                inputs={},
                outputs={},
                tags=[],
                extra={"metadata": {"action": self.action}},
            )
        except Exception:
            structlog.get_logger().warning("trace.memory_write_failed", stage="start")
        else:
            self.trace_id, self.dotted_order = root, order
            self.run_id = run

    def outcome(self, status: MemoryStatus, reason: MemoryReason) -> None:
        """Accept only the small operational vocabulary, even if an internal caller supplies malformed metadata."""
        self.status = status if status in _STATUSES else "unavailable"
        self.reason = reason if reason in _REASONS else "unavailable"

    def close(self) -> None:
        """
        Finish with fixed metadata and record the matching safe Activity event. A root of its own is sent after
        Vercel's response from here; a step's is sent with its chat request's root.
        """
        if self.tracer is not None and self.trace_id is not None and self.run_id is not None:
            try:
                self.tracer.client.update_run(
                    self.run_id,
                    trace_id=self.trace_id,
                    dotted_order=self.dotted_order,
                    parent_run_id=self.parent.run_id if self.parent is not None else None,
                    end_time=datetime.now(UTC),
                    inputs={},
                    outputs={},
                    error=None if self.status in {"ready", "empty"} else "Memory operation not confirmed",
                    extra={"metadata": {"action": self.action, "status": self.status, "reason": self.reason}},
                )
            except Exception:
                structlog.get_logger().warning("trace.memory_write_failed", stage="finish")
            if self.parent is None:
                try:
                    self.tracer.defer_flush()
                except Exception:
                    structlog.get_logger().warning("trace.memory_write_failed", stage="flush")
        structlog.get_logger().info(
            "memory.operation",
            tool="memory_preferences",
            action=self.action,
            status=self.status,
            reason=self.reason,
            ms=round((time.monotonic() - self.started) * 1000),
            **({"traceId": str(self.trace_id)} if self.trace_id is not None else {}),
        )


@contextmanager
def memory_trace(
    tracer: Tracer | None, action: MemoryAction, parent: TraceParent | None = None
) -> Iterator[MemoryTrace]:
    """Always close the safe operation, including cancellation, without catching or serializing its exception."""
    operation = MemoryTrace(tracer, action, parent)
    operation.start()
    try:
        yield operation
    finally:
        operation.close()
