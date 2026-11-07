"""The competition gate grades structured outcomes at offline production boundaries and exposes only public case IDs."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx2
import pytest
from pydantic import ValidationError

from nimbus.prompts import to_messages
from tools import harness_recordings, harness_replay
from tools.harness_replay import IntakeCase, matrix_cases, replay_cases, run_intake_case


def test_matrix_exercises_seven_local_weekdays_in_four_zones_and_both_midnight_calendars() -> None:
    cases = matrix_cases()
    assert len(cases) == len({case.case_id for case in cases})
    for prefix in ("typo-zion", "yosemite-next", "polite-city", "driving", "home-by-three", "typed-park"):
        group = [case for case in cases if case.case_id.startswith(prefix + "-")]
        assert len(group) == 7 * 4
    friday = next(case for case in cases if case.case_id == "typo-zion-lax-fri")
    assert friday.now.astimezone(ZoneInfo("America/Los_Angeles")).date() == date(2026, 11, 6)
    assert friday.now.astimezone(ZoneInfo("America/Denver")).date() == date(2026, 11, 7)
    saturday = next(case for case in cases if case.case_id == "typo-zion-lax-sat")
    assert saturday.expected.weekend_options == (("2026-11-07", "2026-11-08"), ("2026-11-13", "2026-11-15"))


def test_replay_passes_without_live_http_and_includes_the_reviewed_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = []

    async def live_http(*_: Any, **__: Any) -> Any:
        attempts.append("unexpected upstream")
        raise AssertionError("Replay tried to use a network transport")

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", live_http)
    rows = replay_cases()
    assert not attempts
    assert {"dallas-trip-intake", "dallas-trip-date-follow-up", "missing-hotel-dates"} <= {
        row["case_id"] for row in rows if row["suite"] == "golden_replay"
    }
    assert [(row["case_id"], row.get("checks")) for row in rows if row["outcome"] != "pass"] == []
    assert {row["suite"] for row in rows} == {"regressions", "weekend", "red_team", "provider_replay", "golden_replay"}
    assert len({(row["suite"], row["case_id"]) for row in rows}) == len(rows)
    assert all(row["duration_ms"] >= 0 for row in rows)


def test_reviewed_failure_yields_field_names_without_storing_question_or_place() -> None:
    case = IntakeCase.model_validate(
        {
            "case_id": "synthetic-deadline",
            "question": "I want to plan a trip to Zion this weekend from Dallas. I need to be back by noon Sunday.",
            "now": "2026-11-05T18:00:00Z",
            "time_zone": "America/Chicago",
            "expected": {"kind": "briefing", "park": "zion", "return_window": "evening"},
        }
    )
    failed = run_intake_case(case)
    assert failed["outcome"] == "expectation_mismatch"
    assert failed["checks"] == ["return_window"]
    assert case.question not in json.dumps(failed)
    assert "Dallas" not in json.dumps(failed)


def test_changed_model_prompt_requires_reviewed_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    def changed(*args: Any, **kwargs: Any) -> Any:
        messages = to_messages(*args, **kwargs)
        messages[0] = messages[0].model_copy(update={"content": "Synthetic change in system policy"})
        return messages

    monkeypatch.setattr(harness_recordings, "to_messages", changed)
    with pytest.raises(harness_recordings.StaleRecordingError):
        asyncio.run(harness_recordings._weather_transcript())


def test_gemini_enum_guard_walks_wrapped_declarations_without_rejecting_empty_defaults() -> None:
    schema = {"anyOf": [{"type": "null"}, {"items": {"enum": ["evening", ""]}}]}
    assert harness_recordings.has_empty_enum({"function_declarations": [{"parameters": {"properties": {"w": schema}}}]})
    assert not harness_recordings.has_empty_enum({"items": {"default": "", "enum": ["morning", "evening"]}})


@pytest.mark.parametrize("change", ["empty", "missing", "duplicate"])
def test_incomplete_matrix_cannot_produce_a_green_scorecard(
    change: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompts = json.loads(harness_replay.MATRIX_PATH.read_bytes())
    changed = [] if change == "empty" else prompts[1:] if change == "missing" else [*prompts, prompts[0]]
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    monkeypatch.setattr(harness_replay, "MATRIX_PATH", path)
    with pytest.raises(ValueError, match="scenario family"):
        matrix_cases()


@pytest.mark.parametrize(
    ("key", "invalid"), [("now", "2026-11-01"), ("time_zone", "../../private"), ("case_id", "../case")]
)
def test_reviewed_cases_require_portable_ids_local_calendar_and_aware_clock(key: str, invalid: str) -> None:
    valid = matrix_cases()[0].model_dump()
    with pytest.raises(ValidationError):
        IntakeCase.model_validate({**valid, key: invalid})
