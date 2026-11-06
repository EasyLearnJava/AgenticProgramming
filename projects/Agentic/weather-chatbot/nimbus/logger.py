"""
nimbus/logger.py: the app's one way to log: structlog, one JSON object per line on stdout, which Vercel's logs keep;
from step 12, each line also waits for Axiom, when it's set up, and a line at error goes to Sentry, when that is. Every
line names the build it came from; a request's lines also carry its request id, which the request middleware binds.
The field names are the TypeScript app's (requestId, deploymentId), so the Axiom queries written for it keep working.
Other libraries' lines come through here too, as ours.
"""

import logging
import threading
from collections.abc import MutableMapping
from typing import Any

import sentry_sdk
import structlog
from structlog.typing import Processor

from nimbus.axiom import LogShipper
from nimbus.config import Settings
from nimbus.constants import LIBRARY_LOG_LEVEL
from nimbus.sentry import send_failure
from nimbus.travel.mcp_client import travel_mcp_active
from nimbus.utils import to_frames, to_redacted_urls

ERROR_LEVELS = frozenset({"error", "critical"})
_WRITE_LOCK = threading.Lock()


def _with_build_fields(settings: Settings) -> Processor:
    """A step that adds the build's fields to every line: its environment, commit and deployment."""
    fields = {"env": settings.environment, "commit": settings.commit, "deploymentId": settings.vercel_deployment_id}

    def add_build_fields(_logger: Any, _method: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """The line, with the build's fields added."""
        event.update(fields)
        return event

    return add_build_fields


def _send_errors_to_sentry(_logger: Any, _method: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """A step that sends a line at error to Sentry too, when Sentry is on (sentry.py); the line goes on as it is."""
    if event.get("level") in ERROR_LEVELS and sentry_sdk.get_client().is_active():
        send_failure(event)
    return event


class LineLogger:
    """
    Where structlog writes each line: on stdout, as it is when the line is written (given no file, print writes to the
    stdout of that moment, so a line never goes to a stream a test has since closed), and, when Axiom is set up, to
    its shipper, which keeps it for the request's end (step 12).
    """

    def __init__(self, shipper: LogShipper | None) -> None:
        """A logger that also hands each line to the shipper, if there is one."""
        self._shipper = shipper

    def msg(self, message: str) -> None:
        """Writes the line, whole, before any other thread's."""
        with _WRITE_LOCK:
            print(message, flush=True)
        if self._shipper is not None:
            self._shipper.write(message)

    log = debug = info = warn = warning = err = error = critical = exception = fatal = msg


class LibraryLogHandler(logging.Handler):
    """
    Writes another library's log record as a line of ours: its message, with each web address's query string cut
    off; its logger's name; and of an exception, only its class and its frames (file, line and function), since an
    exception's message can quote what was sent.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Writes the record through structlog, so it gets the same fields as the app's own lines."""
        # External MCP libraries may include the remote error body in a warning.
        # The travel service emits its own bounded status independently of these records.
        if travel_mcp_active.get():
            return
        try:
            fields: dict[str, object] = {"logger": record.name}
            if record.exc_info is not None and record.exc_info[0] is not None:
                fields["exceptionClass"] = record.exc_info[0].__name__
                fields["exceptionFrames"] = to_frames(record.exc_info[2])
            # structlog names the standard levels only: a library's own level in between takes the one below it.
            level = min(record.levelno // 10 * 10, logging.CRITICAL)
            structlog.get_logger().log(level, to_redacted_urls(record.getMessage()), **fields)
        except Exception:
            self.handleError(record)


def configure_logging(settings: Settings, shipper: LogShipper | None = None) -> None:
    """
    Sets up structlog for the whole app: JSON lines on stdout, at the configured level, each also to the shipper, if
    there is one (Axiom's), and each at error to Sentry, if it's on. Loggers aren't cached, so a later configuration (a
    test's, say) reaches every logger, including one made before it. Other libraries' warnings and errors become lines
    of ours; their info lines are never written.
    """
    structlog.configure(
        processors=[
            # ① The line's level and time, then the build's fields and the request's (its id).
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _with_build_fields(settings),
            structlog.contextvars.merge_contextvars,
            # ② A line at error, to Sentry too, with the request's id among its tags (step 12).
            _send_errors_to_sentry,
            # ③ One JSON object per line.
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[settings.log_level.upper()]),
        logger_factory=lambda *_args: LineLogger(shipper),
        cache_logger_on_first_use=False,
    )
    # ④ Every other library's lines: their info lines named each request they sent, a query string included, and on
    # Vercel they came out as plain text (issue 43). Our handler replaces any the platform put on the root logger, so
    # no line is written twice, and its own level holds even for a library that sets its logger's lower.
    root = logging.getLogger()
    root.handlers = [LibraryLogHandler(level=LIBRARY_LOG_LEVEL)]
    root.setLevel(LIBRARY_LOG_LEVEL)
