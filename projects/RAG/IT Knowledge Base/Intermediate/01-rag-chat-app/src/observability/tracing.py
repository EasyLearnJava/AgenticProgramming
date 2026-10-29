"""
IT Knowledge Base: Tracing
==========================

One trace for each unit of work (an HTTP request, the start-up build, a question asked in the terminal), and a timed
span for each stage inside it. It handles:
  1. Holding the current trace in a context variable, which follows the work into async tasks and worker threads: its
     ID, when it began, and whether the trace store keeps its lines
  2. trace_context(): a block of work with a trace of its own
  3. span(): one stage, timed, ending in one log line with its status (ok, failed or cancelled), its duration, when
     it started in the trace's time (offset_ms), and whatever the stage recorded; a span inside another knows how
     deep it is

    with trace_context() as trace_id:                      # every log line written inside carries trace_id
        with span("llm.generate", model="...") as fields:
            ...                                            # the stage's work
            fields["output_tokens"] = 120                  # recorded on the span's line
    # -> INFO [trace_id] src.llm: llm.generate ok  duration_ms=812.4 model=... output_tokens=120
"""
import asyncio
import logging
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from src.utils.helpers import elapsed_ms

NO_TRACE = "-"          # the trace ID of a log line written outside any trace, such as the server starting


@dataclass(frozen=True)
class Trace:
    """The unit of work running now."""
    trace_id: str
    started: float          # time.perf_counter() when it began
    recorded: bool          # whether the trace store keeps its log lines


_current: ContextVar[Trace | None] = ContextVar("trace", default=None)
_depth: ContextVar[int] = ContextVar("span_depth", default=0)       # how many spans are open around the code


def new_trace_id() -> str:
    """16 random hex characters: enough to tell one call from every other in the logs, and for none to be guessed."""
    return secrets.token_hex(8)


def current_trace() -> Trace | None:
    """The trace of the work running now, or None outside any."""
    return _current.get()


def current_trace_id() -> str:
    """The trace ID of the work running now, or NO_TRACE."""
    trace = _current.get()
    return trace.trace_id if trace else NO_TRACE


def trace_offset_ms() -> float:
    """Milliseconds since the current trace began (0.0 outside any): where something happens on its timeline."""
    trace = _current.get()
    return elapsed_ms(trace.started) if trace else 0.0


def span_depth() -> int:
    """How many spans are open around the code running now."""
    return _depth.get()


@contextmanager
def trace_context(trace_id: str | None = None, *, recorded: bool = True) -> Iterator[str]:
    """Run a block of work under a new trace (or the ID given); the previous one is back afterwards. recorded=False
    keeps its lines out of the trace store: the middleware passes it for the page's own files and the health checks."""
    token = _current.set(Trace(trace_id or new_trace_id(), time.perf_counter(), recorded))
    try:
        yield current_trace_id()
    finally:
        _current.reset(token)


@contextmanager
def span(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """
    Time one stage and log how it ended. The stage can add fields to the dict it's given; they go on the line.

    Logs INFO "<name> ok" when it ends normally, WARNING "<name> failed" with error_type when it raises (the error
    goes on up: whoever handles it logs it in full), or WARNING "<name> cancelled" when a deadline or Ctrl+C stops
    it. The line goes to the layer's logger, named from the span's first word: "llm.generate" -> src.llm.
    """
    layer_logger = logging.getLogger(f"src.{name.split('.')[0]}")
    start, offset_ms = time.perf_counter(), trace_offset_ms()
    status, error_type = "ok", None
    token = _depth.set(_depth.get() + 1)              # the stage's own lines sit one level deeper than its span
    try:
        yield fields
    except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
        status = "cancelled"
        raise
    except BaseException as err:
        status, error_type = "failed", type(err).__name__
        raise
    finally:
        _depth.reset(token)
        line = {"span": name, "status": status, "duration_ms": elapsed_ms(start), "offset_ms": offset_ms, **fields}
        if error_type:
            line["error_type"] = error_type
        if status == "ok":
            layer_logger.info("%s ok", name, extra=line)
        else:
            layer_logger.warning("%s %s", name, status, extra=line)
