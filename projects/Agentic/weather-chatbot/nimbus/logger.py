"""
nimbus/logger.py: the app's one way to log: structlog, one JSON object per line on stdout, which Vercel's logs keep
(from step 12, Axiom gets the same lines). Every line names the build it came from; a request's lines also carry its
request id, which the request middleware binds. The field names are the TypeScript app's (requestId, deploymentId),
so the Axiom queries written for it keep working.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.typing import Processor

from nimbus.config import Settings


def _with_build_fields(settings: Settings) -> Processor:
    """A step that adds the build's fields to every line: its environment, commit and deployment."""
    fields = {"env": settings.environment, "commit": settings.commit, "deploymentId": settings.vercel_deployment_id}

    def add_build_fields(_logger: Any, _method: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        """The line, with the build's fields added."""
        event.update(fields)
        return event

    return add_build_fields


def configure_logging(settings: Settings) -> None:
    """
    Sets up structlog for the whole app: JSON lines on stdout, at the configured level. Loggers aren't cached, so a
    later configuration (a test's, say) reaches every logger, including one made before it.
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
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
