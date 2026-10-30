"""tests/unit/test_utils.py: the shared helpers: request ids and times."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from nimbus.utils import new_request_id, to_iso, to_request_id

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
