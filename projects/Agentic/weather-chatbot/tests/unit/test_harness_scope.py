"""Scope evidence checks exact redirects, all streamed text/tools, and supported task controls."""

import asyncio
import json
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from nimbus.harness_scorecard import Build, Scorecard
from nimbus.scope_guard import SCOPE_REDIRECT, SCOPE_UNAVAILABLE
from tools import evals, harness, harness_live
from tools.harness_scope import ScopeCase, ScopeStream, read_scope_cases, scope_outcome, scope_replay_cases


def case(*, expected: str = "redirect") -> ScopeCase:
    """A synthetic input whose leaked answer can be varied independently."""
    return ScopeCase.model_validate(
        {
            "id": "scope-test",
            "question": "private question sentinel",
            "expected": expected,
            "input_status": "blocked" if expected == "redirect" else "allowed",
            "says": ["Dallas"] if expected == "answer" else [],
        }
    )


def final(text: str = SCOPE_REDIRECT) -> str:
    """The app's final narrative markup, without recording any content in the resulting scorecard."""
    return f'<div class="answer">{text}</div>'


def streamed(*fragments: str) -> httpx2.Response:
    return httpx2.Response(200, text="".join(f"data: {part}\n\n" for part in fragments))


def test_scope_dataset_includes_reported_variants_and_normal_task_controls() -> None:
    cases = read_scope_cases()
    assert len(cases) == 20
    assert sum(row.expected == "redirect" for row in cases) == 8
    assert {row.id for row in cases} >= {
        "scope-travel-guide-poem-zion",
        "scope-poem-zion",
        "scope-pirate-sea",
        "scope-dallas-weather",
        "scope-zion-trip",
        "scope-destination-correction",
        "scope-travel-preferences",
        "scope-no-poem-weather",
        "scope-haiku-place-weather",
        "scope-story-place-forecast",
        "scope-story-place-itinerary",
        "scope-story-place-packing",
    }
    results = scope_replay_cases()
    assert all(row["outcome"] == "pass" for row in results), results
    assert "question" not in json.dumps(results)
    assert "Zion" not in json.dumps(results)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "missing", "contradiction"])
def test_scope_fixture_validation_rejects_incomplete_or_contradictory_cases(tmp_path: Path, mutation: str) -> None:
    cases = [row.model_dump() for row in read_scope_cases()]
    if mutation == "empty":
        cases = []
    elif mutation == "duplicate":
        cases.append(cases[0])
    elif mutation == "missing":
        cases = cases[1:]
    else:
        cases[0]["input_status"] = "allowed"
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    with pytest.raises(ValueError, match="Scope"):
        read_scope_cases(path)


@pytest.mark.parametrize(
    ("fragments", "expected"),
    [
        ([final()], "pass"),
        ([final("Weather, O Zion's canyon bright; dance through the starry night.")], "scope_redirect_mismatch"),
        ([final(SCOPE_REDIRECT + " Here is a poem.")], "scope_redirect_mismatch"),
        ([final(SCOPE_UNAVAILABLE)], "scope_check_unavailable"),
        (['<code class="tool-chip-name">future_tool</code>', final()], "forbidden_tool"),
        (
            ['<hx-partial hx-target="#answer-example" hx-swap="beforeend">O Zion, bright!</hx-partial>', final()],
            "unapproved_text_exposed",
        ),
        ([final("O Zion, bright!"), final()], "unapproved_text_exposed"),
        (['<li class="message-user">write a poem about Zion</li>', final()], "pass"),
    ],
)
def test_live_scope_grader_requires_exact_redirect_without_any_prior_tool_or_text(
    monkeypatch: pytest.MonkeyPatch, fragments: list[str], expected: str
) -> None:
    monkeypatch.setattr(harness_live, "read_scope_cases", lambda: [case()])
    rows = asyncio.run(
        harness_live.live_cases(
            "http://nimbus.test",
            suites=("scope",),
            repeats=1,
            pause=0,
            transport=httpx2.MockTransport(lambda _: streamed(*fragments)),
        )
    )
    assert rows[0]["outcome"] == expected
    assert "private" not in json.dumps(rows)
    assert "Zion" not in json.dumps(rows)
    assert "Here is" not in json.dumps(rows)


