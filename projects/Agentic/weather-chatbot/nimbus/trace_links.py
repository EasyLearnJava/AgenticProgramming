"""Issue short-lived Activity links for trace roots recorded by Nimbus in Axiom."""

import hmac
import json
import re
from datetime import datetime, timedelta
from uuid import UUID

from nimbus.config import Settings
from nimbus.constants import OBSERVABILITY_DAYS

_HANDLE = re.compile(r"([0-9a-f]{32})\.([0-9]{10})\.([a-zA-Z0-9]{0,8})\.([0-9a-f]{64})", re.ASCII)
_WINDOW = timedelta(days=OBSERVABILITY_DAYS)


def _signature(settings: Settings, payload: str) -> str:
    """Bind a public link to this dataset and project across serverless instances, using Activity's existing key."""
    token = settings.axiom_query_token
    if token is None:
        raise ValueError("Activity requires its read credential")
    message = json.dumps(["nimbus/activity-trace/v1", settings.axiom_dataset, settings.langsmith_project, payload])
    return hmac.digest(token.get_secret_value().encode(), message.encode(), "sha256").hex()


def trace_url(settings: Settings, root: str, started: datetime, ref: str, now: datetime) -> str | None:
    """Issue links within the same start-time window used to read LangSmith. Older chats have no trace ID."""
    if settings.axiom_query_token is None or not now - _WINDOW < started <= now:
        return None
    try:
        trace_id = UUID(root)
    except ValueError:
        return None
    if trace_id.version != 4 or str(trace_id) != root:
        return None
    payload = f"{trace_id.hex}.{int((started + _WINDOW).timestamp())}.{ref}"
    return f"/activity/trace/{payload}.{_signature(settings, payload)}"


def resolve_trace_link(settings: Settings, handle: str, now: datetime) -> tuple[UUID, str] | None:
    """Authenticate the exact trace, expiry and public ref before any LangSmith request."""
    match = _HANDLE.fullmatch(handle)
    if match is None or settings.axiom_query_token is None:
        return None
    root, expires, ref, signature = match.groups()
    if int(expires) <= now.timestamp():
        return None
    if not hmac.compare_digest(signature, _signature(settings, handle.rsplit(".", 1)[0])):
        return None
    return UUID(hex=root), ref
