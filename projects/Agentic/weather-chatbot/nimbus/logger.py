"""
nimbus/logger.py: the app's one way to log: structlog, one JSON object per line on stdout, which Vercel's logs keep
(from step 12, Axiom gets the same lines). Every line names the build it came from; a request's lines also carry its
request id, which the request middleware binds. The field names are the TypeScript app's (requestId, deploymentId),
so the Axiom queries written for it keep working. Other libraries' lines come through here too, as ours.
"""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.typing import Processor

from nimbus.config import Settings
from nimbus.constants import LIBRARY_LOG_LEVEL
from nimbus.utils import to_frames, to_redacted_urls


def _with_build_fields(settings: Settings) -> Processor:
    """A step that adds the build's fields to every line: its environment, commit and deployment."""
    fields = {"env": settings.environment, "commit": settings.commit, "deploymentId": settings.vercel_deployment_id}

    def add_build_fields(_logger: Any, _method: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """The line, with the build's fields added."""
        event.update(fields)
        return event

    return add_build_fields


class LibraryLogHandler(logging.Handler):
    """
    Writes another library's log record as a line of ours: its message, with each web address's query string cut
    off; its logger's name; and of an exception, only its class and its frames (file, line and function), since an
    exception's message can quote what was sent.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Writes the record through structlog, so it gets the same fields as the app's own lines."""
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


def configure_logging(settings: Settings) -> None:
    """
    Sets up structlog for the whole app: JSON lines on stdout, at the configured level. Loggers aren't cached, so a
    later configuration (a test's, say) reaches every logger, including one made before it. Other libraries' warnings
    and errors become lines of ours; their info lines are never written.
    """
    structlog.configure(
        processors=[
            # ① The line's level and time, then the build's fields and the request's (its id).
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _with_build_fields(settings),
            structlog.contextvars.merge_contextvars,
            # ② One JSON object per line.
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[settings.log_level.upper()]),
        # stdout as it is when a line is written: given no file, structlog prints to the stdout of that moment, so a
        # line never goes to a stream a test has since closed.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    # ③ Every other library's lines: their info lines named each request they sent, a query string included, and on
    # Vercel they came out as plain text (issue 43). Our handler replaces any the platform put on the root logger, so
    # no line is written twice, and its own level holds even for a library that sets its logger's lower.
    root = logging.getLogger()
    root.handlers = [LibraryLogHandler(level=LIBRARY_LOG_LEVEL)]
    root.setLevel(LIBRARY_LOG_LEVEL)
