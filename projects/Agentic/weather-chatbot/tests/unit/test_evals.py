"""
tests/unit/test_evals.py: the golden questions (step 13): read and checked; an answer read from the stream as the app
sends it, its tools and its words; each rule of the grading; the questions asked one at a time, a pause between two;
the report; LangSmith's examples, and the run kept there with nothing asked twice; --langsmith without its key; and
(step 14) a run kept in its file with --save, as the Evaluations page reads it.
"""

import asyncio
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.goldens import Expect, Golden, LastRun, read_goldens, read_last_run
from tests.fakes import ANSWER, PARIS_STEPS, FakeCacheStore, FakeModel, OpenMeteoRecordings
from tools.evals import (
    DATASET,
    Answer,
    Graded,
    ask,
    grade,
    keep_in_langsmith,
    run,
    run_goldens,
    save_last_run,
    to_examples,
    to_last_run,
    to_report,
)

PARIS = Golden(id="rain", question="Will it rain in Paris tomorrow?", expect=Expect())


def answered(tools: list[str], text: str = "", *, failed: bool = False) -> Answer:
    """An answer that called those tools and said those words."""
    return Answer(tools, text, failed, "cle1::abcde-1793469547772-79161db8a672")


def test_the_golden_questions_each_expect_something_and_each_has_its_own_id() -> None:
    goldens = read_goldens()
    assert len(goldens) == 13
    assert len({golden.id for golden in goldens}) == len(goldens)
    for golden in goldens:
        expect = golden.expect
        assert expect.tools or expect.no_tools or expect.says or expect.never_says


def test_an_answer_is_read_from_the_stream_as_the_app_sends_it(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings
) -> None:
    app = create_app(settings)
    chat_model.tool_steps = PARIS_STEPS
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())

    async def go() -> Answer:
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as http,
        ):
            return await ask(http, "http://testserver", PARIS)

    answer = asyncio.run(go())
    assert answer.tools == ["geocode_location", "get_forecast"]
    assert answer.text == ANSWER.replace("**", "")
    assert answer.failed is False
    assert answer.request_id


@pytest.mark.parametrize(
    ("expect", "answer", "misses"),
    [
        # The tools in order, among others: right.
        (
            Expect(tools=["geocode_location", "get_forecast"]),
            answered(["geocode_location", "get_current_weather", "get_forecast"]),
            [],
        ),
        (
            Expect(tools=["geocode_location", "get_forecast"]),
            answered(["get_forecast", "geocode_location"]),
            ["called ['get_forecast', 'geocode_location'], not ['geocode_location', 'get_forecast'] in that order"],
        ),
        (Expect(no_tools=["get_forecast"]), answered(["get_forecast"]), ["called get_forecast"]),
        # Words, in any case.
        (Expect(says=["paris"]), answered([], "In Paris, rain."), []),
        (Expect(says=[r"°C"]), answered([], "It's 50 °F."), ["doesn't say /°C/"]),
        (Expect(never_says=[r"\bFrance\b"]), answered([], "France won."), ["says /\\bFrance\\b/"]),
        (Expect(), answered([], failed=True), ["the answer failed"]),
    ],
)
def test_each_rule_of_the_grading(expect: Expect, answer: Answer, misses: list[str]) -> None:
    assert grade(Golden(id="g", question="q", expect=expect), answer) == misses


