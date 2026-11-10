"""Private scope-check traces and Activity events containing only fixed decisions and elapsed time."""

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal

import structlog

from nimbus.request_trace import RequestTrace, TraceParent
from nimbus.scope_guard import SCOPE_REASONS, SCOPE_STATUSES, ScopeDecision
from nimbus.utils import to_ms

SCOPE_TRACE_NAMES: Final = {"input": "scope.input", "output": "scope.output"}
SCOPE_TRACE_STATUSES: Final = SCOPE_STATUSES | {"cancelled", "error"}
SCOPE_OUTCOMES: Final = {
    "allowed": "Allowed",
    "blocked": "Blocked",
    "clarify": "Clarification needed",
    "uncertain": "Further check needed",
    "unavailable": "Unavailable",
    "cancelled": "Cancelled",
    "error": "Error",
}
SCOPE_REASON_LABELS: Final = {
    "supported_task": "Supported task",
    "unsupported_task": "Outside Nimbus's supported tasks",
    "creative_request": "Creative writing request",
    "role_change": "Requested role change",
    "unclear_task": "Requested task is unclear",
    "output_mismatch": "Answer did not match the supported task",
    "unconfigured": "Scope checker is not configured",
    "timeout": "Scope check timed out",
    "invalid_response": "Invalid scope-check response",
    "provider_error": "Scope checker unavailable",
    "oversized": "Scope-check content exceeded its limit",
}
SCOPE_FAILURES: Final = frozenset({"unavailable", "error"})
type ScopeStage = Literal["input", "output"]


@dataclass
class ScopeTrace:
    """One input or output check under the request root, with no inputs, outputs or inherited metadata."""

    request: RequestTrace = field(repr=False)
    stage: ScopeStage
    parent: TraceParent | None = None
    status: str = "error"
    reason: str = ""
    method: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    started: float = field(default_factory=time.perf_counter)
    closed: bool = False

    def start(self) -> None:
        """Create no orphan when tracing is disabled or its request root could not be queued."""
        tracer, upstream = self.request.tracer, self.request.parent
        if tracer is None or upstream is None or self.stage not in SCOPE_TRACE_NAMES:
            return
        run, order, start = upstream.child()
        try:
            tracer.client.create_run(
                id=run,
                trace_id=upstream.trace_id,
                dotted_order=order,
                parent_run_id=upstream.run_id,
                name=SCOPE_TRACE_NAMES[self.stage],
                run_type="chain",
                project_name=tracer.project,
                start_time=start,
                inputs={},
                outputs={},
                tags=[],
                extra={"metadata": {}},
            )
        except Exception:
            structlog.get_logger().warning("trace.scope_write_failed", stage="start")
        else:
            self.parent = TraceParent(upstream.trace_id, run, order)

    def outcome(
        self, status: str, reason: str = "", *, method: str = "", tokens_in: int = 0, tokens_out: int = 0
    ) -> None:
        """Accept only operational vocabulary; never stringify an untrusted classifier response."""
        self.status = status if isinstance(status, str) and status in SCOPE_TRACE_STATUSES else "error"
        self.reason = reason if isinstance(reason, str) and reason in SCOPE_REASONS else ""
        self.method = method if method in ("rule", "model") else ""
        self.tokens_in = tokens_in if isinstance(tokens_in, int) and tokens_in > 0 else 0
        self.tokens_out = tokens_out if isinstance(tokens_out, int) and tokens_out > 0 else 0

    def decided(self, decision: ScopeDecision) -> None:
        """Record a guard decision: its outcome, who made it (rules or Gemini) and the model's token counts."""
        self.outcome(
            decision.status,
            decision.reason,
            method=decision.method,
            tokens_in=decision.tokens_in,
            tokens_out=decision.tokens_out,
        )

    def close(self) -> None:
        """Record a deliberate block as a completed decision and a failed checker as an error."""
        if self.closed:
            return
        self.closed = True
        if self.stage not in SCOPE_TRACE_NAMES:
            return
        structlog.get_logger().info(
            "guardrail.check",
            action=self.stage,
            status=self.status,
            reason=self.reason,
            method=self.method,
            scopeTokensIn=self.tokens_in,
            scopeTokensOut=self.tokens_out,
            ms=to_ms(time.perf_counter() - self.started),
            **self.request.fields(),
        )
        tracer, upstream = self.request.tracer, self.request.parent
        if tracer is None or upstream is None or self.parent is None:
            return
        try:
            tracer.client.update_run(
                self.parent.run_id,
                trace_id=self.parent.trace_id,
                dotted_order=self.parent.dotted_order,
                parent_run_id=upstream.run_id,
                end_time=datetime.now(UTC),
                inputs={},
                outputs={},
                error="Scope check failed" if self.status in SCOPE_FAILURES else None,
                extra={
                    "metadata": {
                        "scope_outcome": self.status,
                        "scope_reason": self.reason,
                        "scope_method": self.method,
                    }
                },
            )
        except Exception:
            structlog.get_logger().warning("trace.scope_write_failed", stage="finish")


@contextmanager
def scope_trace(request: RequestTrace | None, stage: ScopeStage) -> Iterator[ScopeTrace]:
    """Observe the check without capturing its content, hiding exceptions or owning the request flush."""
    operation = ScopeTrace(request or RequestTrace(None), stage)
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
