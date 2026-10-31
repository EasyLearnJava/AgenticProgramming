"""
nimbus/utils.py: small helpers the app shares, with no state and no I/O, each tested in tests/unit/test_utils.py.
"""

import re
import uuid
from datetime import UTC, datetime

from nimbus.constants import NEW_REQUEST_ID_CHARS, REQUEST_ID_PATTERN

MS_PER_SECOND = 1000
REF_CHARS = 8
# Where a browser ends a line of a server-sent event: \r\n, \r or \n, and nowhere else.
SSE_LINE_BREAK = re.compile(r"\r\n|\r|\n")


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


def to_ms(seconds: float) -> int:
    """A time in seconds as the logs write it: whole milliseconds."""
    return round(seconds * MS_PER_SECOND)


def to_ref(request_id: str) -> str:
    """
    A request's ref, which an error's sentence ends with: the last 8 letters and digits of its id, short enough to
    read out, and enough to find its log lines ("cle1::...-fa4d33a7af21" → "33a7af21").
    """
    return "".join(char for char in request_id if char.isalnum())[-REF_CHARS:]


def new_turn_id() -> str:
    """A new id for a chat turn, which its elements' ids in the page carry: 16 random hex characters."""
    return uuid.uuid4().hex[:NEW_REQUEST_ID_CHARS]


def to_sse_message(data: str) -> str:
    """
    One server-sent event: each line of the data on a `data:` line of its own, then a blank line, which ends the
    event. The browser joins the lines back with \\n.
    """
    return "".join(f"data: {line}\n" for line in SSE_LINE_BREAK.split(data)) + "\n"
