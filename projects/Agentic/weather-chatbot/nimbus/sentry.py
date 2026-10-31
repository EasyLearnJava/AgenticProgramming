"""
nimbus/sentry.py: the app's errors, to Sentry (step 12). Each line logged at error goes, as the exception being handled,
with its class and its frames, tagged with where it came from and the ref that finds its lines; a warning (a timeout,
a fallback) stays in the logs. Nothing private goes: Sentry's SDK collects a lot unless told not to (addresses,
headers, bodies, each frame's variables, an exception's message, which can quote what was sent), so each is off, and
its integrations with them: Sentry hears only what the app sends it. Without SENTRY_DSN (a computer, CI), it's off.
"""

import sys
from collections.abc import Mapping
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.dedupe import DedupeIntegration
from sentry_sdk.types import Event, Hint

from nimbus.config import Settings
from nimbus.utils import to_ref

# A line's fields that say where a failure came from, as Sentry's tags: nothing else on the line goes.
TAG_FIELDS = ("event", "requestId", "path", "status", "lane", "tool", "check", "errorClass", "causeClass")


def keep_nothing_private(event: Event, _hint: Hint) -> Event:
    """An event as Sentry gets it: each exception's class and frames, never its message, nor a request's data."""
    for exception in event.get("exception", {}).get("values", []):
        exception.pop("value", None)
    event.pop("request", None)
    event.pop("user", None)
    return event


def to_sentry_options(settings: Settings) -> dict[str, Any]:
    """Sentry's settings: what the app sends, errors only, with nothing private."""
    return {
        "dsn": None if settings.sentry_dsn is None else settings.sentry_dsn.get_secret_value(),
        "environment": settings.environment,
        "release": settings.commit,
        # None of the SDK's own integrations, which would read requests, logs and modules; only one that sends an
        # exception once, should a library log it too.
        "default_integrations": False,
        "auto_enabling_integrations": False,
        "integrations": [DedupeIntegration()],
        # Nothing private, each category said: no user, cookies, headers, query strings or bodies, no AI inputs or
        # outputs, no frame's variables, no breadcrumbs. An exception's message goes before it's sent (before_send).
        "data_collection": {
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "off"}},
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "graphql": {"document": False, "variables": False},
            "gen_ai": {"inputs": False, "outputs": False},
            "database_query_data": False,
            "queues": False,
            "stack_frame_variables": False,
        },
        "max_breadcrumbs": 0,
        "in_app_include": ["nimbus"],
        "before_send": keep_nothing_private,
    }


def start_sentry(settings: Settings) -> bool:
    """Starts Sentry, when the settings have its DSN; whether it's on."""
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(**to_sentry_options(settings))
    return True


def send_failure(line: Mapping[str, Any]) -> None:
    """
    An error line, to Sentry: the exception being handled, with its frames, else the line's event alone; tagged with
    the line's fields that say where it came from, and the ref that finds its lines.
    """
    tags = {name: str(line[name]) for name in TAG_FIELDS if line.get(name) is not None}
    if "requestId" in tags:
        tags["ref"] = to_ref(tags["requestId"])
    error = sys.exc_info()[1]
    if error is None:
        sentry_sdk.capture_message(tags.get("event", "error"), level="error", tags=tags)
    else:
        sentry_sdk.capture_exception(error, tags=tags)
