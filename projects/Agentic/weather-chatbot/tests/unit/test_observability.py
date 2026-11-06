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
from datetime import UTC, date, datetime, timedelta
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
from nimbus.axiom_query import AxiomQuery, Row
from nimbus.config import Settings
from nimbus.constants import NO_STORE, OBSERVABILITY_CACHE_CONTROL
from nimbus.errors import AXIOM_NOT_CONNECTED, AXIOM_UNANSWERED
from nimbus.goldens import GoldenResult, LastRun, read_goldens, read_last_run
from nimbus.observability import (
    ACTIVITY_VIEWS,
    TIMELINE_EVENTS,
    TIMELINE_FIELDS,
    WEATHER_ANSWERS,
    make_axiom_query,
    to_activity_line,
    to_activity_requests,
    to_count,
    to_duration,
    to_named,
    to_request_ids,
    to_share,
    to_window,
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


def test_activity_shows_each_request_as_a_row_that_opens_onto_its_timeline_by_day_the_latest_first(
    observed: TestClient,
) -> None:
    page = observed.get("/activity")
    words = text_of(page.text)
    for said in (
        # Each request's row: how it ended, and the lane it was asked on; an answer that came despite a line that
        # went wrong says how many did.
        "Sunday 1 November 2026",
        "Answered in 5.8 s · 2 tool calls · 5,150 tokens in, 96 out · on REST · no auth 14:05:06",
        "Failed ModelBusyError (ClientError) after 9.5 s · on MCP · no auth 13:00:00",
        "Saturday 31 October 2026",
        "Answered in 4.2 s · 1 tool call · 4,000 tokens in, 80 out · on REST · with auth · 2 lines went wrong 09:00:00",
        "Health check not answering in 590 ms: Apify's MCP server (UpstreamTimeoutError) 08:00:00",
        "Refused question_too_long 07:00:00",
        "Stopped after 2.1 s · on REST · no auth 05:00:00",
        # And its timeline: every line of its own, each with its time since the first.
        "+0 ms Question on REST · no auth",
        "+1.1 s Open-Meteo from our cache in 28 ms",
        "+1.2 s geocode_location on REST · no auth in 30 ms",
        "+4.5 s Open-Meteo fetched in 380 ms, 2 tries",
        "+4.6 s get_forecast on REST · no auth in 412 ms",
        "+6.0 s Answered in 5.8 s",
        "+6.0 s Request ended 200 in 5.8 s",
        "Ref 0a1b2c3d",
        "+8.3 s geocode_location failed on MCP · no auth: UpstreamTimeoutError, after 8.0 s",
        "+300 ms Apify failed: AuthError, after 300 ms",
        "+310 ms Fell back REST · with auth to REST · no auth: AuthError",
        "+0 ms Apify's REST API check working in 150 ms",
        "+440 ms Apify's MCP server check not answering: UpstreamTimeoutError, after 590 ms",
        "+441 ms Health check not answering in 590 ms",
        "+450 ms Request ended 503 in 600 ms",
        "+3 ms Request ended 422 in 3 ms",
    ):
        assert said in words
    assert words.index("Sunday 1 November 2026") < words.index("Saturday 31 October 2026")
    assert words.index("+250 ms Open-Meteo fetched in 400 ms") < words.index(
        "+270 ms Open-Meteo check working in 420 ms"
    )
    assert page.text.count('<details class="obs-details">') == 6
    assert page.text.count('<summary class="obs-line" data-tone="warn">') == 2
    assert "observability.query" not in words


def test_activity_asks_for_the_requests_then_their_lines_never_an_id_that_isnt_one(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    observed.get("/activity")
    picked, lines = axiom.queries
    assert picked.endswith(
        f"| where isnotempty(requestId) and ({ACTIVITY_VIEWS['questions']}) | summarize started = min(_time) "
        "by requestId | sort by started desc | take 50"
    )
    ids = '"cle1::iad1::never-shown-0a1b2c3d", "iad1::mcp-11112222", "iad1::fallback-77778888", '
    assert f"| where requestId in ({ids}" in lines
    assert '"iad1::no-lines-bbbbcccc") and event in ("chat.request", ' in lines
    assert "or true" not in lines
    assert "| sort by _time desc | take 2000 | project _time, requestId, event, level, status, ms, " in lines


def test_a_view_with_no_requests_asks_once_and_says_so(observed: TestClient, axiom: AxiomRecordings) -> None:
    axiom.rows = {}
    page = observed.get("/activity?show=errors")
    assert len(axiom.requests) == 1
    assert "No requests in the last 7 days." in text_of(page.text)
    assert page.headers["cache-control"] == OBSERVABILITY_CACHE_CONTROL


def test_the_views_are_these_where_clauses_and_health_runs_have_their_own() -> None:
    events = ", ".join(f'"{event}"' for event in TIMELINE_EVENTS)
    assert {
        "questions": 'event in ("chat.request", "chat.rejected")',
        "errors": (
            f'event in ({events}) and (level == "error" or tostring(status) in ("failed", "down") '
            'or event == "lane.fallback" or (event in ("nps.alerts", "nws.alerts") and tostring(status) == "partial") '
            'or (event == "travel.call" and tostring(status) !in ("found", "no_results", "disabled")) '
            "or (event == \"travel.plan\" and toint(column_ifexists('failedSections', 0)) > 0))"
        ),
        "health": 'event == "health.done"',
        "feedback": 'event == "answer.feedback"',
    } == ACTIVITY_VIEWS
    assert {"health.check", "health.done", "http.request", "upstream.http", "lane.fallback"} <= set(TIMELINE_EVENTS)


def test_a_field_not_every_line_has_is_read_with_its_default_so_a_young_dataset_never_fails(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    observed.get("/activity")
    _picked, lines = axiom.queries
    assert "lane = column_ifexists('lane', '')" in lines
    assert "fromLane = column_ifexists('fromLane', '')" in lines
    assert "project _time, requestId, event, level, status, ms, lane = " in lines
    assert "isempty(column_ifexists('check', ''))" in " ".join(WEATHER_ANSWERS)


def test_a_timeline_names_only_its_own_fields_and_shows_a_request_only_by_its_ref(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    page = observed.get("/activity")
    assert "never-shown" not in page.text
    assert "Ref 0a1b2c3d" in text_of(page.text)
    _picked, lines = axiom.queries
    assert lines.endswith(f"| project {', '.join(to_named(name) for name in TIMELINE_FIELDS)}")
    never = {"path", "host", "method", "questionChars", "historyMessages", "answerChars", "deploymentId", "model"}
    assert not never & set(TIMELINE_FIELDS)


@pytest.mark.parametrize("show", list(ACTIVITY_VIEWS))
def test_each_view_asks_its_own_where_and_marks_its_tab(
    observed: TestClient, axiom: AxiomRecordings, show: str
) -> None:
    href = "/activity" if show == "questions" else f"/activity?show={show}"
    page = observed.get(href)
    assert page.status_code == 200
    assert f"| where isnotempty(requestId) and ({ACTIVITY_VIEWS[show]}) | summarize started" in axiom.queries[0]
    assert f'href="{escape(href)}" aria-current="page"' in page.text


@pytest.mark.parametrize(
    ("address", "words", "where"),
    [
        (
            "/activity?tool=get_forecast",
            "Questions that called get_forecast",
            'event in ("tool.call", "knowledge.call", "nps.alerts", "nws.alerts", "travel.call", "travel.plan", '
            '"travel.briefing") '
            "and column_ifexists('tool', '') == \"get_forecast\"",
        ),
        (
            "/activity?asked=mcp-no-auth",
            "Questions asked on MCP · no auth",
            "event == \"chat.request\" and column_ifexists('lane', '') == \"mcp-no-auth\"",
        ),
        (
            "/activity?lane=rest-no-auth",
            "Questions whose tools ran on REST · no auth",
            "event == \"tool.call\" and column_ifexists('lane', '') == \"rest-no-auth\"",
        ),
        ("/activity?ended=failed", "Questions failed", 'event == "chat.failed"'),
        (
            "/activity?refused=question_too_long",
            "Questions refused for question_too_long",
            "event == \"chat.rejected\" and column_ifexists('code', '') == \"question_too_long\"",
        ),
        (
            "/activity?failed=AnswerTimeoutError",
            "Questions that failed with AnswerTimeoutError",
            "event == \"chat.failed\" and column_ifexists('errorClass', '') == \"AnswerTimeoutError\"",
        ),
        (
            "/activity?fellback=AuthError",
            "Questions whose forecast fell back after AuthError",
            "event == \"lane.fallback\" and column_ifexists('errorClass', '') == \"AuthError\"",
        ),
    ],
)
def test_each_link_narrows_the_questions_to_its_lines_and_says_so(
    observed: TestClient, axiom: AxiomRecordings, address: str, words: str, where: str
) -> None:
    page = observed.get(address)
    assert page.status_code == 200
    assert f"| where isnotempty(requestId) and ({where}) | summarize started" in axiom.queries[0]
    assert f"{words}. Show them all" in text_of(page.text)
    assert '<a href="/activity">Show them all</a>' in page.text
    assert 'href="/activity" aria-current="page"' in page.text


def test_a_day_narrows_the_requests_to_its_part_of_the_7_days_and_its_views_keep_it(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    today = datetime.now(UTC).date()
    page = observed.get(f"/activity?show=health&day={today.isoformat()}")
    assert page.status_code == 200
    picked, lines = (json.loads(request.content) for request in axiom.requests)
    start, end = (datetime.fromisoformat(picked[name]) for name in ("startTime", "endTime"))
    assert start == datetime(today.year, today.month, today.day, tzinfo=UTC)
    assert abs(datetime.now(UTC) - end) < timedelta(minutes=1)
    assert datetime.fromisoformat(lines["endTime"]) - datetime.fromisoformat(lines["startTime"]) == timedelta(days=7)
    assert f"On {today:%A} {today.day} {today:%B %Y}. Show them all" in text_of(page.text)
    assert f'href="/activity?show=errors&amp;day={today.isoformat()}"' in page.text


def test_a_days_query_answers_only_that_day_though_its_words_are_another_days(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    today = datetime.now(UTC).date()
    observed.get(f"/activity?show=health&day={today.isoformat()}")
    observed.get(f"/activity?show=health&day={(today - timedelta(days=1)).isoformat()}")
    picked = [
        json.loads(request.content) for request in axiom.requests if "summarize started" in request.content.decode()
    ]
    assert len(picked) == 2
    assert picked[0]["apl"] == picked[1]["apl"]
    assert picked[0]["startTime"] != picked[1]["startTime"]


def test_a_day_the_7_days_reach_into_is_their_part_of_it() -> None:
    now = datetime(2026, 11, 2, 18, 30, tzinfo=UTC)
    assert to_window(None, now) == (now - timedelta(days=7), now)
    assert to_window(date(2026, 11, 1), now) == (datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC))
    assert to_window(date(2026, 10, 26), now) == (now - timedelta(days=7), datetime(2026, 10, 27, tzinfo=UTC))
    assert to_window(date(2026, 11, 2), now) == (datetime(2026, 11, 2, tzinfo=UTC), now)


@pytest.mark.parametrize(
    "query",
    [
        "show=everything",
        "show=all",
        "show=tools",
        "tool=get_weather_of_mars",
        "asked=rest-no-tokens",
        "lane=rest-no-tokens",
        "ended=done-ish",
        'refused=x" or true or "',
        "refused=CallUsAt5551234",
        "failed=",
        "fellback=ValueError",
        "tool=get_forecast&lane=rest-no-auth",
        "show=health&tool=get_forecast",
        "day=2 November",
        "day=2026-13-01",
        "day=2020-01-01",
        "day=2999-01-01",
    ],
)
def test_a_view_or_a_link_we_dont_make_is_a_404_and_asks_nothing(
    observed: TestClient, axiom: AxiomRecordings, query: str
) -> None:
    page = observed.get(f"/activity?{query}")
    assert page.status_code == 404
    assert axiom.requests == []


def test_runs_past_their_minute_are_let_go_so_a_timelines_queries_dont_pile_up(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    observed.get("/activity")
    runs = state_of(observed).observability_runs
    assert len(runs) == 2
    for run in runs.values():
        run.started -= 61
    observed.get("/performance")
    assert len(runs) == 4
    assert not any("requestId in" in key for key in runs)


@pytest.mark.parametrize(
    ("row", "said"),
    [
        (
            {"event": "lane.connect", "upstream": "apify", "status": "ok", "ms": 900},
            ("Apify's MCP server", "connected in 900 ms", "ok"),
        ),
        (
            {"event": "lane.connect", "upstream": "apify", "status": "failed", "ms": 50, "errorClass": "AuthError"},
            ("Apify's MCP server", "failed: AuthError, after 50 ms", "bad"),
        ),
        (
            {"event": "upstream.mcp", "upstream": "apify", "status": "ok", "ms": 3600},
            ("Apify's MCP server", "answered in 3.6 s", "ok"),
        ),
        (
            {"event": "upstream.cache", "upstream": "open-meteo", "status": "unreadable"},
            ("Open-Meteo", "our cache's copy was unreadable", "warn"),
        ),
        (
            {"event": "upstream.http", "upstream": "open-meteo", "status": "ok", "ms": 120, "attempts": 1},
            ("Open-Meteo", "fetched in 120 ms", "ok"),
        ),
        (
            {"event": "nws.alerts", "status": "failed", "reason": "timeout", "ms": 5000},
            ("NWS weather alerts", "failed · live fetch · timeout in 5.0 s", "bad"),
        ),
        (
            {"event": "nws.alerts", "status": "partial", "cached": "true", "ms": 1},
            ("NWS weather alerts", "partial · cached result in 1 ms", "warn"),
        ),
        ({"event": "cache.failed", "errorClass": "TimeoutError"}, ("Our cache", "failed: TimeoutError", "warn")),
        ({"event": "http.request", "status": 200, "ms": 12}, ("Request ended", "200 in 12 ms", "ok")),
        ({"event": "http.request", "status": 404, "ms": 2}, ("Request ended", "404 in 2 ms", "warn")),
        ({"event": "http.request", "status": 500, "ms": 2}, ("Request ended", "500 in 2 ms", "bad")),
        (
            {"event": "chat.failed", "errorClass": "AnswerTimeoutError", "ms": 10000},
            ("Failed", "AnswerTimeoutError after 10.0 s", "bad"),
        ),
        # Axiom may send a column that holds numbers and words as words.
        ({"event": "http.request", "status": "200", "ms": 12}, ("Request ended", "200 in 12 ms", "ok")),
        (
            {"event": "mcp.call", "tool": "get_forecast", "status": "ok", "ms": 430},
            ("Our MCP server", "get_forecast in 430 ms", "ok"),
        ),
        (
            {"event": "mcp.call", "tool": "geocode_location", "status": "failed", "ms": 8000, "errorClass": "X"},
            ("Our MCP server", "geocode_location failed: X, after 8.0 s", "bad"),
        ),
        # With too little time left, the forecast fails instead of falling back, though the line is written.
        (
            {"event": "lane.fallback", "fromLane": "rest-with-auth", "toLane": "rest-no-auth", "fellBack": False},
            ("Couldn't fall back", "REST · with auth to REST · no auth, too little time left: ", "bad"),
        ),
    ],
)
def test_each_line_a_timeline_shows_says_what_happened_in_words(row: dict[str, object], said: tuple[str, ...]) -> None:
    line = to_activity_line({"_time": "2026-11-01T00:00:00Z", **row})
    assert line is not None
    assert (line.what, line.detail, line.tone) == said


def test_a_request_with_no_ending_in_its_lines_says_so() -> None:
    rows: list[Row] = [
        {"_time": "2026-11-01T00:00:00Z", "requestId": "iad1::q", "event": "chat.request", "lane": "rest-no-auth"},
        {"_time": "2026-11-01T00:00:01Z", "requestId": "iad1::h", "event": "upstream.http", "status": "ok"},
    ]
    # The latest begun first: the lone line came a second after the question.
    lone, question = to_activity_requests(["iad1::q", "iad1::h"], rows)
    assert (question.summary.what, question.summary.detail) == (
        "Question",
        "on REST · no auth, with no ending in its lines",
    )
    assert (lone.summary.what, lone.summary.detail, lone.summary.tone) == (
        "Request",
        "with no end in its lines",
        "idle",
    )
    assert to_request_ids([{"requestId": "iad1::q"}, {"requestId": "iad1::q"}, {"requestId": ""}]) == ["iad1::q"]


def test_a_call_to_our_mcp_server_is_a_row_of_its_own_by_its_tool_and_says_what_went_wrong() -> None:
    rows: list[Row] = [
        {"_time": "2026-11-01T00:00:00Z", "requestId": "iad1::m", "event": "upstream.http", "status": "failed"},
        {"_time": "2026-11-01T00:00:01Z", "requestId": "iad1::m", "event": "mcp.call", "tool": "get_forecast"},
        {"_time": "2026-11-01T00:00:02Z", "requestId": "iad1::m", "event": "http.request", "status": 200},
    ]
    [call] = to_activity_requests(["iad1::m"], rows)
    assert (call.summary.what, call.summary.tone) == ("Our MCP server", "bad")
    rows[1]["status"] = "ok"
    [call] = to_activity_requests(["iad1::m"], rows)
    assert (call.summary.what, call.summary.detail, call.summary.tone) == (
        "Our MCP server",
        "get_forecast in 0 ms · 1 line went wrong",
        "warn",
    )


def test_at_the_cap_the_oldest_request_found_is_left_out_and_the_page_says_so(
    observed: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(observability, "ACTIVITY_REQUEST_LINES", 27)
    words = text_of(observed.get("/activity").text)
    assert "The latest requests whose lines fit in 27; older ones aren't shown." in words
    assert "Stopped after 2.1 s" not in words
    assert "Refused question_too_long" in words


def test_a_timeline_axiom_couldnt_answer_says_so_and_is_never_kept(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    axiom.failing = {"where requestId in (": 503}
    page = observed.get("/activity")
    assert len(axiom.requests) == 2
    assert str(escape(AXIOM_UNANSWERED)) in page.text
    assert page.headers["cache-control"] == NO_STORE


def test_each_narrowing_and_day_has_a_query_name_of_its_own_so_a_failure_is_its_own(observed: TestClient) -> None:
    today = datetime.now(UTC).date().isoformat()
    with capture_logs() as lines:
        observed.get("/activity?tool=get_forecast")
        observed.get(f"/activity?show=health&day={today}")
    names = [line["query"] for line in lines if line["event"] == "observability.query"]
    # The second timeline names the same requests, so its query's run of a moment ago answers it.
    assert names == ["activity-questions-tool", "activity-lines", "activity-health-day"]


def test_a_narrowed_view_with_no_requests_says_none_like_these(observed: TestClient, axiom: AxiomRecordings) -> None:
    axiom.rows = {}
    assert "None like these." in text_of(observed.get("/activity?tool=get_forecast").text)


def test_the_refusal_codes_a_link_takes_are_the_ones_the_app_writes() -> None:
    written = {
        code
        for path in Path(observability.__file__).parent.glob("*.py")
        for code in re.findall(r'InputError\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))
    }
    assert written == observability.REFUSAL_CODES
    assert {"AnswerTimeoutError", "AuthError", "ObservabilityError"} <= observability.ERROR_CLASSES


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
    assert "The last run: 17 of 18 passed, answered by build 4785bc7, on 01 November 2026, 15:04 UTC" in words
    for golden in goldens:
        assert golden.question in words
    assert "call geocode_location, then get_forecast" in words
    assert "failed: doesn't say /16 days/" in words
    # Step 15: each result opens onto the tools it called.
    assert "passed It called geocode_location, then get_forecast." in words
    assert "failed: doesn't say /16 days/ It called no tool." in words
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


def test_each_row_with_questions_or_health_runs_behind_it_links_to_them_on_activity(
    observed: TestClient, axiom: AxiomRecordings
) -> None:
    performance = observed.get("/performance").text
    assert '<a class="obs-bar-label" id="tools-1" href="/activity?tool=get_forecast">get_forecast</a>' in performance
    assert 'id="lanes-1" href="/activity?lane=mcp-no-auth">MCP · no auth</a>' in performance
    assert 'id="questions-1" href="/activity?asked=rest-no-auth">REST · no auth</a>' in performance
    assert '<span class="obs-bar-label" id="weather-1">From our cache</span>' in performance
    reasons = [
        *axiom.rows["by event, code ="],
        {"event": "chat.rejected", "code": None, "errorClass": None, "lines": 1},
    ]
    axiom.rows = {**axiom.rows, "by event, code =": reasons}
    evaluations = observed.get("/evaluations").text
    for href in (
        "ended=done",
        "ended=aborted",
        "ended=failed",
        "ended=rejected",
        "refused=question_too_long",
        "failed=ModelBusyError",
    ):
        assert f'href="/activity?{href}"' in evaluations
    assert 'href="/activity?fellback=AuthError">AuthError</a>' in evaluations
    assert '<span class="obs-bar-label" id="refusals-2">none given</span>' in evaluations
    health = observed.get("/health").text
    assert 'id="history-1" href="/activity?show=errors&amp;day=2026-11-01">Sunday 1 November</a>' in health


def test_a_name_that_isnt_one_of_ours_gets_no_link() -> None:
    rows = [{"tool": "get_tides", "lane": "rest-by-pigeon", "calls": 1, "failed": 0, "totalMs": 5, "slowestMs": 5}]
    assert [bar.href for bar in observability.to_tool_bars(rows, "tool")] == [""]
    assert [bar.href for bar in observability.to_tool_bars(rows, "lane")] == [""]


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
    picked, timeline = [line for line in lines if line["event"] == "observability.query"]
    assert (picked["query"], picked["status"], picked["rows"]) == ("activity-questions", "ok", 8)
    assert (timeline["query"], timeline["status"], timeline["rows"]) == ("activity-lines", "ok", 27)
    assert isinstance(picked["ms"], int)


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
    assert to_activity_line({"_time": "2026-11-01T00:00:00Z", "event": "observability.query"}) is None
    assert to_activity_line({"event": "chat.done"}) is None
    assert to_activity_line({"_time": "not a time", "event": "chat.done"}) is None
