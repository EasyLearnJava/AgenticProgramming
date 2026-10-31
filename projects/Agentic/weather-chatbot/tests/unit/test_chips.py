"""
tests/unit/test_chips.py: a tool call as its chip shows it: running, done, failed or stopped; its input in a few words;
once done, its lane, host and time, and the request as it went out; a failure as our own sentence, never another's.
"""

import json
from dataclasses import replace

import pytest

from nimbus.answer import ToolEnded, ToolStarted
from nimbus.chips import ToolChip, to_duration_text, to_input_summary
from nimbus.errors import TOOL_MISUSED, WEATHER_TOO_SLOW
from nimbus.open_meteo import WireRequest
from nimbus.tools import ToolCallRecord

REQUEST = WireRequest(
    method="GET",
    url="https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json",
    headers={"accept": "application/json"},
)
RECORD = ToolCallRecord("rest-no-auth", REQUEST, 312, "Paris, Île-de-France Region, FR · 48.85, 2.35")


def started() -> ToolChip:
    """The geocoding's chip, as the model asked for it."""
    return ToolChip.start(0, ToolStarted("call-0-0", "geocode_location", {"query": "Paris"}))


def test_a_running_chip_shows_its_tool_and_input() -> None:
    chip = started()
    assert (chip.status, chip.mark, chip.word, chip.name) == ("running", "…", "Running", "geocode_location")
    assert (chip.input_summary, chip.lane_line, chip.output_json) == ("“Paris”", None, None)
    assert json.loads(chip.input_json) == {"query": "Paris"}


def test_a_done_chip_shows_its_lane_host_time_and_output() -> None:
    chip = started()
    chip.end(ToolEnded("call-0-0", "geocode_location", '{"candidates": [], "is_ambiguous": false}', RECORD, False))
    assert (chip.status, chip.mark, chip.word) == ("done", "✓", "Done")
    assert chip.lane_line == "REST · no auth · geocoding-api.open-meteo.com · 0.3 s"
    assert chip.output_json == '{\n  "candidates": [],\n  "is_ambiguous": false\n}'


@pytest.mark.parametrize(
    ("content", "shown"),
    [
        (WEATHER_TOO_SLOW, WEATHER_TOO_SLOW),
        ("1 validation error for GeocodeInput query String should have at least 1 character", TOOL_MISUSED),
    ],
    ids=["our sentence", "anything else"],
)
def test_a_failed_chip_shows_only_our_own_sentences(content: str, shown: str) -> None:
    chip = started()
    chip.end(ToolEnded("call-0-0", "geocode_location", content, None, True))
    assert (chip.status, chip.mark, chip.error, chip.lane_line) == ("failed", "✗", shown, None)


def test_stopping_marks_a_running_chip_only() -> None:
    running, done = started(), started()
    done.end(ToolEnded("call-0-0", "geocode_location", "{}", RECORD, False))
    running.stop()
    done.stop()
    assert (running.status, running.mark, done.status) == ("stopped", "■", "done")


@pytest.mark.parametrize(
    ("args", "summary"),
    [
        ({"query": "Springfield, MA"}, "“Springfield, MA”"),
        ({"latitude": 48.85341, "longitude": 2.3488, "units": "metric"}, "48.85, 2.35"),
        (
            {"latitude": 48.85341, "longitude": 2.3488, "days": 1, "include_hourly": True, "units": "metric"},
            "48.85, 2.35 · 1 day, hourly",
        ),
        (
            {"latitude": 32.78, "longitude": -96.81, "days": 3, "include_hourly": False, "units": "imperial"},
            "32.78, -96.81 · 3 days · imperial",
        ),
        ({}, ""),
    ],
)
def test_an_input_in_a_few_words(args: dict[str, object], summary: str) -> None:
    assert to_input_summary(args) == summary


@pytest.mark.parametrize(("ms", "text"), [(0, "<0.1 s"), (49, "<0.1 s"), (312, "0.3 s"), (2950, "3.0 s")])
def test_a_call_s_time_to_a_tenth_of_a_second(ms: int, text: str) -> None:
    assert to_duration_text(ms) == text


def test_a_chip_answered_from_the_cache_says_so_before_its_time() -> None:
    chip = started()
    chip.end(ToolEnded("call-0-0", "geocode_location", "{}", replace(RECORD, from_cache=True), False))
    assert chip.lane_line == "REST · no auth · geocoding-api.open-meteo.com · from the cache · 0.3 s"
