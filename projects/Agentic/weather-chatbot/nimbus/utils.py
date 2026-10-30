"""
nimbus/utils.py: small helpers the app shares, with no state and no I/O, each tested in tests/unit/test_utils.py.
"""

import uuid
from datetime import UTC, datetime

from nimbus.constants import NEW_REQUEST_ID_CHARS, REQUEST_ID_PATTERN


def new_request_id() -> str:
    """A new request id, for a request that didn't bring one: 16 random hex characters."""
    return uuid.uuid4().hex[:NEW_REQUEST_ID_CHARS]


def to_request_id(header_value: str | None) -> str:
    """
    The header's value if it looks like a request id, else a new one. A header can hold anything, and this value goes
    into every log line and back to the browser.
    """
    if header_value is not None and REQUEST_ID_PATTERN.fullmatch(header_value):
        return header_value
    return new_request_id()


def to_iso(moment: datetime) -> str:
    """A moment as the logs and the APIs write it: UTC, to the millisecond, "2026-10-30T19:57:20.324Z"."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
