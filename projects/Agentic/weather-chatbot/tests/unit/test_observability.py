"""
tests/unit/test_observability.py: the Observability pages (step 14), through the app, with Axiom played back. Without
the query token, each says Axiom isn't connected, and asks nothing. With it: Activity's lines in words, by day, never a
field its query doesn't name, a filter at a time, one we don't have a 404; Performance's numbers added up; Evaluations'
golden questions and their last run, and how live answers ended; Health's checks now, its days, and our MCP server.
Each query over the dataset and the last 7 days, once a minute on each copy; a page that answered kept a minute by the
CDN, one that didn't never kept, without Axiom's words; a refused token at error once on each copy, then a warning.
"""

import html
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from markupsafe import escape
from pydantic import SecretStr
from starlette.datastructures import State
from structlog.testing import capture_logs

from nimbus import observability
from nimbus.axiom_query import AxiomQuery
from nimbus.config import Settings
from nimbus.constants import NO_STORE, OBSERVABILITY_CACHE_CONTROL
from nimbus.errors import AXIOM_NOT_CONNECTED, AXIOM_UNANSWERED
from nimbus.goldens import GoldenResult, LastRun, read_goldens, read_last_run
from nimbus.observability import (
    ACTIVITY_FIELDS,
    ACTIVITY_FILTERS,
    WEATHER_ANSWERS,
    make_axiom_query,
    to_activity_line,
    to_count,
    to_duration,
    to_named,
    to_share,
)
from tests.fakes import AXIOM_WORDS, AxiomRecordings, OpenMeteoRecordings

PAGES = ["/activity", "/performance", "/evaluations", "/health"]
TOKEN = SecretStr("xaat-query-test")
LOCAL_MCP = "http://127.0.0.1:8000/api/mcp"


@pytest.fixture
def axiom() -> AxiomRecordings:
    """Axiom's query door, played back with the recorded rows."""
    return AxiomRecordings()


@pytest.fixture
def observed(client: TestClient, settings: Settings, axiom: AxiomRecordings) -> TestClient:
    """The app with Axiom's query token and dataset, asking Axiom played back; its MCP server at a local name."""
    app = cast(FastAPI, client.app)
    app.state.settings = settings.model_copy(update={"axiom_query_token": TOKEN, "axiom_dataset": "weather-chatbot"})
    app.state.axiom_query = AxiomQuery(TOKEN, lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(axiom)))
    app.state.to_mcp_url = lambda _request, _settings: LOCAL_MCP
    return client


def state_of(client: TestClient) -> State:
    """The state of the app the client calls."""
    return cast(FastAPI, client.app).state


