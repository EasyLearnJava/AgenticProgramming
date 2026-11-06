"""
nimbus/utils.py: small helpers the app shares, with no state and no I/O, each tested in tests/unit/test_utils.py.
"""

import re
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal
from urllib.parse import parse_qsl, urlsplit

from markdown_it.common.normalize_url import normalizeLink

from nimbus.constants import (
    DEFAULT_LOCALE,
    IMPERIAL_REGIONS,
    LIBRARY_LOG_MAX_FRAMES,
    LOCALE_MAX_CHARS,
    LOCALE_PATTERN,
    NEW_REQUEST_ID_CHARS,
    REQUEST_ID_PATTERN,
)

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


def checked_source_url(value: str) -> str:
    """A canonical public HTTPS NPS URL, with optional fragment and default port, but no credentials or query."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Park sources cannot contain control characters")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname not in {"www.nps.gov", "nps.gov", "home.nps.gov"}
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
    ):
        raise ValueError("Park sources must be public HTTPS pages on NPS domains")
    # Canonicalize just as Markdown does, so citation allowlists match the rendered href, including Unicode paths.
    return normalizeLink(parts._replace(scheme="https", netloc=parts.hostname).geturl())


def is_same_origin(origin: str | None, destination: str) -> bool:
    """Allow nonbrowser callers or the same HTTP origin; reject malformed origins without echoing their text."""
    if not origin:
        return True
    try:
        supplied, target = urlsplit(origin), urlsplit(destination)
        if (
            supplied.scheme not in {"http", "https"}
            or not supplied.hostname
            or supplied.username
            or supplied.password
            or supplied.query
            or supplied.fragment
            or supplied.path not in {"", "/"}
        ):
            return False
        return (supplied.scheme, supplied.hostname, supplied.port or (443 if supplied.scheme == "https" else 80)) == (
            target.scheme,
            target.hostname,
            target.port or (443 if target.scheme == "https" else 80),
        )
    except ValueError:
        return False


def checked_form_fields(body: bytes, *, max_fields: int) -> dict[str, str]:
    """Decode a bounded UTF-8 form, rejecting empty submissions, too many fields and duplicate field names."""
    pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, errors="strict", max_num_fields=max_fields)
    if not pairs or len(dict(pairs)) != len(pairs):
        raise ValueError("Empty or duplicate form fields")
    return dict(pairs)


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


def hide_error_text(data: dict[str, Any]) -> dict[str, Any]:
    """
    LangSmith's anonymizer (issue 68): a failed run's error says only that it failed, since its text, the exception's
    own words and its traceback, can quote a tool's input or the question; anything else it's given, a run's metadata
    with its lane, goes on as it is.
    """
    return {**data, "error": "hidden"} if "error" in data else data


def is_usable_locale(value: str) -> bool:
    """A language tag the app can use: at most 35 characters, letters, digits and hyphens ("en-GB", "zh-Hant-TW")."""
    return len(value) <= LOCALE_MAX_CHARS and LOCALE_PATTERN.fullmatch(value) is not None


def to_browser_locale(accept_language: str) -> str:
    """
    The browser's first language, from a request's Accept-Language header ("en-GB,en;q=0.9" → "en-GB"), checked as
    the chat checks its locale field; else the default, as the chat takes it.
    """
    first = accept_language.split(",")[0].split(";")[0].strip()
    return first if is_usable_locale(first) else DEFAULT_LOCALE


def to_region(locale: str) -> str:
    """
    A language tag's region: its subtag of two letters or three digits ("en-US" → "US", "zh-Hant-TW" → "TW", "es-419"
    → "419"), before any extension or private part (-u-..., -x-...); "" when it has none.
    """
    for subtag in locale.split("-")[1:]:
        if len(subtag) == 1:
            break
        if (len(subtag) == 2 and subtag.isalpha()) or (len(subtag) == 3 and subtag.isdigit()):
            return subtag.upper()
    return ""


def to_unit_system(locale: str) -> Literal["imperial", "metric"]:
    """A locale's system of units: imperial where its region uses them (en-US), else metric (en-GB, fr, ...)."""
    return "imperial" if to_region(locale) in IMPERIAL_REGIONS else "metric"


# The planner's four currencies, by the browser's region (Bulgaria has used the euro since 2026); else US dollars.
EURO_REGIONS: Final = frozenset(
    {"AT", "BE", "BG", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV", "MT", "NL"}
    | {"PT", "SI", "SK"}
)


# Languages most of whose speakers use the euro, for a browser that reports a language alone ("de", "fr").
EURO_LANGUAGES: Final = frozenset({"bg", "de", "el", "et", "fi", "fr", "hr", "it", "lt", "lv", "mt", "nl", "sk", "sl"})


def to_currency(locale: str) -> str:
    """The currency travel prices are searched in for a locale: GBP for en-GB, CAD for Canada, EUR in the euro area."""
    region = to_region(locale)
    if not region:
        return "EUR" if locale.split("-")[0].lower() in EURO_LANGUAGES else "USD"
    return {"GB": "GBP", "CA": "CAD"}.get(region, "EUR" if region in EURO_REGIONS else "USD")
