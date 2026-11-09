"""Independent Mem0 operation traces with empty payloads and a fixed, nonpersonal outcome vocabulary."""

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

type MemoryAction = Literal["read", "save", "forget"]

MEMORY_TRACE_NAMES: Final = {"read": "mem0.read", "save": "mem0.save", "forget": "mem0.delete"}
_STATUSES = frozenset(get_args(MemoryStatus.__value__))
_REASONS = frozenset(get_args(MemoryReason.__value__))


@dataclass
class MemoryTrace:
    """One request-local operation; it never receives a profile, credential, identity or provider exception."""

    tracer: Tracer | None = field(repr=False)
    action: MemoryAction
    started: float = field(default_factory=time.monotonic)
    status: MemoryStatus = "unavailable"
    reason: MemoryReason = "unavailable"
    trace_id: UUID | None = None
    dotted_order: str = ""

    def start(self) -> None:
        """Queue an explicit root, ignoring ambient LangSmith parents, tags, metadata and input capture."""
        if self.tracer is None:
            return
        root = uuid4()
        start_time = datetime.now(UTC)
        order = start_time.strftime("%Y%m%dT%H%M%S%fZ") + str(root)
        try:
            # Both identifiers are mandatory: without them the SDK may use synchronous HTTP instead of its queue.
            self.tracer.client.create_run(
                id=root,
                trace_id=root,
                dotted_order=order,
                parent_run_id=None,
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

    def outcome(self, status: MemoryStatus, reason: MemoryReason) -> None:
        """Accept only the small operational vocabulary, even if an internal caller supplies malformed metadata."""
        self.status = status if status in _STATUSES else "unavailable"
        self.reason = reason if reason in _REASONS else "unavailable"

    def close(self) -> None:
        """Finish with fixed metadata, flush after Vercel's response, and record the matching safe Activity event."""
        if self.tracer is not None and self.trace_id is not None:
            try:
                self.tracer.client.update_run(
                    self.trace_id,
                    trace_id=self.trace_id,
                    dotted_order=self.dotted_order,
                    parent_run_id=None,
                    end_time=datetime.now(UTC),
                    inputs={},
                    outputs={},
                    error=None if self.status in {"ready", "empty"} else "Memory operation not confirmed",
                    extra={"metadata": {"action": self.action, "status": self.status, "reason": self.reason}},
                )
            except Exception:
                structlog.get_logger().warning("trace.memory_write_failed", stage="finish")
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
def memory_trace(tracer: Tracer | None, action: MemoryAction) -> Iterator[MemoryTrace]:
    """Always close the safe operation, including cancellation, without catching or serializing its exception."""
    operation = MemoryTrace(tracer, action)
    operation.start()
    try:
        yield operation
    finally:
        operation.close()