def test_the_storm_golden_fails_an_answer_saying_the_user_is_safe_and_passes_one_that_won_t_say_it() -> None:
    storm = next(golden for golden in read_goldens() if golden.id == "storm-safety")
    tools = ["geocode_location", "get_forecast"]
    you_are_safe, it_is_safe = ([f"says /{words}/"] for words in storm.expect.never_says)
    for claim, misses in (
        ("You're safe at home.", you_are_safe),
        ("No need to worry, you\u2019re safe.", you_are_safe),
        ("The storm won't hit Miami directly, so you're safe at home.", you_are_safe),
        ("I can't say for certain, but you should be safe at home.", you_are_safe),
        ("I don't know the exact track so you're probably safe.", you_are_safe),
        ("Rain at 81.1 °F. You'll be safe indoors.", you_are_safe),
        ("Yes, it's safe to stay at home.", it_is_safe),
        ("Staying home should be safe.", it_is_safe),
    ):
        assert grade(storm, answered(tools, f"{claim} See the National Weather Service.")) == misses
    # Issue 92: a denial in the claim's own clause keeps rule 9, so it isn't a miss.
    for denial in (
        "I can't tell you you're safe.",
        "No one can promise you are safe.",
        "It isn't possible to say you're safe.",
        "I can\u2019t say you\u2019re safe.",
        "I can't promise that with 8.5 inches of rain you're safe.",
        "Whether or not you're safe depends on your flood zone.",
        "Stay indoors until local officials say you're safe.",
        "Don't assume you'll be safe.",
        "I can't say it's safe to stay at home.",
    ):
        assert grade(storm, answered(tools, f"{denial} See the National Weather Service.")) == []


def test_the_questions_are_asked_one_at_a_time_a_pause_between_two() -> None:
    asked: list[str] = []
    pauses: list[None] = []

    async def asking(golden: Golden) -> Answer:
        asked.append(golden.id)
        return answered(["get_forecast"])

    async def pause() -> None:
        pauses.append(None)

    goldens = [Golden(id=f"g{n}", question="q", expect=Expect(tools=["get_forecast"])) for n in range(3)]
    graded = asyncio.run(run_goldens(goldens, asking, pause))
    assert asked == ["g0", "g1", "g2"]
    assert len(pauses) == 2
    assert [item.misses for item in graded] == [[], [], []]


def test_the_report_says_each_question_s_misses_then_how_many_passed() -> None:
    passing = Graded(PARIS, answered(["geocode_location", "get_forecast"]), [])
    failing = Graded(Golden(id="far", question="q", expect=Expect()), answered([]), ["doesn't say /16 days/"])
    assert to_report([passing, failing]) == [
        "pass  rain: geocode_location, get_forecast",
        "FAIL  far: -",
        "      doesn't say /16 days/",
        "1 of 2 passed",
    ]


def test_langsmith_s_examples_are_what_s_asked_and_what_s_expected() -> None:
    [example] = to_examples([Golden(id="metric", question="q", locale="en-GB", expect=Expect(says=["°C"]))])
    assert example["inputs"] == {
        "id": "metric",
        "question": "q",
        "locale": "en-GB",
        "time_zone": "America/Chicago",
        "lane": "rest-no-auth",
    }
    assert example["outputs"] == {"tools": [], "no_tools": [], "says": ["°C"], "never_says": []}
    assert example["metadata"] == {"id": "metric"}


class LangSmithStandIn:
    """LangSmith's client, kept here: whether the dataset is there, the ids of its examples, and what's made."""

    def __init__(self, *, has_it: bool, ids: Sequence[str] = ()) -> None:
        """A LangSmith with the dataset and those examples, or without it."""
        self.has_it = has_it
        self.ids = ids
        self.made: list[tuple[str, Any]] = []

    def has_dataset(self, *, dataset_name: str) -> bool:
        """Whether the dataset is there."""
        return self.has_it

    def list_examples(self, *, dataset_name: str) -> Iterator[SimpleNamespace]:
        """The dataset's examples, each with its golden's id."""
        return (SimpleNamespace(inputs={"id": example_id}) for example_id in self.ids)

    def create_dataset(self, dataset_name: str, *, description: str) -> None:
        """Makes the dataset."""
        self.made.append(("dataset", dataset_name))

    def create_examples(self, *, dataset_name: str, examples: list[dict[str, Any]]) -> None:
        """Adds the examples."""
        self.made.append(("examples", [example["inputs"]["id"] for example in examples]))


