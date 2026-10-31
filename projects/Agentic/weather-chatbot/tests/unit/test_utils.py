"""
tests/unit/test_utils.py: the shared helpers: request ids, refs and turn ids, times, server-sent events, web
addresses without their query strings, and an exception's frames.
"""

import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from nimbus.utils import (
    new_request_id,
    new_turn_id,
    to_frames,
    to_iso,
    to_ms,
    to_redacted_urls,
    to_ref,
    to_request_id,
    to_sse_message,
)

HEX = set("0123456789abcdef")


def test_a_new_request_id_is_16_hex_characters_and_new_each_time() -> None:
    first, second = new_request_id(), new_request_id()
    assert len(first) == 16
    assert set(first) <= HEX
    assert first != second


@pytest.mark.parametrize("header", ["cle1::v9h4q-1793390239541-fa4d33a7af21", "iad1::abc_def.1", "a", "x" * 128])
def test_keeps_a_header_that_looks_like_a_request_id(header: str) -> None:
    assert to_request_id(header) == header


@pytest.mark.parametrize("header", ["", "has space", "x" * 129, "naïve", "line\n", "a/b", "<script>"])
def test_replaces_a_header_that_does_not(header: str) -> None:
    request_id = to_request_id(header)
    assert request_id != header
    assert len(request_id) == 16


def test_makes_a_new_one_when_there_is_no_header() -> None:
    assert len(to_request_id(None)) == 16


def test_a_moment_is_written_in_utc_to_the_millisecond() -> None:
    assert to_iso(datetime(2026, 10, 30, 19, 57, 20, 324_567, tzinfo=UTC)) == "2026-10-30T19:57:20.324Z"
    dallas = timezone(timedelta(hours=-5))
    assert to_iso(datetime(2026, 10, 30, 14, 57, tzinfo=dallas)) == "2026-10-30T19:57:00.000Z"


def test_a_ref_is_the_last_8_letters_and_digits_of_a_request_id() -> None:
    assert to_ref("cle1::v9h4q-1793390239541-fa4d33a7af21") == "33a7af21"
    assert to_ref("0123456789abcdef") == "89abcdef"
    assert to_ref("a-b.c:d") == "abcd"


def test_a_new_turn_id_is_16_hex_characters_and_new_each_time() -> None:
    first, second = new_turn_id(), new_turn_id()
    assert len(first) == 16
    assert set(first) <= HEX
    assert first != second


def test_a_time_in_seconds_is_written_in_whole_milliseconds() -> None:
    assert to_ms(1.2346) == 1235
    assert to_ms(0.0004) == 0


def test_a_server_sent_event_puts_each_line_of_its_data_on_a_data_line_and_ends_with_a_blank_line() -> None:
    assert to_sse_message("one") == "data: one\n\n"
    assert to_sse_message("<li>\n  <p>two</p>\n</li>") == "data: <li>\ndata:   <p>two</p>\ndata: </li>\n\n"
    assert to_sse_message("") == "data: \n\n"


def test_a_server_sent_event_breaks_lines_only_where_the_browser_does() -> None:
    # The browser ends a line at \r\n, \r or \n, and nowhere else: Python's splitlines() would also break at \u2028.
    assert to_sse_message("a\r\nb\rc\nd") == "data: a\ndata: b\ndata: c\ndata: d\n\n"
    assert to_sse_message("keep\u2028this") == "data: keep\u2028this\n\n"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            'HTTP Request: GET https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35 "HTTP/1.1 200 OK"',
            'HTTP Request: GET https://api.open-meteo.com/v1/forecast?... "HTTP/1.1 200 OK"',
        ),
        ("for url 'http://example.test/a?b=1#top'", "for url 'http://example.test/a?...#top'"),
        ("HTTPS://API.OPEN-METEO.COM/v1/forecast?latitude=48.85 x", "HTTPS://API.OPEN-METEO.COM/v1/forecast?... x"),
        ("Failed: https://example.test/runs?id=1: timeout", "Failed: https://example.test/runs?...: timeout"),
        ("a fragment's own ? stays: https://a.test/p#x?y", "a fragment's own ? stays: https://a.test/p#x?y"),
        ("two: https://a.test/?x=1 and https://b.test/p?y=2", "two: https://a.test/?... and https://b.test/p?..."),
        ("no query: https://a.test/path", "no query: https://a.test/path"),
        ("a question? Not an address", "a question? Not an address"),
    ],
)
def test_a_web_address_loses_its_query_string_and_nothing_else_changes(text: str, expected: str) -> None:
    assert to_redacted_urls(text) == expected


def test_cutting_query_strings_takes_linear_time() -> None:
    # A pattern that needed a ? after each address searched the text again from every "http" in it, and one that
    # searched the query lazily, every run of dots: 10,000 schemes in a row took seconds (issue 43).
    started = time.perf_counter()
    assert to_redacted_urls("https://a.test/?" + "." * 50_000 + "x") == "https://a.test/?..."
    assert to_redacted_urls("https://" * 10_000) == "https://" * 10_000
    assert time.perf_counter() - started < 0.5


def test_an_exception_s_frames_are_files_lines_and_functions_innermost_last() -> None:
    def fail() -> None:
        raise ValueError("a private value")

    with pytest.raises(ValueError, match="a private value") as caught:
        fail()
    frames = to_frames(caught.tb)
    assert frames[-1].startswith("unit/test_utils.py:")
    assert frames[-1].endswith(" fail")
    assert frames[-2].endswith(" test_an_exception_s_frames_are_files_lines_and_functions_innermost_last")
    assert all("private" not in frame for frame in frames)


def test_only_an_exception_s_innermost_8_frames_are_kept() -> None:
    def recurse(depth: int) -> None:
        if depth == 0:
            raise ValueError("the deepest call")
        recurse(depth - 1)

    with pytest.raises(ValueError, match="the deepest call") as caught:
        recurse(20)
    frames = to_frames(caught.tb)
    assert len(frames) == 8
    assert all(frame.endswith(" recurse") for frame in frames)