def text_of(page: str) -> str:
    """A page's words, its tags gone, its characters unescaped and its spaces made one, as a visitor reads them."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.mark.parametrize("path", PAGES)
def test_without_the_query_token_each_page_says_axiom_isnt_connected_and_asks_nothing(
    client: TestClient, path: str
) -> None:
    assert state_of(client).axiom_query is None
    page = client.get(path)
    assert page.status_code == 200
    notice = page.text.split('class="obs-notice"', 1)[1].split("</p>", 1)[0]
    assert str(escape(AXIOM_NOT_CONNECTED)) in notice
    assert '<a href="/waiting-on-you">Waiting on you</a>' in notice
    assert page.headers["cache-control"] == NO_STORE
    assert f'href="{path}" aria-current="page"' in page.text


def test_activity_shows_each_line_in_words_by_day_the_latest_first(observed: TestClient) -> None:
    words = text_of(observed.get("/activity").text)
    for said in (
        "Sunday 1 November 2026",
        "Answered in 5.8 s · 2 tool calls · 5,150 tokens in, 96 out 14:05:12",
        "get_forecast on REST · no auth in 412 ms",
        "geocode_location failed on MCP · no auth: UpstreamTimeoutError, after 8.0 s",
        "Question on REST · no auth",
        "Saturday 31 October 2026",
        "Fell back REST · with auth to REST · no auth: AuthError",
        "Health check not answering in 590 ms",
        "Refused question_too_long",
        "Failed ModelBusyError after 1.2 s",
        "Stopped after 2.1 s",
    ):
        assert said in words
    assert words.index("Sunday 1 November 2026") < words.index("Saturday 31 October 2026")
    assert "app.started" not in words


def test_the_filters_are_these_where_clauses_and_all_leaves_out_the_health_checks() -> None:
    chat = '"chat.request", "chat.done", "chat.aborted", "chat.failed", "chat.rejected"'
    assert {
        "all": f'event in ({chat}, "tool.call", "lane.fallback")',
        "questions": f"event in ({chat})",
        "tools": 'event in ("tool.call", "lane.fallback")',
        "health": 'event == "health.done"',
        "errors": (
            f'event in ({chat}, "tool.call", "lane.fallback", "health.done") and (level == "error" '
            'or tostring(status) in ("failed", "down") or event == "lane.fallback")'
        ),
    } == ACTIVITY_FILTERS


def test_a_field_not_every_line_has_is_read_with_its_default_so_a_young_dataset_never_fails(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    observed.get("/activity")
    [apl] = axiom.queries
    assert "lane = column_ifexists('lane', '')" in apl
    assert "fromLane = column_ifexists('fromLane', '')" in apl
    assert "project _time, event, level, " in apl
    assert "isempty(column_ifexists('check', ''))" in " ".join(WEATHER_ANSWERS)


def test_activity_names_only_its_own_fields_and_never_shows_another(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    page = observed.get("/activity")
    assert "never-shown" not in page.text
    [apl] = axiom.queries
    assert apl.endswith(f"| project {', '.join(to_named(name) for name in ACTIVITY_FIELDS)}")
    assert not {"requestId", "path", "questionChars", "historyMessages", "deploymentId"} & set(ACTIVITY_FIELDS)


@pytest.mark.parametrize("show", list(ACTIVITY_FILTERS))
def test_each_filter_asks_its_own_where_and_marks_its_tab(
    observed: TestClient, axiom: AxiomRecordings, show: str
) -> None:
    href = "/activity" if show == "all" else f"/activity?show={show}"
    page = observed.get(href)
    assert page.status_code == 200
    [apl] = axiom.queries
    assert f"| where {ACTIVITY_FILTERS[show]} |" in apl
    assert f'href="{escape(href)}" aria-current="page"' in page.text


def test_a_filter_we_dont_have_is_a_404_and_asks_nothing(observed: TestClient, axiom: AxiomRecordings) -> None:
    page = observed.get("/activity?show=everything")
    assert page.status_code == 404
    assert axiom.requests == []


def test_each_query_is_over_the_dataset_and_the_last_7_days(observed: TestClient, axiom: AxiomRecordings) -> None:
    observed.get("/performance")
    assert len(axiom.requests) == 4
    for request in axiom.requests:
        body = json.loads(request.content)
        assert body["apl"].startswith("['weather-chatbot'] | ")
        start, end = (datetime.fromisoformat(body[name]) for name in ("startTime", "endTime"))
        assert end - start == timedelta(days=7)
        assert abs(datetime.now(UTC) - end) < timedelta(minutes=1)


def test_performance_adds_up_answers_tools_lanes_and_the_cache(observed: TestClient) -> None:
    words = text_of(observed.get("/performance").text)
    for said in (
        "Answers 11 ended well",
        "P50 526 ms half took less",
        "P95 711 ms",
        "P99 719 ms",
        "Tool calls 2.1 an answer",
        "Tokens 5,150 in 96 out, an answer",
        # Each tool: the forecast's 12 calls took 5,220 ms; the place's 12, 2,400 ms; the slowest first.
        "get_forecast 435 ms average · slowest 900 ms 12 calls, 0 failed",
        "geocode_location 200 ms average · slowest 8.0 s 12 calls, 1 failed",
        # Each lane: REST · no auth's 22 calls took 6,520 ms.
        "MCP · no auth 550 ms average · slowest 600 ms 2 calls, 0 failed",
        "REST · no auth 296 ms average · slowest 8.0 s 22 calls, 1 failed",
        "REST · no auth 12",
        "MCP · no auth 3",
        # Open-Meteo's answers: the cache's hits only, never one it couldn't read.
        "From our cache 30",
        "Fetched 10",
    ):
        assert said in words
    assert words.index("get_forecast 435 ms") < words.index("geocode_location 200 ms")
    assert 'value="0.750"' in observed.get("/performance").text


def test_evaluations_shows_each_golden_its_last_run_and_how_answers_ended(
    observed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    goldens = read_goldens()
    results = [GoldenResult(id=golden.id, passed=True, tools=golden.expect.tools, misses=[]) for golden in goldens]
    results[5] = GoldenResult(id=goldens[5].id, passed=False, tools=[], misses=["doesn't say /16 days/"])
    ran_at = datetime(2026, 11, 1, 15, 4, tzinfo=UTC)
    last_run = LastRun(commit="4785bc7", ran_at=ran_at, results=results)
    monkeypatch.setattr(observability, "read_last_run", lambda: last_run)
    words = text_of(observed.get("/evaluations").text)
    assert "The last run: 12 of 13 passed, answered by build 4785bc7, on 01 November 2026, 15:04 UTC" in words
    for golden in goldens:
        assert golden.question in words
    assert "call geocode_location, then get_forecast" in words
    assert "failed: doesn't say /16 days/" in words
    for said in (
        "Answered 11 ended well",
        "Stopped 1",
        "Failed 1",
        "Refused 2",
        "question_too_long 2",
        "ModelBusyError 1",
        "AuthError 3",
    ):
        assert said in words


def test_evaluations_without_a_run_kept_says_how_to_keep_one(
    observed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(observability, "read_last_run", lambda: None)
    words = text_of(observed.get("/evaluations").text)
    assert "No run kept yet" in words
    assert words.count("not run") == len(read_goldens())


def test_a_run_kept_that_cant_be_read_is_as_none_kept_and_says_so(
    observed: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / "last-run.json"
    broken.write_text('{"commit": "x", "results": "<<<<<<< HEAD"}', encoding="utf-8")
    monkeypatch.setattr(observability, "read_last_run", lambda: read_last_run(broken))
    with capture_logs() as lines:
        page = observed.get("/evaluations")
    assert page.status_code == 200
    assert "No run kept yet" in text_of(page.text)
    assert [line["errorClass"] for line in lines if line["event"] == "evals.unreadable"] == ["ValidationError"]


def test_the_run_kept_in_the_repository_reads() -> None:
    last_run = read_last_run()
    if last_run is not None:
        assert {result.id for result in last_run.results} <= {golden.id for golden in read_goldens()}


def test_health_shows_the_checks_now_each_day_and_our_mcp_server(observed: TestClient) -> None:
    page = observed.get("/health")
    words = text_of(page.text)
    for said in (
        "Now: working",
        "Open-Meteo working",
        "Our MCP server working",
        "Apify's REST API off not run",
        "REST · no auth working",
        "MCP · with auth off",
        "Sunday 1 November 39 of 40 passed",
        "Saturday 31 October 12 of 12 passed",
        LOCAL_MCP,
        "geocode_location",
        "get_air_quality",
    ):
        assert said in words
    assert 'id="mcp-server"' in page.text
    assert page.headers["cache-control"] == OBSERVABILITY_CACHE_CONTROL


def test_health_shows_7_days_at_most(observed: TestClient, axiom: AxiomRecordings) -> None:
    days = [{"day": f"2026-10-{day:02}T00:00:00Z", "runs": 10, "down": 0} for day in range(31, 23, -1)]
    axiom.rows = {"bin(_time, 1d)": days}
    words = text_of(observed.get("/health").text)
    assert "Sunday 25 October 10 of 10 passed" in words
    assert "Saturday 24 October" not in words


def test_health_shows_our_mcp_server_at_the_production_address_when_there_is_one(
    observed: TestClient, settings: Settings
) -> None:
    production = settings.model_copy(
        update={"vercel_project_production_url": "nimbus.example", "axiom_query_token": TOKEN, "axiom_dataset": "w"}
    )
    state_of(observed).settings = production
    assert "https://nimbus.example/api/mcp" in observed.get("/health").text


def test_a_health_page_with_a_lane_down_is_never_kept_though_axiom_answered(
    observed: TestClient, open_meteo: OpenMeteoRecordings
) -> None:
    open_meteo.failing = frozenset({"/v1/search"})
    page = observed.get("/health")
    assert "Now: not answering" in text_of(page.text)
    assert "Sunday 1 November 39 of 40 passed" in text_of(page.text)
    assert page.headers["cache-control"] == NO_STORE


@pytest.mark.parametrize("path", PAGES)
def test_a_page_that_answered_is_kept_a_minute_and_one_that_didnt_never(
    observed: TestClient, axiom: AxiomRecordings, path: str
) -> None:
    assert observed.get(path).headers["cache-control"] == OBSERVABILITY_CACHE_CONTROL
    state_of(observed).observability_runs.clear()
    axiom.status = 503
    page = observed.get(path)
    assert page.status_code == 200
    assert page.headers["cache-control"] == NO_STORE
    assert str(escape(AXIOM_UNANSWERED)) in page.text
    assert AXIOM_WORDS not in page.text
    assert "Waiting on you</a>" not in page.text.split("obs-notice", 1)[1].split("</p>", 1)[0]


def test_each_query_runs_once_a_minute_on_each_copy(observed: TestClient, axiom: AxiomRecordings) -> None:
    observed.get("/performance")
    observed.get("/performance")
    assert len(axiom.requests) == 4
    for run in state_of(observed).observability_runs.values():
        run.started -= 61
    observed.get("/performance")
    assert len(axiom.requests) == 8


def test_a_refused_token_is_an_error_once_on_each_copy_whichever_query_meets_it_then_a_warning(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    axiom.status = 401
    with capture_logs() as lines:
        observed.get("/performance")
        observed.get("/activity")
        axiom.status = 200
        state_of(observed).observability_runs.clear()
        observed.get("/activity")
        axiom.status = 401
        state_of(observed).observability_runs.clear()
        observed.get("/activity")
    queried = [line for line in lines if line["event"] == "observability.query"]
    assert [line["log_level"] for line in queried if line["status"] == "failed"] == [
        "error",
        "warning",
        "warning",
        "warning",
        "warning",
        "error",
    ]
    assert {line["code"] for line in queried if line["status"] == "failed"} == {"axiom_refused"}
    assert all(TOKEN.get_secret_value() not in json.dumps(line, default=str) for line in lines)


def test_a_query_failing_beside_others_that_answer_is_an_error_once_then_again_after_it_answers(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    axiom.failing = {"totalMs = sum(ms)": 400}

    def visit() -> None:
        """Performance, a minute after the last visit, so each query runs again."""
        for run in state_of(observed).observability_runs.values():
            run.started -= 61
        observed.get("/performance")

    with capture_logs() as lines:
        visit()
        visit()
        axiom.failing = {}
        visit()
        axiom.failing = {"totalMs = sum(ms)": 400}
        visit()
    failed = [(line["log_level"], line["query"]) for line in lines if line.get("status") == "failed"]
    assert failed == [("error", "tool-calls"), ("warning", "tool-calls"), ("error", "tool-calls")]


def test_the_query_token_and_only_it_asks_axiom(settings: Settings) -> None:
    assert make_axiom_query(settings) is None
    with_token = settings.model_copy(update={"axiom_query_token": TOKEN})
    assert make_axiom_query(with_token) is None
    connected = settings.model_copy(
        update={"axiom_query_token": TOKEN, "axiom_dataset": "weather-chatbot", "axiom_token": SecretStr("xaat-ingest")}
    )
    query = make_axiom_query(connected)
    assert query is not None
    assert query._token is TOKEN


def test_a_query_that_answers_is_one_line_with_its_rows(observed: TestClient) -> None:
    with capture_logs() as lines:
        observed.get("/activity")
    [queried] = [line for line in lines if line["event"] == "observability.query"]
    assert (queried["query"], queried["status"], queried["rows"]) == ("activity-all", "ok", 10)
    assert isinstance(queried["ms"], int)


@pytest.mark.parametrize(
    ("ms", "said"), [(0, "0 ms"), (412.4, "412 ms"), (999, "999 ms"), (1000, "1.0 s"), (5820, "5.8 s")]
)
def test_a_duration_is_milliseconds_under_a_second_else_seconds(ms: float, said: str) -> None:
    assert to_duration(ms) == said


def test_a_count_of_one_is_singular() -> None:
    assert [to_count(n, "tool call") for n in (0, 1, 2, 1234)] == [
        "0 tool calls",
        "1 tool call",
        "2 tool calls",
        "1,234 tool calls",
    ]


def test_a_share_of_nothing_is_none() -> None:
    assert to_share(3, 4) == 0.75
    assert to_share(3, 0) == 0.0


def test_a_line_activity_doesnt_show_or_with_no_time_is_left_out() -> None:
    assert to_activity_line({"_time": "2026-11-01T00:00:00Z", "event": "http.request"}) is None
    assert to_activity_line({"event": "chat.done"}) is None
    assert to_activity_line({"_time": "not a time", "event": "chat.done"}) is None