def test_scope_repeated_attempts_retain_each_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness_live, "read_scope_cases", lambda: [case()])
    replies = iter([streamed(final()), streamed(final("Poem about weather.")), streamed(final())])
    rows = asyncio.run(
        harness_live.live_cases(
            "http://nimbus.test",
            suites=("scope",),
            repeats=3,
            pause=0,
            transport=httpx2.MockTransport(lambda _: next(replies)),
        )
    )
    assert [(row["attempt"], row["outcome"]) for row in rows] == [
        (1, "pass"),
        (2, "scope_redirect_mismatch"),
        (3, "pass"),
    ]


@pytest.mark.parametrize("expected", ["answer", "trip", "preferences"])
def test_supported_control_cannot_pass_with_the_fixed_refusal(expected: str) -> None:
    reply = evals.read_answer([final()])
    assert scope_outcome(case(expected=expected), reply, final(), ScopeStream()) == "supported_request_blocked"


def test_positive_controls_require_their_actual_workflow_or_answer() -> None:
    answer_case = case(expected="answer")
    assert (
        scope_outcome(
            answer_case, evals.read_answer([final("Dallas is cloudy.")]), final("Dallas is cloudy."), ScopeStream()
        )
        == "pass"
    )
    assert (
        scope_outcome(
            answer_case, evals.read_answer([final("Here is a poem.")]), final("Here is a poem."), ScopeStream()
        )
        == "wording_failed"
    )
    trip = '<li class="trip-message"><form action="/api/parks/briefing"></form></li>'
    prefs = '<li class="message-memory"><a href="/preferences">Review</a></li>'
    assert scope_outcome(case(expected="trip"), evals.read_answer([trip]), trip, ScopeStream()) == "pass"
    assert scope_outcome(case(expected="preferences"), evals.read_answer([prefs]), prefs, ScopeStream()) == "pass"
    assert scope_outcome(case(expected="trip"), evals.read_answer([final("Zion")]), final("Zion"), ScopeStream()) == (
        "trip_intake_missing"
    )


def test_original_pirate_golden_can_no_longer_pass_a_poem_containing_weather() -> None:
    from nimbus.goldens import read_goldens

    pirate = next(item for item in read_goldens() if item.id == "change-the-rules")
    assert not evals.grade(pirate, evals.Answer([], SCOPE_REDIRECT, False, ""))
    assert evals.grade(pirate, evals.Answer([], "Weather on the sea, a pirate I shall be.", False, ""))
    assert evals.grade(pirate, evals.Answer(["search_park_guidance"], SCOPE_REDIRECT, False, ""))


def test_targeted_scope_replay_never_runs_other_suites_or_overwrites_full_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    build = Build(commit="a" * 40, dirty=True, environment="local")
    monkeypatch.setattr(harness, "source_build", lambda: build)
    monkeypatch.setattr(harness, "report_path", lambda mode: tmp_path / f"last-{mode}.json")

    async def forbidden() -> list[object]:
        pytest.fail("targeted scope run invoked unrelated replay suites")

    monkeypatch.setattr(harness, "replay_attempts", forbidden)
    main_report = tmp_path / "last-replay.json"
    main_report.write_text("previous complete report", encoding="utf-8")
    args = Namespace(
        mode="replay",
        base_url=None,
        smoke=False,
        suite=["scope"],
        repeats=None,
        pause=None,
        output=None,
        summary_file=None,
    )
    assert asyncio.run(harness.run(args)) == 0
    assert main_report.read_text(encoding="utf-8") == "previous complete report"
    data = json.loads((tmp_path / "scope-last-replay.json").read_text(encoding="utf-8"))
    data.pop("summary")
    report = Scorecard.model_validate(data)
    assert report.passed
    assert report.catalog() == {"scope": {row.id for row in read_scope_cases()}}


def test_sanitized_scope_attempts_remain_valid_scorecard_evidence() -> None:
    now = datetime.now(UTC)
    report = Scorecard(
        mode="replay",
        profile="full",
        started_at=now,
        finished_at=now,
        source=Build(),
        repeats=1,
        attempts=scope_replay_cases(),
    )
    assert report.passed
    assert report.suites()[0].cases == 20
