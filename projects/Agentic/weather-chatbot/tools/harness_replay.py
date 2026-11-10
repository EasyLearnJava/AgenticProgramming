"""Replay park intake on reviewed clocks and messages. This module never reads settings or calls a model."""

import time
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from nimbus.memory.models import PreferenceProfile
from nimbus.parks import ParkKnowledge
from nimbus.travel.preferences import analyze_with_preferences

ROOT = Path(__file__).resolve().parents[1]
type CaseId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,95}$")]
type Text = Annotated[str, Field(min_length=1, max_length=2000)]
type Park = Literal["zion", "yosemite", "grand-canyon"]
type Kind = Literal["chat", "form", "briefing", "choose_weekend", "choose_park", "other_place"]


class IntakeExpected(BaseModel):
    """Only explicitly supplied fields are graded. An empty string asserts an absent place, date or window."""

    model_config = ConfigDict(extra="forbid")
    kind: Kind
    park: Park | Literal[""] = ""
    origin: str = ""
    arrival: str = ""
    departure: str = ""
    transport: Literal["", "fly", "drive", "skip"] = ""
    depart_window: str = ""
    return_window: str = ""
    skip_flights: bool = False
    skip_hotels: bool = False
    weekend_options: tuple[tuple[str, str], ...] = ()
    candidate_parks: tuple[Park, ...] = ()
    unit_system: Literal["", "metric", "imperial"] = ""
    currency: str = ""
    activity: str = ""


class IntakeCase(BaseModel):
    """A synthetic reviewed example with a frozen instant, an explicit local calendar and its oracle."""

    model_config = ConfigDict(extra="forbid")
    case_id: CaseId
    question: Text
    previous_question: Annotated[str, Field(max_length=2000)] = ""
    now: AwareDatetime
    time_zone: Annotated[str, Field(min_length=1, max_length=80)]
    expected: IntakeExpected
    preferences: PreferenceProfile = Field(default_factory=PreferenceProfile)

    @field_validator("time_zone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("Expected an IANA time zone") from None
        return value


@cache
def park_index() -> ParkKnowledge:
    """Load only the app's compact destination catalog; replay does not contact Qdrant or a model."""
    return ParkKnowledge(ROOT / "data" / "parks" / "catalog.json")


def run_intake_case(case: IntakeCase, *, suite: str = "regressions") -> dict[str, Any]:
    """Return field names on a mismatch, never the visitor's words, tool arguments or their values."""
    started = time.perf_counter()
    expected = case.expected.model_dump(exclude_unset=True)
    checks: list[str] = []
    try:
        intent = analyze_with_preferences(
            case.question, park_index(), case.previous_question, case.now, case.time_zone, case.preferences
        )
        actual: dict[str, Any] = {"kind": "chat"}
        if intent:
            actual = {
                **intent.fields,
                "kind": intent.kind,
                "skip_hotels": intent.skip_hotels,
                "skip_flights": intent.skip_flights,
                "depart_window": intent.depart_window,
                "return_window": intent.return_window,
                "weekend_options": intent.weekend_options,
                "candidate_parks": tuple(sorted(intent.candidate_parks)),
            }
        if "candidate_parks" in expected:
            expected["candidate_parks"] = tuple(sorted(expected["candidate_parks"]))
        checks = [key for key, value in expected.items() if actual.get(key, "") != value]
        outcome = "expectation_mismatch" if checks else "pass"
    except Exception:
        outcome = "execution_error"
    return {
        "suite": suite,
        "case_id": case.case_id,
        "outcome": outcome,
        "duration_ms": round(1000 * (time.perf_counter() - started), 2),
        "checks": checks,
    }


class MatrixPrompt(BaseModel):
    """Date profiles have human-written calendar answers independent of the production date parser."""

    model_config = ConfigDict(extra="forbid")
    case_id: CaseId
    question: Text
    previous_question: str = ""
    profile: Literal["this", "next", "none"]
    expected: IntakeExpected


# Week of Monday 2 November 2026. Even on Sunday there is no same-day overnight stay to offer.
THIS = ("2026-11-06", "2026-11-08")
NEXT = ("2026-11-13", "2026-11-15")
REMAINDER = ("2026-11-07", "2026-11-08")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MATRIX_PATH = ROOT / "evals" / "harness" / "weekend-matrix.json"
REQUIRED_FAMILIES = frozenset(
    {
        "typo-zion",
        "polite-city",
        "yosemite-next",
        "home-by-three",
        "driving",
        "no-quotes",
        "choose-park",
        "typed-park",
        "missing-dates",
        "weather-only",
        "qualified-place",
    }
)
ZONES = (
    ("America/New_York", "PHL", "Philadelphia"),
    ("America/Chicago", "DFW", "Dallas"),
    ("America/Denver", "DEN", "Denver"),
    ("America/Los_Angeles", "LAX", "Los Angeles"),
)


def matrix_cases() -> list[IntakeCase]:
    """Exercise each prompt near local midnight across all seven days, including Friday's origin/park split."""
    prompts = TypeAdapter(list[MatrixPrompt]).validate_json(MATRIX_PATH.read_bytes())
    ids = {prompt.case_id for prompt in prompts}
    if len(ids) != len(prompts) or not ids >= REQUIRED_FAMILIES:
        raise ValueError("Weekend matrix contains duplicate IDs or is missing a required scenario family.")
    cases = []
    for zone, airport, city in ZONES:
        for day in range(2, 9):
            local = datetime(2026, 11, day, 23, 30, tzinfo=ZoneInfo(zone))
            for prompt in prompts:
                values = {"airport": airport, "city": city}
                expected = prompt.expected.model_dump(exclude_unset=True)
                if "origin" in expected:
                    expected["origin"] = expected["origin"].format(**values)
                if prompt.profile == "next" or (prompt.profile == "this" and day <= 6):
                    expected["arrival"], expected["departure"] = NEXT if prompt.profile == "next" else THIS
                elif prompt.profile == "this":
                    expected.update(
                        arrival="", departure="", weekend_options=(REMAINDER, NEXT) if day == 7 else (NEXT,)
                    )
                    if expected["kind"] == "briefing":
                        expected["kind"] = "choose_weekend"
                # A known airport overrides a browser abroad. City-only origins use the visitor's browser zone.
                calendar = "UTC" if "{airport}" in prompt.question + prompt.previous_question else zone
                cases.append(
                    IntakeCase(
                        case_id=f"{prompt.case_id}-{airport.lower()}-{WEEKDAYS[local.weekday()]}",
                        question=prompt.question.format(**values),
                        previous_question=prompt.previous_question.format(**values),
                        now=local.astimezone(UTC),
                        time_zone=calendar,
                        expected=IntakeExpected.model_validate(expected),
                    )
                )
    return cases


def replay_cases() -> list[dict[str, Any]]:
    """No model, credentials, live weather or inventory. Reviewed regressions run in the same gate as built-ins."""
    from tools.harness_recordings import recorded_cases
    from tools.harness_review import reviewed_cases

    rows = [run_intake_case(case, suite="weekend") for case in matrix_cases()]
    memory_cases = TypeAdapter(list[IntakeCase]).validate_json(
        (ROOT / "evals/harness/memory-defaults.json").read_bytes()
    )
    if len(memory_cases) != 6 or len({case.case_id for case in memory_cases}) != 6:
        raise ValueError("Memory regression catalog is missing scenarios or contains duplicate IDs.")
    rows.extend(run_intake_case(case, suite="golden_replay") for case in memory_cases)
    rows.extend(recorded_cases())
    rows.extend(run_intake_case(case) for case in reviewed_cases())
    return rows
