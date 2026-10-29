"""
IT Knowledge Base: The Trace Store
==================================

Keeps the log lines of the newest traces in memory, so each one can be read back by its trace ID: the chat page shows
each request's trace in boxes beside its answer, from GET /api/v1/traces/{trace_id}. It handles:
  1. Collecting each log line under its trace, as one more handler of the logging system: whatever module or library
     wrote it, from any task or worker thread. The app's lines are kept from DEBUG up, the libraries' from INFO up
  2. Keeping the newest max_traces traces, and up to MAX_EVENTS lines each; a pinned trace (the start-up build's) is
     never dropped
  3. Each line as an event on the trace's timeline: when it happened (a span: when it started), how many spans it
     sits inside, its level, logger, message and fields; secrets masked, and an error's type and message, never its
     traceback (that stays in the log file)

    store = TraceStore(max_traces=200, secrets=[api_key])      # main.py makes it; setup_logging() installs it
    store.get(trace_id)    ->  {"events": [...], "dropped": 0}, the events in timeline order; or None
"""
import json
import logging
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from pydantic import SecretStr

from src.observability.logging_setup import APP_LOGGERS, mask, record_fields
from src.observability.tracing import current_trace, span_depth, trace_offset_ms

MAX_EVENTS = 300        # lines kept per trace; more are counted, not kept


class TraceStore(logging.Handler):
    """
    The log lines of the newest traces, by trace ID.

    Step 1: Configure: the constructor stores the limits and the secrets to mask; it holds no lines yet
    Step 2: Collect: as a logging handler, emit() files each line under the trace it was written in
    Step 3: Read: get() gives one trace's events, in timeline order
    """

    def __init__(self, *, max_traces: int, secrets: Iterable[SecretStr] = ()):
        super().__init__(logging.DEBUG)
        self.max_traces = max_traces
        self.secrets = tuple(secret.get_secret_value() for secret in secrets)
        self._traces: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._dropped: dict[str, int] = {}
        self._pinned: set[str] = set()

    def emit(self, record: logging.LogRecord) -> None:
        """File one log line under its trace. logging calls this, holding the handler's lock."""
        trace = current_trace()
        if trace is None or not trace.recorded:
            return
        if record.levelno < logging.INFO and record.name.split(".")[0] not in APP_LOGGERS:
            return
        try:
            event = self._event(record)
        except Exception:                      # a line that can't be made into an event never stops the app
            self.handleError(record)
            return
        events = self._traces.get(trace.trace_id)
        if events is None:
            events = self._traces[trace.trace_id] = []
            self._drop_oldest()
        if len(events) < MAX_EVENTS:
            events.append(event)
        else:
            self._dropped[trace.trace_id] = self._dropped.get(trace.trace_id, 0) + 1

    def pin(self, trace_id: str) -> None:
        """Never drop this trace, however many come after it."""
        with self.lock:
            self._pinned.add(trace_id)

    def get(self, trace_id: str) -> dict[str, Any] | None:
        """One trace's events, in timeline order (an enclosing span before what's inside it), and how many lines
        weren't kept; or None if no trace with this ID is kept."""
        with self.lock:
            if trace_id not in self._traces:
                return None
            events = [dict(event) for event in self._traces[trace_id]]
            dropped = self._dropped.get(trace_id, 0)
        return {"events": sorted(events, key=lambda event: (event["at_ms"], event["depth"])), "dropped": dropped}

    def _event(self, record: logging.LogRecord) -> dict[str, Any]:
        """One log line as an event: everything on it, secrets masked."""
        fields = record_fields(record)
        span = fields.pop("span", None)
        offset_ms = fields.pop("offset_ms", None)
        logged_ms = trace_offset_ms()
        event = {"at_ms": offset_ms if span and offset_ms is not None else logged_ms, "logged_ms": logged_ms,
                 "depth": span_depth(), "level": record.levelname, "logger": record.name,
                 "message": record.getMessage(), "span": span, "status": fields.pop("status", None),
                 "duration_ms": fields.pop("duration_ms", None), "fields": fields, "error": None}
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            event["error"] = f"{type(error).__name__}: {error}"
        # Through JSON: masks a secret wherever it is, and leaves only values the API can send
        return json.loads(mask(json.dumps(event, ensure_ascii=False, default=str), self.secrets))

    def _drop_oldest(self) -> None:
        """Drop the oldest unpinned traces until at most max_traces are kept."""
        while len(self._traces) > self.max_traces:
            oldest = next((trace_id for trace_id in self._traces if trace_id not in self._pinned), None)
            if oldest is None:
                return
            del self._traces[oldest]
            self._dropped.pop(oldest, None)
