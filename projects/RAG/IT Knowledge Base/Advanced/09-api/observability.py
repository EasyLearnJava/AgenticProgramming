"""
IT Knowledge Base: Request IDs and Logs
=======================================

Makes every request traceable through the logs without the logs leaking what was asked. It handles:
  1. The request's ID, in a context variable: every log line written while it's served, in any module and in the
     worker threads the engine runs in, carries it
  2. The request's fields (its caller, the answer's status, tokens and cost): the routes add them with note(), and
     the middleware writes them in the request's one access line
  3. Two formats: JSON, an object per line, for a log service to search and chart; text, for reading. Every line has
     the time (UTC), the level, the logger, the request ID, the message and the fields
  4. Masking: each secret handed to setup_logging() (the Gemini key) is replaced by ********** in every line

Nothing here logs a question, an answer or an API key: the API's own lines carry IDs, statuses, times and counts.

    setup_logging("INFO", "json", secrets=[gemini_key])
    {"time": "2026-10-30T21:03:11.402Z", "level": "INFO", "logger": "api", "request_id": "9f2c...", "message": ...}
"""
import json
import logging
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

NO_REQUEST = "-"                     # the request ID of a line written outside any request (start-up, say)
MASK = "**********"

_request_id: ContextVar[str] = ContextVar("request_id", default=NO_REQUEST)
_fields: ContextVar[dict[str, Any] | None] = ContextVar("request_fields", default=None)

# What every LogRecord has; anything else on one came from `extra=` and is a field. color_message is uvicorn's copy of
# its message with terminal colours in it
STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message", "asctime", "taskName", "request_id", "color_message"}
QUIET_LOGGERS = ("httpx", "httpcore", "asyncio")   # below WARNING, kept out: a line per HTTP call drowns the rest


@contextmanager
def request_context(request_id: str) -> Iterator[dict[str, Any]]:
    """While one request is served: its ID on every log line, and the dict of fields for its access line."""
    fields: dict[str, Any] = {}
    id_token, fields_token = _request_id.set(request_id), _fields.set(fields)
    try:
        yield fields
    finally:
        _request_id.reset(id_token)
        _fields.reset(fields_token)


def current_request_id() -> str:
    return _request_id.get()


def note(**fields: Any) -> None:
    """Add fields to the current request's access line; outside a request, nothing happens."""
    current = _fields.get()
    if current is not None:
        current.update(fields)


def mask(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, MASK)
    return text


class RequestIdFilter(logging.Filter):
    """Adds request_id, the current request's ID, to every record a handler gets."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


class QuietLibrariesFilter(logging.Filter):
    """Drops the chatty libraries' lines below WARNING: their warnings and errors still show."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or record.name.split(".")[0] not in QUIET_LOGGERS


class JsonFormatter(logging.Formatter):
    """One JSON object per line: the time, level, logger, request ID and message, then the fields."""

    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        entry = {"time": timestamp(record), "level": record.levelname, "logger": record.name,
                 "request_id": getattr(record, "request_id", NO_REQUEST), "message": record.getMessage(),
                 **record_fields(record)}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return mask(json.dumps(entry, ensure_ascii=False, default=str), self.secrets)


class TextFormatter(JsonFormatter):
    """One readable line: time, level, [request ID], logger: message, then the fields as key=value."""

    def format(self, record: logging.LogRecord) -> str:
        line = (f"{timestamp(record)} {record.levelname:<7} [{getattr(record, 'request_id', NO_REQUEST)}] "
                f"{record.name}: {record.getMessage()}")
        fields = record_fields(record)
        if fields:
            line += "  " + " ".join(f"{key}={json.dumps(value, ensure_ascii=False, default=str)}"
                                    for key, value in fields.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return mask(line, self.secrets)


def timestamp(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")[:-6] + "Z"


def record_fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields a log line was given with `extra=`."""
    return {key: value for key, value in vars(record).items() if key not in STANDARD_ATTRIBUTES}


_installed: list[logging.Handler] = []      # what setup_logging() added, so a second call replaces it


def setup_logging(level: str = "INFO", log_format: str = "json", secrets: Iterable[str] = ()) -> None:
    """Send every log line, the libraries' too, to stderr in one format, each with its request ID; a second call
    replaces what the first set up, and handlers others added (pytest's) are left alone."""
    root = logging.getLogger()
    for handler in _installed:
        root.removeHandler(handler)
    _installed.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter(secrets) if log_format == "json" else TextFormatter(secrets))
    handler.addFilter(RequestIdFilter())
    handler.addFilter(QuietLibrariesFilter())
    root.addHandler(handler)
    _installed.append(handler)
    root.setLevel(level)
    logging.captureWarnings(True)