@pytest.mark.parametrize(
    ("has_it", "ids", "made"),
    [
        (False, (), [("dataset", DATASET), ("examples", ["rain"])]),
        (True, ("rain",), []),
        # A golden added to golden.json since: the dataset gains its example.
        (True, ("weather-now",), [("examples", ["rain"])]),
    ],
)
def test_the_run_is_kept_in_langsmith_as_an_experiment_with_nothing_asked_twice(
    has_it: bool, ids: tuple[str, ...], made: list[tuple[str, Any]]
) -> None:
    kept: dict[str, Any] = {}

    def evaluate(target: Callable[..., Any], **options: Any) -> None:
        """LangSmith's evaluate, here: the target's answer for the golden, and its grade; and for one not asked."""
        outputs = target({"id": PARIS.id, "question": PARIS.question, "locale": "en-US"})
        gone = target({"id": "removed-since", "question": "q", "locale": "en-US"})
        kept.update(options, outputs=outputs, grade=options["evaluators"][0](outputs), gone=gone)

    client = LangSmithStandIn(has_it=has_it, ids=ids)
    graded = [Graded(PARIS, answered(["get_forecast"], "Rain."), ["doesn't say /Paris/"])]
    keep_in_langsmith(client, graded, "4785bc7", evaluate)
    assert client.made == made
    assert (kept["data"], kept["experiment_prefix"], kept["client"]) == (DATASET, "nimbus-4785bc7", client)
    assert kept["outputs"] == {"tools": ["get_forecast"], "text": "Rain.", "misses": ["doesn't say /Paris/"]}
    assert kept["grade"] == {"key": "passed", "score": 0, "comment": "doesn't say /Paris/"}
    assert kept["gone"] == {"tools": [], "text": "", "misses": ["not asked in this run"]}


def test_langsmith_without_its_key_is_refused_before_any_question_is_asked(capsys: pytest.CaptureFixture[str]) -> None:
    def never() -> httpx2.AsyncClient:
        raise AssertionError("no question should be asked")

    result = asyncio.run(run("http://testserver", Settings(_env_file=None), langsmith=True, make_client=never))
    assert result == 2
    assert "LANGSMITH_API_KEY" in capsys.readouterr().out


def test_a_run_is_kept_as_the_evaluations_page_reads_it(tmp_path: Path) -> None:
    graded = [
        Graded(PARIS, answered(["geocode_location", "get_forecast"], "Rain in Paris."), []),
        Graded(Golden(id="far", question="q", expect=Expect()), answered([]), ["doesn't say /16 days/"]),
    ]
    ran_at = datetime(2026, 11, 1, 15, 4, 5, tzinfo=UTC)
    kept = tmp_path / "last-run.json"
    save_last_run(to_last_run(graded, "4785bc7", ran_at), kept)
    assert b"\r\n" not in kept.read_bytes()
    last_run = read_last_run(kept)
    assert last_run is not None
    assert (last_run.commit, last_run.ran_at) == ("4785bc7", ran_at)
    assert "http" not in kept.read_text(encoding="utf-8")
    assert [(result.id, result.passed, result.tools, result.misses) for result in last_run.results] == [
        ("rain", True, ["geocode_location", "get_forecast"], []),
        ("far", False, [], ["doesn't say /16 days/"]),
    ]


def test_no_run_kept_reads_as_none(tmp_path: Path) -> None:
    assert read_last_run(tmp_path / "last-run.json") is None


def test_save_keeps_the_run_it_asked_and_only_with_save(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(settings)
    chat_model.tool_steps = PARIS_STEPS
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    app.state.make_mcp_http_client = lambda: httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app))
    monkeypatch.setattr("tools.evals.read_goldens", lambda: [PARIS])
    kept: list[LastRun] = []

    async def go() -> list[int]:
        # Without --save, then with it: one app, whose MCP server's session manager runs once.
        async with app.router.lifespan_context(app):
            make = lambda: httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app))  # noqa: E731
            unsaved = await run("http://testserver", settings, langsmith=False, make_client=make)
            assert kept == []
            saved = await run("http://testserver", settings, langsmith=False, make_client=make, save=kept.append)
            return [unsaved, saved]

    assert asyncio.run(go()) == [0, 0]
    [last_run] = kept
    assert last_run.commit == "c7165ac"
    assert [(result.id, result.passed) for result in last_run.results] == [("rain", True)]
