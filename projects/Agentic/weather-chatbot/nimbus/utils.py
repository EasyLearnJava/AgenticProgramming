"""
nimbus/utils.py: small helpers the app shares, with no state and no I/O, each tested in tests/unit/test_utils.py.
"""

import re
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from nimbus.constants import LIBRARY_LOG_MAX_FRAMES, NEW_REQUEST_ID_CHARS, REQUEST_ID_PATTERN

MS_PER_SECOND = 1000
REF_CHARS = 8
# Where a browser ends a line of a server-sent event: \r\n, \r or \n, and nowhere else.
SSE_LINE_BREAK = re.compile(r"\r\n|\r|\n")
# A web address, in any case, from its scheme to the next space, quote or angle bracket. Nothing is required after it,
# so each search ends where the last one did: a pattern that needed a ? after the address searched again from every
# "http" in the text (issue 43). Only a query string in such an address is cut; urllib3's debug lines ("GET /a?b
# HTTP/1.1") aren't, and the level never writes them.
WEB_ADDRESS = re.compile(r"https?://[^\s\"'<>]*", re.IGNORECASE)
# The punctuation that ends a sentence rather than a query string ("...?id=1: timeout").
SENTENCE_END = ".,:;!?)]"


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


def _without_query(match: re.Match[str]) -> str:
    """A web address with its query string cut to "?...": what comes after its #, and a sentence's end, are kept."""
    address, hash_mark, fragment = match[0].partition("#")
    path, question_mark, query = address.partition("?")
    if not question_mark:
        return match[0]
    sentence_end = query[len(query.rstrip(SENTENCE_END)) :]
    return f"{path}?...{sentence_end}{hash_mark}{fragment}"


def to_redacted_urls(text: str) -> str:
    """
    The text with each web address's query string cut to "?...", for another library's log line: a query string can
    hold what a visitor typed, or where they are ("forecast?latitude=48.85&..." → "forecast?...").
    """
    return WEB_ADDRESS.sub(_without_query, text)


def _to_frame_line(frame: traceback.FrameSummary) -> str:
    """One frame of an exception, as a log line gives it: "nimbus/chat.py:281 chat"."""
    path = Path(frame.filename)
    return f"{path.parent.name}/{path.name}:{frame.lineno} {frame.name}"


def to_frames(trace: TracebackType | None) -> list[str]:
    """
    Where an exception went, for a log line: its innermost 8 frames, each as "nimbus/chat.py:281 chat", with none of
    its values or messages, which can hold anything. No source file is read.
    """
    frames = traceback.StackSummary.extract(traceback.walk_tb(trace), lookup_lines=False)[-LIBRARY_LOG_MAX_FRAMES:]
    return [_to_frame_line(frame) for frame in frames]
