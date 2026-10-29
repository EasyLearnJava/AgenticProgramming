"""
IT Knowledge Base: Logging
==========================

Sets up logging once, at start-up, for the app and every library it uses. It handles:
  1. Stamping every log line with the current trace ID, whichever module or library wrote it
  2. Two outputs at logging.level: the console (stderr), as readable text, and the log file, one JSON object per line,
     rotated by size so it never fills the disk
  3. A third, when it's handed one: the trace store, which keeps each request's lines for the page to show, the app's
     from DEBUG up whatever logging.level is, and the libraries' from INFO up (httpx's line for each call to Google,
     Google's retries)
  4. Masking secrets: the API key is replaced by ********** in every line, should a library ever put it in one
  5. Keeping the console and the file to what's worth a line there: no httpx line per HTTP request (the spans time
     each call), no asyncio notes on itself, and no Google notice about a feature this app never uses

Usage (main.py calls it, once):
    setup_logging(settings.logging, secrets=[api_key], trace_store=trace_store)

    console:  2026-10-29T21:03:11.402Z INFO    [9f2c4e1a7b3d4c5e] src.llm: llm.generate ok  duration_ms=812.4 ...
    file:     {"time": "2026-10-29T21:03:11.402Z", "level": "INFO", "trace_id": "9f2c4e1a7b3d4c5e", ...}
"""
import json
import logging
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from typing import Any

from pydantic import SecretStr

from src.config.settings import LoggingSettings
from src.observability.tracing import NO_TRACE, current_trace_id

MASK = "**********"

# What every LogRecord has; anything else on a record came from `extra=` and is one of its fields. color_message is
# uvicorn's copy of its message with terminal colours in it: the same text again.
STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime", "taskName",
                                                                                   "trace_id", "color_message"}
# In the text format these are already in the message ("llm.generate ok") or only matter on a timeline; the JSON
# format keeps them as fields
TEXT_HIDDEN_FIELDS = {"span", "status", "offset_ms"}
APP_LOGGERS = ("src", "main")                       # the app's own loggers: src.<layer>, and main.py's
QUIET_LOGGERS = ("httpx", "httpcore", "asyncio")    # below WARNING, kept off the console and the file
TRACED_LIBRARY_LOGGERS = ("httpx", "google_genai")  # at INFO, for the trace store: each HTTP call, each retry

_installed: list[logging.Handler] = []      # the handlers setup_logging() added, so a second call replaces them


def mask(text: str, secrets: Iterable[str]) -> str:
    """The text with every secret in it replaced by MASK."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, MASK)
    return text


def record_fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields a log line was given with `extra=`."""
    return {key: value for key, value in vars(record).items() if key not in STANDARD_ATTRIBUTES}


class TraceIdFilter(logging.Filter):
    """Adds trace_id, the current trace's ID, to every record a handler gets."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id()
        return True


class QuietLibrariesFilter(logging.Filter):
    """Drops the chatty libraries' lines below WARNING: their warnings and errors still show."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING or record.name.split(".")[0] not in QUIET_LOGGERS


class _Formatter(logging.Formatter):
    """What both formats share: the time in UTC, and masking the secrets."""

    def __init__(self, secrets: Iterable[str] = ()):
        super().__init__()
        self.secrets = tuple(secret for secret in secrets if secret)

    @staticmethod
    def timestamp(record: logging.LogRecord) -> str:
        return datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")[:-6] + "Z"


class TextFormatter(_Formatter):
    """One readable line: time, level, [trace ID], logger: message, then the fields as key=value."""

    def format(self, record: logging.LogRecord) -> str:
        line = (f"{self.timestamp(record)} {record.levelname:<7} [{getattr(record, 'trace_id', NO_TRACE)}] "
                f"{record.name}: {record.getMessage()}")
        fields = {key: value for key, value in record_fields(record).items() if key not in TEXT_HIDDEN_FIELDS}
        if fields:
            line += "  " + " ".join(f"{key}={_text_value(value)}" for key, value in fields.items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return mask(line, self.secrets)


class JsonFormatter(_Formatter):
    """One JSON object per line, for searching and charting: the same facts as the text line, each as a field."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {"time": self.timestamp(record), "level": record.levelname,
                 "trace_id": getattr(record, "trace_id", NO_TRACE), "logger": record.name,
                 "message": record.getMessage(), **record_fields(record)}
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return mask(json.dumps(entry, ensure_ascii=False, default=str), self.secrets)


def _text_value(value: Any) -> str:
    """A field's value for the text format: lists and texts with spaces as JSON, so each stays one token."""
    if isinstance(value, (list, tuple, dict)) or (isinstance(value, str) and (" " in value or not value)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _drop_unused_feature_notice(record: logging.LogRecord) -> bool:
    """Google's client logs that "automatic function calling" (AFC) is on, on every call: a feature this app never
    uses. Only those lines are dropped; any other still shows."""
    message = record.getMessage()
    return "AFC" not in message and "automatic function calling" not in message


def setup_logging(settings: LoggingSettings, secrets: Iterable[SecretStr] = (),
                  trace_store: logging.Handler | None = None) -> None:
    """Send every log line to the console and the log file, each stamped with its trace ID, and to the trace store
    when there is one; a second call replaces what the first set up. Handlers that others added (pytest's, say) are
    left alone. Raises OSError when the log file can't be opened."""
    root = logging.getLogger()
    for handler in _installed:
        root.removeHandler(handler)
        handler.close()
    _installed.clear()

    values = [secret.get_secret_value() for secret in secrets]
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(JsonFormatter(values) if settings.console_format == "json" else TextFormatter(values))
    outputs: list[logging.Handler] = [console]
    if settings.file is not None:
        settings.file.parent.mkdir(parents=True, exist_ok=True)
        # Opened now, not at the first line: a path that can't be written (a folder, say) stops the start
        log_file = RotatingFileHandler(settings.file, maxBytes=settings.max_bytes, backupCount=settings.backup_count,
                                       encoding="utf-8")
        log_file.setFormatter(JsonFormatter(values))
        outputs.append(log_file)
    for handler in outputs:
        handler.setLevel(settings.level)       # the level is the outputs': the trace store may take more
        handler.addFilter(TraceIdFilter())
        handler.addFilter(QuietLibrariesFilter())
    for handler in outputs + ([trace_store] if trace_store is not None else []):
        root.addHandler(handler)
        _installed.append(handler)
    root.setLevel(settings.level)

    # With a trace store, the app's DEBUG lines and the libraries' INFO lines are made whatever logging.level is:
    # the store keeps them for the page, and the outputs still show only logging.level and up
    for name in APP_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG if trace_store is not None else logging.NOTSET)
    for name in TRACED_LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO if trace_store is not None else logging.NOTSET)

    logging.captureWarnings(True)                  # Python's warnings become log lines, with their trace ID
    google = logging.getLogger("google_genai.models")
    if _drop_unused_feature_notice not in google.filters:
        google.addFilter(_drop_unused_feature_notice)
