"""
nimbus/observability.py: the Observability pages (step 14). Activity: the latest requests, a view at a time, each
opening onto its timeline (step 15). Performance: how long answers and tools take, each lane, the cache. Evaluations:
the golden questions' last run, and how live answers end. Health: the checks now, how often they passed, and our MCP
server. Their numbers come from Axiom, asked with a token that can only query, over the last 7 days; each query names
the fields it reads. A request's id is read only to put its lines together, and a page shows only its ref, the 8
characters an error's sentence ends with; never a request's path, or anything a visitor typed, which the lines never
hold anyway (step 11). A row of Performance, Evaluations or Health links to the requests behind it. A page's queries
answer it for a minute on each copy of the app, and Vercel's CDN keeps the page a minute more; a page Axiom couldn't
answer is never kept.
"""

import asyncio
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Container, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Annotated, Final
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.datastructures import State

from nimbus.axiom_query import AxiomQuery, Row
from nimbus.config import Settings
from nimbus.constants import (
    ACTIVITY_REQUEST_LINES,
    ACTIVITY_REQUESTS,
    MCP_PATH,
    NO_STORE,
    OBSERVABILITY_CACHE_CONTROL,
    OBSERVABILITY_DAYS,
    OBSERVABILITY_RUN_SECONDS,
    REQUEST_ID_PATTERN,
)
from nimbus.errors import AXIOM_NOT_CONNECTED, NimbusError, ObservabilityError
from nimbus.feedback import CATEGORIES, TURN_ID
from nimbus.goldens import LastRun, read_goldens, read_last_run
from nimbus.harness_scorecard import public_reports
from nimbus.health import TRAVEL_CHECKS, CheckResult, to_report
from nimbus.lanes import LANES
from nimbus.model import is_tracing_allowed
from nimbus.pages import render_page
from nimbus.retrieval_gate import RetrievalGate
from nimbus.tools import WEATHER_TOOLS
from nimbus.trace_links import resolve_trace_link, trace_url
from nimbus.trace_presenter import present_trace
from nimbus.trace_view import REJECTION_LABELS, TRACE_TOOL_NAMES, TraceView, read_trace
from nimbus.utils import to_ms, to_ref

router = APIRouter()
log = structlog.get_logger()

MS_PER_SECOND = 1000
HTTP_CLIENT_ERROR = 400
HTTP_SERVER_ERROR = 500
ACTIVITY_TIME_ZONE: Final = ZoneInfo("America/Chicago")
LANE_LABELS: Final = {lane.id: lane.label for lane in LANES}
TOOL_NAMES: Final = TRACE_TOOL_NAMES | {
    "retrieval_playground",
    "park_alerts",
    "park_trip_plan",
    "park_trip_briefing",
    "memory_preferences",
}
CHECK_LABELS: Final = {
    "open-meteo": "Open-Meteo geocoding",
    "our-mcp": "Nimbus weather MCP tools",
    "park-index": "Park knowledge index",
    "kiwi-mcp": "Kiwi flight search tools",
    "trivago-mcp": "trivago hotel search tools",
    "apify-rest": "Apify's REST API",
    "apify-mcp": "Apify's MCP server",
}
UPSTREAM_LABELS: Final = {"open-meteo": "Open-Meteo", "apify": "Apify"}
STATUS_WORDS: Final = {"ok": "working", "down": "not answering", "off": "off"}
# The three operations that call Mem0, named once for Activity's rows and their trace links; pause and resume change
# only the browser's own setting, so their rows say nothing of Mem0.
MEM0_LABELS: Final = {
    "read": "Read Preferences (mem0)",
    "save": "Save Preferences (mem0)",
    "forget": "Delete Preferences (mem0)",
}
# A failure that needs a look: Axiom refused our token, or our query. Each is an error once on each copy of the app,
# which reaches Sentry; then a warning, as the health check's (issue 74).
NEEDS_A_LOOK: Final = frozenset({"axiom_refused", "axiom_bad_query"})
# A refused token is one fault, whichever query met it: it's kept by its code, so it reaches Sentry once on each copy,
# not once for each query; a refused query, by the query's name.
TOKEN_FAULTS: Final = frozenset({"axiom_refused"})


# ① The queries: each over the dataset, each naming the fields it reads. _time, requestId, event, level, status and ms
# are on every request's own line (http.request), so the dataset has them once the app has answered once; any other
# comes from rarer lines, which a young dataset may never have had, and Axiom refuses a query that names a field it has
# never seen: those are read through column_ifexists, which gives a default instead. status holds a number on some
# lines (http.request's 200) and words on others, so it's compared as words.
QUESTION_EVENTS: Final = ("chat.request", "chat.done", "chat.aborted", "chat.failed", "chat.rejected")
ENDING_EVENTS: Final = QUESTION_EVENTS[1:]
TOOL_EVENTS: Final = ("tool.call", "lane.fallback")
# What a request's timeline shows (step 15): its question and how it ended; each tool call, and what each asked of
# Open-Meteo, of our cache or of Apify; a fallback; a call our MCP server answered, in that call's own request; a
# health run's checks; and the request's own line, last.
TIMELINE_EVENTS: Final = (
    *QUESTION_EVENTS,
    *TOOL_EVENTS,
    "knowledge.call",
    "memory.operation",
    "semantic_cache.operation",
    "nps.alerts",
    "nws.alerts",
    "travel.call",
    "travel.plan",
    "travel.briefing",
    "travel.section_error",
    "answer.feedback",
    "lane.open.failed",
    "mcp.call",
    "lane.connect",
    "upstream.cache",
    "upstream.http",
    "upstream.mcp",
    "cache.failed",
    "health.check",
    "health.done",
    "http.request",
)
EVERY_LINES_FIELDS: Final = frozenset({"_time", "requestId", "event", "level", "status", "ms"})
STATUS: Final = "tostring(status)"
# The fields a timeline reads: never a path, a host, a question's length or a deployment. The request's id puts the
# lines together, and only its ref is shown.
TIMELINE_FIELDS: Final = (
    "_time",
    "requestId",
    "event",
    "level",
    "status",
    "ms",
    "lane",
    "tool",
    "check",
    "upstream",
    "errorClass",
    "causeClass",
    "code",
    "attempts",
    "toolCalls",
    "tokensIn",
    "tokensOut",
    "fromLane",
    "toLane",
    "fellBack",
    "cached",
    "reason",
    "complete",
    "provider",
    "count",
    "deduplicated",
    "failedSections",
    "missingSections",
    "traceId",
    "category",
    "answerRef",
    "workflow",
    "tripForm",
    "cityTripIntake",
    "hotelDateIntake",
    "forecastHorizon",
    "section",
    "action",
    "memoryIntake",
)


def to_in(name: str, values: Sequence[str]) -> str:
    """An APL test that a field is one of the values, all our own."""
    quoted = ", ".join(f'"{value}"' for value in values)
    return f"{name} in ({quoted})"


def to_field(name: str, default: str = "''") -> str:
    """A field as a query reads it: as it is, if every request's line has it; else its default where it's never been."""
    return name if name in EVERY_LINES_FIELDS else f"column_ifexists('{name}', {default})"


def to_named(name: str) -> str:
    """A field a query reads and gives back under its own name."""
    field = to_field(name)
    return name if field == name else f"{name} = {field}"


# Activity's views (step 15), each a where clause of our own, chosen by name, never written from the address: the lines
# that pick its requests. A question's first line (a refusal comes before the question is taken); any line that went
# wrong, a question's or a health run's; a health run's last line, which every page's dots and every uptime ping add,
# so they have a view of their own.
ACTIVITY_VIEWS: Final[Mapping[str, str]] = {
    "questions": to_in("event", ("chat.request", "chat.rejected")),
    "errors": (
        f'{to_in("event", TIMELINE_EVENTS)} and (level == "error" or {STATUS} in ("failed", "down") '
        f'or event == "lane.fallback" or (event in ("nps.alerts", "nws.alerts") and {STATUS} == "partial") '
        f'or (event == "travel.call" and {STATUS} !in ("found", "no_results", "disabled")) '
        f'or (event == "knowledge.call" and {STATUS} == "unavailable") '
        f'or (event == "nps.alerts" and {STATUS} == "not_configured") '
        f'or (event == "memory.operation" and {STATUS} in ("unavailable", "pending", "conflict")) '
        f'or (event == "semantic_cache.operation" and {STATUS} == "error") '
        f'or event == "travel.section_error" '
        f'or (event in ("travel.plan", "travel.briefing") '
        f"and (toint({to_field('failedSections', '0')}) > 0 or toint({to_field('missingSections', '0')}) > 0)))"
    ),
    "health": 'event == "health.done"',
    "feedback": 'event == "answer.feedback"',
    "memory": (
        f'event == "memory.operation" or (event == "chat.done" and tostring({to_field("memoryIntake")}) == "true")'
    ),
}
ACTIVITY_TABS: Final = (
    ("questions", "Questions"),
    ("errors", "Errors"),
    ("health", "Health"),
    ("feedback", "Feedback"),
    ("memory", "Memory"),
)
DAY_PATTERN: Final = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
NO_REASON: Final = "none given"


def to_error_classes(base: type[Exception]) -> frozenset[str]:
    """The names of an error class and of every class under it."""
    return frozenset({base.__name__}).union(*(to_error_classes(child) for child in base.__subclasses__()))


# A link's narrowings (step 15), each by its name: the values it takes, all ours, checked before anything is asked, so
# a query never holds a visitor's words; the words it says; and the line that picks a question by it. How a question
# ended; the code of each refusal the app writes (each InputError's, a test checks); the class of each error of ours.
ENDED_WORDS: Final = {"done": "answered", "aborted": "stopped", "failed": "failed", "rejected": "refused"}
REFUSAL_CODES: Final = frozenset(
    {
        "body_too_large",
        "form_unreadable",
        "history_too_long",
        "history_unreadable",
        "lane_closed",
        "lane_needs_token",
        "not_a_form",
        "question_empty",
        "question_too_long",
    }
)
ERROR_CLASSES: Final = to_error_classes(NimbusError)
NARROWINGS: Final[Mapping[str, tuple[Container[str], str, str]]] = {
    "tool": (
        TOOL_NAMES,
        "Questions that called {label}",
        to_in(
            "event",
            (
                "tool.call",
                "knowledge.call",
                "nps.alerts",
                "nws.alerts",
                "travel.call",
                "travel.plan",
                "travel.briefing",
                "memory.operation",
            ),
        )
        + f' and {to_field("tool")} == "{{value}}"',
    ),
    "asked": (
        LANE_LABELS,
        "Questions asked on {label}",
        f'event == "chat.request" and {to_field("lane")} == "{{value}}"',
    ),
    "lane": (
        LANE_LABELS,
        "Questions whose tools ran on {label}",
        f'event == "tool.call" and {to_field("lane")} == "{{value}}"',
    ),
    "ended": (ENDED_WORDS, "Questions {label}", 'event == "chat.{value}"'),
    "refused": (
        REFUSAL_CODES,
        "Questions refused for {label}",
        f'event == "chat.rejected" and {to_field("code")} == "{{value}}"',
    ),
    "failed": (
        ERROR_CLASSES,
        "Questions that failed with {label}",
        f'event == "chat.failed" and {to_field("errorClass")} == "{{value}}"',
    ),
    "fellback": (
        ERROR_CLASSES,
        "Questions whose forecast fell back after {label}",
        f'event == "lane.fallback" and {to_field("errorClass")} == "{{value}}"',
    ),
}
# Evaluations' reasons, each event's by the narrowing that finds its questions.
REASON_LINKS: Final = {"chat.rejected": "refused", "chat.failed": "failed", "lane.fallback": "fellback"}
RESPONSE_WORKFLOW: Final = (
    f'case(tostring({to_field("workflow")}) in ("agent", "intake", "briefing", "cached"), '
    f'tostring({to_field("workflow")}), tostring({to_field("tripForm")}) == "false", "briefing", '
    f'tostring({to_field("tripForm")}) == "true" '
    f'or tostring({to_field("cityTripIntake")}) == "true" '
    f'or tostring({to_field("hotelDateIntake")}) == "true" '
    f'or tostring({to_field("forecastHorizon")}) == "true", "intake", '
    f"isnotempty(tostring({to_field('tokensIn')})) or isnotempty(tostring({to_field('tokensOut')})), "
    '"agent", "unknown")'
)
ANSWERS: Final = (
    'where event == "chat.done"',
    f"extend responseWorkflow = {RESPONSE_WORKFLOW}",
    'where responseWorkflow == "agent"',
    "summarize answers = count(), p50 = percentile(ms, 50), p95 = percentile(ms, 95), p99 = percentile(ms, 99), "
    f"avgToolCalls = avg(toint({to_field('toolCalls')})), avgTokensIn = avg(toint({to_field('tokensIn')})), "
    f"avgTokensOut = avg(toint({to_field('tokensOut')}))",
)
WORKFLOWS: Final = (
    'where event == "chat.done"',
    f"extend responseWorkflow = {RESPONSE_WORKFLOW}",
    "summarize responses = count(), p50 = percentile(ms, 50), p95 = percentile(ms, 95) by responseWorkflow",
)
SERVICE_CALLS: Final = (
    'where event in ("knowledge.call", "nps.alerts", "nws.alerts", "travel.call")',
    f"summarize calls = count(), totalMs = sum(ms), slowestMs = max(ms) by event, {to_named('tool')}, "
    f"status = {STATUS}",
)
ENDINGS: Final = (f"where {to_in('event', QUESTION_EVENTS)}", f"summarize lines = count() by event, {to_named('lane')}")
TOOL_CALLS: Final = (
    'where event == "tool.call"',
    f'summarize calls = count(), failed = countif({STATUS} == "failed"), totalMs = sum(ms), slowestMs = max(ms) '
    f"by {to_named('tool')}, {to_named('lane')}",
)
# Open-Meteo's answers to the tools: the health check's own geocoding, which skips the cache, carries its check's name
# (health.py), and is left out.
WEATHER_ANSWERS: Final = (
    f'where event in ("upstream.cache", "upstream.http") and {to_field("upstream")} == "open-meteo" '
    f"and isempty({to_field('check')})",
    f"summarize lines = count() by event, status = {STATUS}",
)
REASONS: Final = (
    f"where {to_in('event', ('chat.rejected', 'chat.failed', 'lane.fallback'))}",
    f"summarize lines = count() by event, {to_named('code')}, {to_named('errorClass')}",
)
HEALTH_DAYS: Final = (
    'where event == "health.done"',
    "extend day = bin(_time, 1d)",
    f'summarize runs = count(), down = countif({STATUS} == "down") by day',
    "sort by day desc",
)


def to_apl(dataset: str, steps: Sequence[str]) -> str:
    """An APL query over the dataset: its steps, each after a pipe."""
    return " | ".join((f"['{dataset}']", *steps))


def to_requests_query(where: str) -> tuple[str, ...]:
    """
    Activity's first query: the latest 50 requests the lines picked belong to, each by its id, the latest first; a
    line written outside any request has no id, and is left out.
    """
    return (
        f"where isnotempty(requestId) and ({where})",
        "summarize started = min(_time) by requestId",
        "sort by started desc",
        f"take {ACTIVITY_REQUESTS}",
    )


def to_timeline_query(request_ids: Sequence[str]) -> tuple[str, ...]:
    """
    Activity's second: every line of those requests a timeline shows, the latest 2,000 if there are more, so a cap
    reached cuts the oldest requests, never the ones shown first; with only its fields. Each is put in order after.
    """
    return (
        f"where {to_in('requestId', request_ids)} and {to_in('event', TIMELINE_EVENTS)}",
        "sort by _time desc",
        f"take {ACTIVITY_REQUEST_LINES}",
        f"project {', '.join(to_named(name) for name in TIMELINE_FIELDS)}",
    )


@dataclass(frozen=True)
class Narrowing:
    """What a link from another page narrows Activity's questions to: its name, its words, and the lines it picks."""

    kind: str
    words: str
    where: str


def to_narrowing(links: Mapping[str, str | None]) -> Narrowing | None:
    """
    The questions a link asks for, by the narrowing it names: those that called a tool, were asked on a lane, had
    their tools run on one, ended one way, were refused for a code, failed with an error, or fell back after one; None
    for all. A value that isn't one of ours, or two narrowings at once, is a 404.
    """
    given = [(kind, value) for kind, value in links.items() if value is not None]
    if not given:
        return None
    if len(given) > 1:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    [(kind, value)] = given
    known, words, where = NARROWINGS[kind]
    if value not in known:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    label = LANE_LABELS.get(value) or ENDED_WORDS.get(value) or value
    if kind == "tool" and value == "park_trip_briefing":
        return Narrowing(kind, "Park trip briefings", where.format(value=value))
    if kind == "tool" and value == "park_trip_plan":
        return Narrowing(kind, "Park trip plans", where.format(value=value))
    if kind == "tool" and value in {"search_flights", "search_hotels"}:
        return Narrowing(kind, f"Travel searches using {value}", where.format(value=value))
    if kind == "tool" and value == "park_alerts":
        return Narrowing(kind, "Park alert checks", where.format(value=value))
    if kind == "tool" and value == "retrieval_playground":
        return Narrowing(kind, "Retrieval Playground runs", where.format(value=value))
    if kind == "tool" and value == "memory_preferences":
        return Narrowing(kind, "Preference memory operations", where.format(value=value))
    return Narrowing(kind, words.format(label=label), where.format(value=value))


def to_day(day: str | None, now: datetime) -> date | None:
    """
    The day a link from Health asks for, in UTC, as YYYY-MM-DD; None for the last 7 days. A day that isn't one, or
    that the 7 days before now don't reach, is a 404.
    """
    if day is None:
        return None
    try:
        found = date.fromisoformat(day) if DAY_PATTERN.fullmatch(day) else None
    except ValueError:
        found = None
    if found is None or not (now - timedelta(days=OBSERVABILITY_DAYS)).date() <= found <= now.date():
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    return found


def to_activity_href(show: str, **narrowed: str | None) -> str:
    """Activity's address for a view and what a link narrows it to, the questions' view without its name."""
    given = {"show": show if show != "questions" else None, **narrowed}
    query = urlencode({name: value for name, value in given.items() if value is not None})
    return f"/activity?{query}" if query else "/activity"


def make_axiom_query(settings: Settings) -> AxiomQuery | None:
    """The way to ask Axiom, when the settings have its query token and the dataset; else None: not connected."""
    if settings.axiom_query_token is None or settings.axiom_dataset is None:
        return None
    return AxiomQuery(settings.axiom_query_token)


# ② Asking: each query once a minute on each copy of the app, its run shared by every request meanwhile.
@dataclass
class QueryRun:
    """A run of one query: when it started, and the task that finds its rows."""

    started: float
    task: asyncio.Task[list[Row]]


def to_window(day: date | None, now: datetime) -> tuple[datetime, datetime]:
    """The time a query looks over: the 7 days before now; or, for a day, the part of it they reach, in UTC."""
    start, end = now - timedelta(days=OBSERVABILITY_DAYS), now
    if day is None:
        return start, end
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return max(start, midnight), min(end, midnight + timedelta(days=1))


async def run_query(state: State, name: str, apl: str, day: date | None) -> list[Row]:
    """
    The query's rows over the last 7 days, or the day's part of them, and one observability.query line: its name, how
    it went, its time; a failure by its class and code, at error when it needs a look and is new on this copy, else a
    warning: a query that keeps failing would send Sentry an event every minute, and use up its free quota. failing
    keeps each query's failure, until it answers; a refused token, once for every query, until any answers.
    """
    axiom: AxiomQuery = state.axiom_query
    failing: dict[str, str] = state.observability_failures
    started = time.perf_counter()
    try:
        rows = await axiom.run(apl, *to_window(day, datetime.now(UTC)))
    except ObservabilityError as error:
        ms = to_ms(time.perf_counter() - started)
        key = error.code if error.code in TOKEN_FAULTS else name
        is_new = failing.get(key) != error.code
        failing[key] = error.code
        write = log.error if error.code in NEEDS_A_LOOK and is_new else log.warning
        write(
            "observability.query", query=name, status="failed", ms=ms, errorClass=type(error).__name__, code=error.code
        )
        raise
    failing.pop(name, None)
    for fault in TOKEN_FAULTS:
        failing.pop(fault, None)
    log.info("observability.query", query=name, status="ok", ms=to_ms(time.perf_counter() - started), rows=len(rows))
    return rows


async def ask(request: Request, name: str, apl: str, day: date | None = None) -> list[Row]:
    """
    The query's rows: from the run of the same query over the same time that started within the last minute on this
    copy of the app, waited for if it's still going; else a new run. A failed run answers for its minute too, so an
    Axiom that's failing isn't asked again at every visit. Runs past their minute are let go first: a timeline's query
    names its requests, so a new one comes every minute.
    """
    state = request.app.state
    runs: dict[str, QueryRun] = state.observability_runs
    now = time.monotonic()
    for old in [key for key, kept in runs.items() if now - kept.started >= OBSERVABILITY_RUN_SECONDS]:
        del runs[old]
    key = apl if day is None else f"{apl} @ {day.isoformat()}"
    run = runs.get(key)
    if run is None or run.task.get_loop() is not asyncio.get_running_loop():
        run = runs[key] = QueryRun(now, asyncio.create_task(run_query(state, name, apl, day)))
    # Shielded: a visitor who goes away doesn't stop the run the others wait for.
    return await asyncio.shield(run.task)


@dataclass(frozen=True)
class Answers:
    """What a page's queries found, by name; or, with none, the sentence that says why."""

    rows: Mapping[str, list[Row]]
    notice: str | None = None

    @property
    def has_no_token(self) -> bool:
        """Whether there are none because this deployment has no token to ask with."""
        return self.notice == AXIOM_NOT_CONNECTED


async def ask_axiom(request: Request, queries: Mapping[str, Sequence[str]], day: date | None = None) -> Answers:
    """
    Each query's rows, all at once, over the last 7 days or a day of them; none, with its sentence, when Axiom isn't
    connected or one query failed.
    """
    state = request.app.state
    dataset = state.settings.axiom_dataset
    if state.axiom_query is None or dataset is None:
        return Answers({}, AXIOM_NOT_CONNECTED)
    names = list(queries)
    found = await asyncio.gather(
        *(ask(request, name, to_apl(dataset, queries[name]), day) for name in names), return_exceptions=True
    )
    failure = next((item for item in found if isinstance(item, BaseException)), None)
    if failure is not None:
        if isinstance(failure, ObservabilityError):
            return Answers({}, failure.user_message)
        raise failure
    return Answers({name: rows for name, rows in zip(names, found, strict=True) if isinstance(rows, list)})


# ③ The rows, read: each field as a number or words, whatever Axiom sent; a duration and a share as a page shows them.
def to_number(row: Row, name: str) -> float:
    """A field's number; 0 when it's missing, or isn't one."""
    value = row.get(name)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def to_words(row: Row, name: str) -> str:
    """A field's words; empty when it's missing."""
    value = row.get(name)
    return "" if value is None else str(value)


def to_moment(row: Row, name: str) -> datetime | None:
    """A field's moment, in UTC; None when it's missing, or isn't one."""
    try:
        return datetime.fromisoformat(to_words(row, name)).astimezone(UTC)
    except ValueError:
        return None


def to_duration(ms: float) -> str:
    """A time as a page shows it: milliseconds under a second, else seconds to a tenth."""
    return f"{round(ms):,} ms" if ms < MS_PER_SECOND else f"{ms / MS_PER_SECOND:.1f} s"


def to_share(part: float, whole: float) -> float:
    """The part's share of the whole, from 0 to 1; 0 of nothing."""
    return part / whole if whole else 0.0


def to_count(count: float, word: str) -> str:
    """A count and its word, the word plural unless the count is one: "1 tool call", "2 tool calls"."""
    whole = round(count)
    return f"{whole:,} {word}{'' if whole == 1 else 's'}"


def to_lane_label(lane_id: str) -> str:
    """A lane's label, from its id; an id we don't know, as it is."""
    return LANE_LABELS.get(lane_id, lane_id)


@dataclass(frozen=True)
class Tile:
    """A number at the top of a page: what it is, its value, and a line under it."""

    label: str
    value: str
    note: str = ""


@dataclass(frozen=True)
class Bar:
    """
    A line of a breakdown: what it is, its value in words, its share of the largest or the whole, a note, and the
    address of the requests behind it on Activity, if it has one (step 15).
    """

    label: str
    value: str
    share: float
    note: str = ""
    href: str = ""


# ④ Activity: each request a row, its timeline under it, each line in words, the requests grouped by day.
@dataclass(frozen=True)
class ActivityLine:
    """One line of a timeline: when, what happened, the rest in words, and how it went: ok, warn, bad or idle."""

    at: datetime
    what: str
    detail: str
    tone: str


def to_question_line(row: Row, at: datetime, event: str, took: str) -> ActivityLine | None:
    """A line about a question and its answer, in words; None for another event."""
    lane, error_class = to_lane_label(to_words(row, "lane")), to_words(row, "errorClass")
    if event == "chat.request":
        return ActivityLine(at, "Question", f"on {lane}", "idle")
    if event == "answer.feedback":
        label = CATEGORIES.get(to_words(row, "category"), "Unrecognized category")
        return ActivityLine(at, "Visitor feedback", label, "idle")
    if event == "chat.done":
        for flag, label in (
            ("cityTripIntake", "City trip clarification"),
            ("hotelDateIntake", "Hotel date clarification"),
            ("forecastHorizon", "Forecast limit explained"),
            ("memoryIntake", "Preference review"),
            ("tripForm", "Trip details requested"),
        ):
            if to_words(row, flag).lower() == "true":
                return ActivityLine(at, label, f"in {took}", "ok")
        workflow = to_words(row, "workflow")
        if workflow == "briefing" or to_words(row, "tripForm").lower() == "false":
            return ActivityLine(at, "Park trip briefing", f"in {took}", "ok")
        if workflow == "intake":
            return ActivityLine(at, "Clarification", f"in {took}", "ok")
        if workflow == "cached":
            return ActivityLine(at, "Cached weather answer", f"in {took} · no model or tool calls", "ok")
        calls = (
            to_count(to_number(row, "toolCalls"), "tool call")
            if isinstance(row.get("toolCalls"), int | float)
            else "tool count unavailable"
        )
        tokens = "token usage unavailable"
        if all(
            isinstance(row.get(name), int | float) and not isinstance(row[name], bool)
            for name in ("tokensIn", "tokensOut")
        ):
            tokens_in, tokens_out = (round(to_number(row, name)) for name in ("tokensIn", "tokensOut"))
            tokens = f"{tokens_in:,} tokens in, {tokens_out:,} out"
        detail = f"in {took} · {calls} · {tokens}"
        return ActivityLine(at, "Answered", detail, "ok")
    if event == "chat.aborted":
        return ActivityLine(at, "Stopped", f"after {took}", "idle")
    if event == "chat.failed":
        cause = to_words(row, "causeClass")
        return ActivityLine(at, "Failed", f"{error_class}{f' ({cause})' if cause else ''} after {took}", "bad")
    if event == "chat.rejected":
        return ActivityLine(at, "Refused", to_words(row, "code"), "warn")
    if event == "tool.call":
        tool = to_words(row, "tool")
        if to_words(row, "status") == "failed":
            return ActivityLine(at, tool, f"failed on {lane}: {error_class}, after {took}", "bad")
        return ActivityLine(at, tool, f"on {lane} in {took}", "ok")
    if event == "travel.briefing":
        status = to_words(row, "status")
        label = {
            "pause": "Pause travel",
            "review": "Review conditions",
            "adapt": "Adjust plans",
            "proceed": "Continue planning",
        }.get(status, "Outcome unavailable")
        missing = to_number(row, "missingSections")
        failed = to_number(row, "failedSections")
        detail = label + (f" · {to_count(missing, 'check')} incomplete" if missing else "")
        tone = "warn" if missing or failed else "ok" if status == "proceed" else "idle"
        return ActivityLine(at, "Park trip conditions", detail, tone)
    if event == "travel.section_error":
        section = to_words(row, "section")
        known = {"weather", "park guidance", "NPS notices", "NWS alerts", "flight", "hotel"}
        label = f"{section} check" if section in known else "Trip check"
        detail = "timed out" if to_words(row, "errorClass") == "TimeoutError" else "unavailable"
        return ActivityLine(at, label, detail, "bad")
    if event == "travel.plan":
        failed = to_number(row, "failedSections")
        missing = to_number(row, "missingSections")
        detail = f"{to_count(missing, 'section')} unavailable, {failed:g} failed"
        return ActivityLine(at, "Park trip plan", detail, "warn" if failed or missing else "ok")
    if event == "travel.call":
        status = to_words(row, "status")
        tone = (
            "ok"
            if status in {"found", "no_results", "ok"}
            else "idle"
            if status == "disabled"
            else "warn"
            if status == "partial"
            else "bad"
        )
        provider = to_words(row, "provider")
        count = to_count(to_number(row, "count"), "offer")
        return ActivityLine(at, to_words(row, "tool"), f"{provider} {status}: {count} in {took}".strip(), tone)
    if event == "knowledge.call":
        status = to_words(row, "status")
        detail = f"{status.replace('_', ' ')} in {took}"
        tone = "bad" if status in {"failed", "unavailable"} else "idle" if status == "cancelled" else "ok"
        return ActivityLine(at, to_words(row, "tool"), detail, tone)
    if event in {"nps.alerts", "nws.alerts"}:
        status = to_words(row, "status")
        source = "cached result" if to_words(row, "cached").lower() == "true" else "live fetch"
        if status in {"not_configured", "unsupported"}:
            source = "not requested"
        reasons = {
            "authentication_failed": "authentication failed",
            "rate_limited": "rate limit",
            "upstream_error": "upstream server error",
            "timeout": "timeout",
            "network_error": "network error",
            "invalid_response": "invalid response",
            "invalid_record": "some records could not be read",
        }
        reason = reasons.get(to_words(row, "reason"), "")
        detail = f"{status.replace('_', ' ')} · {source}{f' · {reason}' if reason else ''} in {took}"
        tone = (
            "bad"
            if status in {"failed", "unavailable"}
            else ("warn" if status in {"not_configured", "partial", "unsupported"} else "ok")
        )
        name = "NWS weather alerts" if event == "nws.alerts" else to_words(row, "tool")
        return ActivityLine(at, name, detail, tone)
    if event == "lane.open.failed":
        return ActivityLine(at, "Weather connection", f"failed on {lane}: {error_class}", "bad")
    if event == "lane.fallback":
        moved = f"{to_lane_label(to_words(row, 'fromLane'))} to {to_lane_label(to_words(row, 'toLane'))}"
        # With too little time left, the line is written and the forecast fails instead (auth_lanes.py).
        if to_words(row, "fellBack").lower() == "false":
            return ActivityLine(at, "Couldn't fall back", f"{moved}, too little time left: {error_class}", "bad")
        return ActivityLine(at, "Fell back", f"{moved}: {error_class}", "warn")
    return None


def to_call_line(row: Row, at: datetime, event: str, took: str) -> ActivityLine | None:
    """A line about a call out (Open-Meteo, our cache, Apify), a health check, or the request's end; None otherwise."""
    status, error_class = to_words(row, "status"), to_words(row, "errorClass")
    upstream = UPSTREAM_LABELS.get(to_words(row, "upstream"), to_words(row, "upstream"))
    failed = f"failed: {error_class}, after {took}"
    if event == "upstream.cache":
        if status == "hit":
            return ActivityLine(at, upstream, f"from our cache in {took}", "ok")
        return ActivityLine(at, upstream, f"our cache's copy was {status}", "warn")
    if event == "upstream.http":
        tries = round(to_number(row, "attempts"))
        again = f", {tries} tries" if tries > 1 else ""
        return ActivityLine(at, upstream, f"fetched in {took}{again}" if status == "ok" else failed, ok_or_bad(status))
    if event in ("upstream.mcp", "lane.connect"):
        what = f"{upstream}'s MCP server"
        done = f"connected in {took}" if event == "lane.connect" else f"answered in {took}"
        return ActivityLine(at, what, done if status == "ok" else failed, ok_or_bad(status))
    if event == "mcp.call":
        tool = to_words(row, "tool")
        detail = f"{tool} in {took}" if status == "ok" else f"{tool} {failed}"
        return ActivityLine(at, "Our MCP server", detail, ok_or_bad(status))
    if event == "cache.failed":
        return ActivityLine(at, "Our cache", f"failed: {error_class}", "warn")
    if event == "health.check":
        detail = f"not answering: {error_class}, after {took}" if status == "down" else f"working in {took}"
        return ActivityLine(at, f"{to_check_label(row)} check", detail, "bad" if status == "down" else "ok")
    if event == "health.done":
        return ActivityLine(at, "Health check", f"{STATUS_WORDS.get(status, status)} in {took}", ok_or_bad(status))
    if event == "http.request":
        # A number on this line, though Axiom may send the column as words, since other lines hold words in it.
        code = round(to_number(row, "status")) or (int(status) if status.isdigit() else 0)
        tone = "bad" if code >= HTTP_SERVER_ERROR else "warn" if code >= HTTP_CLIENT_ERROR else "ok"
        return ActivityLine(at, "Request ended", f"{code} in {took}", tone)
    return None


def ok_or_bad(status: str) -> str:
    """A tone from a status: ok when it's ok, else bad."""
    return "ok" if status == "ok" else "bad"


def to_check_label(row: Row) -> str:
    """A health check's name in words, from its line; a name we don't know, as it is."""
    return CHECK_LABELS.get(to_words(row, "check"), to_words(row, "check"))


def to_activity_line(row: Row) -> ActivityLine | None:
    """A line of a timeline from Axiom's row; None for an event a timeline doesn't show, or one with no time."""
    at = to_moment(row, "_time")
    if at is None:
        return None
    event, took = to_words(row, "event"), to_duration(to_number(row, "ms"))
    if event == "memory.operation":
        return to_memory_line(row, at, took)
    if event == "semantic_cache.operation":
        return to_semantic_cache_line(row, at, took)
    return to_question_line(row, at, event, took) or to_call_line(row, at, event, took)


def to_semantic_cache_line(row: Row, at: datetime, took: str) -> ActivityLine:
    """Allowlist operation metadata; provider errors, questions, scopes and answer contents never become labels."""
    action = to_words(row, "action")
    suffix = f" · {action}" if action in {"lookup", "store", "list"} else ""
    outcomes = {
        "exact_hit": ("Exact match", "ok"),
        "semantic_hit": ("Similar question matched", "ok"),
        "miss": ("No reusable answer", "idle"),
        "bypass": ("Skipped", "idle"),
        "error": ("Unavailable; normal answer flow continues", "warn"),
        "stored": ("Answer saved", "ok"),
        "saved": ("Answer saved", "ok"),
        "not_reusable": ("Answer not reusable", "idle"),
        "cache_full": ("Cache capacity reached", "idle"),
        "timed_out": ("Save timed out; Qdrant may still have saved it", "warn"),
        "shadow_hit": ("Match measured; answer not reused", "idle"),
        "ready": ("Inventory read", "ok"),
        "disabled": ("Disabled", "idle"),
    }
    label, tone = outcomes.get(to_words(row, "status"), ("Outcome unavailable", "warn"))
    reason = {
        "expiry": "expired",
        "context": "context changed",
        "unsafe": "outside cache scope",
        "ineligible": "outside cache scope",
        "timeout": "time limit reached",
        "unavailable": "provider unavailable",
        # Rows logged before each evidence check had its own reason.
        "evidence": "weather evidence was incomplete or unsuitable for reuse",
        "capacity": "cache capacity reached",
        "disabled": "cache is disabled or unconfigured",
        **REJECTION_LABELS,
    }.get(to_words(row, "reason"), "")
    detail = f"{label}{f' · {reason}' if reason else ''} in {took}"
    return ActivityLine(at, f"Weather answer cache{suffix}", detail, tone)


def to_memory_line(row: Row, at: datetime, took: str) -> ActivityLine:
    """Show only approved operation metadata; never echo arbitrary stored values, identities or provider errors."""
    action, status = to_words(row, "action"), to_words(row, "status")
    labels = {**MEM0_LABELS, "pause": "Pause memory", "resume": "Resume memory"}
    outcomes = {
        ("read", "ready"): ("preferences available", "ok"),
        ("read", "empty"): ("no saved preferences", "idle"),
        ("save", "ready"): ("save confirmed", "ok"),
        ("pause", "ready"): ("paused locally; saved preferences retained", "idle"),
        ("resume", "ready"): ("preference use resumed", "ok"),
        ("forget", "empty"): ("deletion confirmed", "ok"),
    }
    fallback = {
        "pending": ("awaiting confirmation", "warn"),
        "conflict": ("needs review", "warn"),
        "unavailable": ("unavailable", "bad"),
        "failed": ("failed", "bad"),
    }
    outcome, tone = outcomes.get((action, status), fallback.get(status, ("outcome unavailable", "warn")))
    reasons = {
        "not_configured": "not configured",
        "invalid_identity": "browser identity rejected",
        "timeout": "timeout",
        "authentication_failed": "authentication failed",
        "rate_limited": "rate limit",
        "unavailable": "provider unavailable",
        "invalid_response": "invalid provider response",
        "pagination_limit": "record limit reached",
        "ownership_mismatch": "record scope could not be verified",
        "stale_revision": "saved preferences changed",
        "duplicates": "conflicting records",
        "pending_confirmation": "confirmation pending",
    }
    reason = reasons.get(to_words(row, "reason"), "")
    detail = f"{outcome}{f' · {reason}' if reason else ''} in {took}"
    return ActivityLine(at, labels.get(action, "Preference memory"), detail, tone)


@dataclass(frozen=True)
class ActivityTraceLink:
    """A signed operation link with a fixed label, never a visitor value or upstream run name."""

    label: str
    url: str


@dataclass(frozen=True)
class ActivityRequest:
    """
    One request on Activity: when its first line was written, its row (what it was and how it ended), its ref, and
    its timeline, each line with its time since the first.
    """

    at: datetime
    summary: ActivityLine
    ref: str
    steps: list[tuple[str, ActivityLine]]
    is_chat: bool
    trace_url: str | None
    answer_ref: str
    trace_note: str = ""
    memory_traces: tuple[ActivityTraceLink, ...] = ()

    @property
    def local_at(self) -> datetime:
        """Show the request in Dallas Central Time while keeping UTC timestamps for traces and durations."""
        return self.at.astimezone(ACTIVITY_TIME_ZONE)


def to_memory_trace_links(
    found: Sequence[tuple[Row, ActivityLine]], settings: Settings | None, ref: str, now: datetime
) -> tuple[ActivityTraceLink, ...]:
    """Link only unique recorded Mem0 operations, using the same project, age and signature checks as chat."""
    if settings is None:
        return ()
    labels = MEM0_LABELS
    roots = Counter(
        to_words(row, "traceId") for row, _ in found if row.get("event") in (*ENDING_EVENTS, "memory.operation")
    )
    links = []
    for row, line in found:
        if row.get("event") != "memory.operation":
            continue
        label, root = labels.get(to_words(row, "action")), to_words(row, "traceId")
        if label is None or roots[root] != 1:
            continue
        # The operation is logged when it ends. Its recorded duration establishes its start-time window.
        duration = to_number(row, "ms")
        if not 0 <= duration <= 60_000:
            continue
        started = line.at - timedelta(milliseconds=duration)
        href = trace_url(settings, root, started, ref, now)
        if href is not None:
            links.append(ActivityTraceLink(label, href))
    return tuple(links)


def to_summary(rows: Sequence[Row], lines: Sequence[ActivityLine]) -> ActivityLine:
    """
    A request's row: a health run, by how it ended and each check that wasn't answering; a question, by how it ended
    and the lane it was asked on; a call to our MCP server, by its tool; else the request's own end. A row whose end
    went well, though a line on the way didn't, says how many didn't, and isn't green.
    """
    first = lines[0]
    by_event = {to_words(row, "event"): (row, line) for row, line in zip(rows, lines, strict=True)}
    if "health.done" in by_event:
        _row, done = by_event["health.done"]
        down = [
            f"{to_check_label(row)} ({to_words(row, 'errorClass')})"
            for row in rows
            if to_words(row, "event") == "health.check" and to_words(row, "status") == "down"
        ]
        detail = f"{done.detail}: {', '.join(down)}" if down else done.detail
        return ActivityLine(first.at, "Health check", detail, "warn" if down and done.tone == "ok" else done.tone)
    if "answer.feedback" in by_event:
        return by_event["answer.feedback"][1]
    question = by_event.get("chat.request")
    on = f" · {question[1].detail}" if question else ""
    ending = next((by_event[event][1] for event in ENDING_EVENTS if event in by_event), None)
    if ending is not None:
        if ending.what == "Park trip briefing" and "travel.briefing" in by_event:
            outcome = by_event["travel.briefing"][1]
            return with_problems(
                ActivityLine(first.at, ending.what, f"{outcome.detail} · {ending.detail}{on}", outcome.tone), lines
            )
        return with_problems(ActivityLine(first.at, ending.what, f"{ending.detail}{on}", ending.tone), lines)
    if question is not None:
        return ActivityLine(first.at, "Question", f"{question[1].detail}, with no ending in its lines", "idle")
    if "mcp.call" in by_event:
        call = by_event["mcp.call"][1]
        return with_problems(ActivityLine(first.at, call.what, call.detail, call.tone), lines)
    if "memory.operation" in by_event:
        operation = by_event["memory.operation"][1]
        return with_problems(ActivityLine(first.at, operation.what, operation.detail, operation.tone), lines)
    if "semantic_cache.operation" in by_event:
        operation = by_event["semantic_cache.operation"][1]
        return with_problems(ActivityLine(first.at, operation.what, operation.detail, operation.tone), lines)
    if "http.request" in by_event:
        end = by_event["http.request"][1]
        if end.tone == "ok":
            for event in ("travel.plan", "travel.briefing", "knowledge.call", "nps.alerts", "nws.alerts"):
                if event in by_event:
                    operation = by_event[event][1]
                    return with_problems(
                        ActivityLine(first.at, operation.what, operation.detail, operation.tone), lines
                    )
        return with_problems(ActivityLine(first.at, "Request", end.detail, end.tone), lines)
    return ActivityLine(first.at, "Request", "with no end in its lines", "idle")


def with_problems(row: ActivityLine, lines: Sequence[ActivityLine]) -> ActivityLine:
    """A row whose end went well, with the count of its lines that didn't, and their tone; any other, as it is."""
    problems = [line for line in lines if line.tone in ("warn", "bad") and line.what != "Request ended"]
    if row.tone not in ("ok", "idle") or not problems:
        return row
    return ActivityLine(row.at, row.what, f"{row.detail} · {to_count(len(problems), 'line')} went wrong", "warn")


def to_request_ids(rows: Sequence[Row]) -> list[str]:
    """The requests the first query found, the latest first, each once; an id that isn't one is left out."""
    found = (to_words(row, "requestId") for row in rows)
    return list(dict.fromkeys(request_id for request_id in found if REQUEST_ID_PATTERN.fullmatch(request_id)))


def to_activity_requests(
    request_ids: Sequence[str], rows: Sequence[Row], settings: Settings | None = None
) -> list[ActivityRequest]:
    """
    Each request the first query found, the latest begun first, with every line of its own the second query found,
    in the order they were written; a request none of whose lines a timeline shows is left out.
    """
    lines: dict[str, list[tuple[Row, ActivityLine]]] = {}
    for row in rows:
        line = to_activity_line(row)
        if line is not None:
            lines.setdefault(to_words(row, "requestId"), []).append((row, line))
    requests = []
    now = datetime.now(UTC)
    for request_id in request_ids:
        found = sorted(lines.get(request_id, []), key=lambda item: item[1].at)
        if not found:
            continue
        rows_of, lines_of = [row for row, _line in found], [line for _row, line in found]
        start = lines_of[0].at
        steps = [(f"+{to_duration((line.at - start) / timedelta(milliseconds=1))}", line) for line in lines_of]
        ref = to_ref(request_id)
        memory_traces = to_memory_trace_links(found, settings, ref, now)
        is_chat = any(row.get("event") in QUESTION_EVENTS for row in rows_of)
        # A server-minted root appears only on a traced chat ending. Ambiguous/reused request IDs have no link.
        endings = [(row, line) for row, line in found if row.get("event") in ENDING_EVENTS]
        beginnings = [line.at for row, line in found if row.get("event") == "chat.request"]
        href = None
        if settings is not None and len(beginnings) == len(endings) == 1:
            ending, _ = endings[0]
            if ending.get("event") in ("chat.done", "chat.failed", "chat.aborted"):
                href = trace_url(settings, to_words(ending, "traceId"), beginnings[0], ref, now)
        trace_note = ""
        if len(endings) == 1 and endings[0][0].get("event") == "chat.done" and not to_words(endings[0][0], "traceId"):
            trace_note = {
                "cached": (
                    "Nimbus reused a fresh weather answer without a model call. "
                    "No LangSmith model trace was created for this cache hit."
                ),
                "briefing": (
                    "Nimbus built this park briefing directly without a model call. "
                    "Its source checks appear in this timeline; no LangSmith model trace was created."
                ),
                "intake": (
                    "Nimbus handled this clarification directly without a model call. "
                    "No LangSmith model trace was created."
                ),
            }.get(to_words(endings[0][0], "workflow"), "")
            if to_words(endings[0][0], "memoryIntake").lower() == "true":
                trace_note = (
                    "Nimbus handled this preference request directly without a model call. "
                    "This chat reply did not save any preferences."
                )
        answer_ref = next(
            (to_words(row, "answerRef") for row in rows_of if TURN_ID.fullmatch(to_words(row, "answerRef"))), ""
        )
        requests.append(
            ActivityRequest(
                start, to_summary(rows_of, lines_of), ref, steps, is_chat, href, answer_ref, trace_note, memory_traces
            )
        )
    # By when each began: the first query found each by the line that picked it, which may come later.
    return sorted(requests, key=lambda request: request.at, reverse=True)


def to_days(requests: Sequence[ActivityRequest]) -> list[tuple[str, list[ActivityRequest]]]:
    """Group requests by their Dallas calendar day, retaining their latest-first absolute-time order."""
    days: dict[str, list[ActivityRequest]] = {}
    for request in requests:
        local = request.local_at
        days.setdefault(f"{local:%A} {local.day} {local:%B %Y}", []).append(request)
    return list(days.items())


# ⑤ Performance and Evaluations: the rows, added up.
def to_counts(rows: Sequence[Row], key: str) -> dict[str, float]:
    """Each value of a field, and the lines that had it, added up."""
    counts: dict[str, float] = {}
    for row in rows:
        counts[to_words(row, key)] = counts.get(to_words(row, key), 0) + to_number(row, "lines")
    return counts


def to_endings(rows: Sequence[Row]) -> list[Bar]:
    """How answers ended: answered, stopped, failed, refused, each its count and its share of all four."""
    counts = to_counts(rows, "event")
    endings = (
        ("Answered", "chat.done", "ended well"),
        ("Stopped", "chat.aborted", "Stop pressed, or the page closed"),
        ("Failed", "chat.failed", "our error sentence shown"),
        ("Refused", "chat.rejected", "a rule of the input broken"),
    )
    whole = sum(counts.get(event, 0) for _label, event, _note in endings)
    return [
        Bar(
            label,
            f"{round(counts.get(event, 0)):,}",
            to_share(counts.get(event, 0), whole),
            note,
            to_narrowed_href("ended", event.removeprefix("chat.")),
        )
        for label, event, note in endings
    ]


def to_tool_bars(rows: Sequence[Row], key: str) -> list[Bar]:
    """
    Tool calls by a field (tool or lane): each one's average time and slowest, its calls and failures, and a link to
    the questions behind it, when it's a tool or a lane of ours.
    """
    totals: dict[str, list[float]] = {}
    for row in rows:
        calls, failed, total_ms, slowest = totals.setdefault(to_words(row, key), [0.0, 0.0, 0.0, 0.0])
        totals[to_words(row, key)] = [
            calls + to_number(row, "calls"),
            failed + to_number(row, "failed"),
            total_ms + to_number(row, "totalMs"),
            max(slowest, to_number(row, "slowestMs")),
        ]
    averages = {name: to_share(total_ms, calls) for name, (calls, _failed, total_ms, _slowest) in totals.items()}
    longest = max(averages.values(), default=0.0)
    return [
        Bar(
            to_lane_label(name) if key == "lane" else name,
            f"{to_duration(averages[name])} average · slowest {to_duration(slowest)}",
            to_share(averages[name], longest),
            f"{to_count(calls, 'call')}, {round(failed):,} failed",
            to_narrowed_href(key, name),
        )
        for name, (calls, failed, _total_ms, slowest) in sorted(totals.items(), key=lambda item: -averages[item[0]])
    ]


def to_narrowed_href(kind: str, value: str) -> str:
    """The address of the questions a narrowing picks by a value; none for a value that isn't one of ours."""
    return to_activity_href("questions", **{kind: value}) if value in NARROWINGS[kind][0] else ""


def to_cache_bars(rows: Sequence[Row]) -> list[Bar]:
    """Open-Meteo's answers: from our cache, or fetched, each its share."""
    from_cache = sum(
        to_number(row, "lines")
        for row in rows
        if to_words(row, "event") == "upstream.cache" and to_words(row, "status") == "hit"
    )
    fetched = sum(to_number(row, "lines") for row in rows if to_words(row, "event") == "upstream.http")
    whole = from_cache + fetched
    return [
        Bar("From our cache", f"{round(from_cache):,}", to_share(from_cache, whole), "Vercel's Runtime Cache (step 7)"),
        Bar("Fetched", f"{round(fetched):,}", to_share(fetched, whole), "asked of Open-Meteo"),
    ]


def to_reasons(rows: Sequence[Row], event: str, key: str) -> list[Bar]:
    """
    Why lines of one event happened, by a field (a refusal's code, a failure's class): the most common first, each
    with a link to the questions it happened to, by that event; none for a reason not given, or not one of ours.
    """
    counts: dict[str, float] = {}
    for row in rows:
        if to_words(row, "event") == event:
            reason = to_words(row, key) or NO_REASON
            counts[reason] = counts.get(reason, 0) + to_number(row, "lines")
    whole = sum(counts.values())
    return [
        Bar(name, f"{round(count):,}", to_share(count, whole), href=to_narrowed_href(REASON_LINKS[event], name))
        for name, count in sorted(counts.items(), key=lambda item: -item[1])
    ]


# ⑥ The pages.
def read_kept_run() -> LastRun | None:
    """The golden questions' last run kept; None when there's none, or when its file can't be read, which says so."""
    try:
        return read_last_run()
    except (ValidationError, ValueError) as error:
        log.warning("evals.unreadable", errorClass=type(error).__name__)
        return None


def respond(request: Request, template: str, context: Mapping[str, object], is_kept: bool) -> HTMLResponse:
    """A page, kept by Vercel's CDN for a minute when all it shows answered, else never."""
    response = render_page(request, template, context)
    response.headers["cache-control"] = OBSERVABILITY_CACHE_CONTROL if is_kept else NO_STORE
    return response


@router.get("/activity", response_class=HTMLResponse)
async def activity_page(
    request: Request,
    show: str = "questions",
    tool: str | None = None,
    asked: str | None = None,
    lane: str | None = None,
    ended: str | None = None,
    refused: str | None = None,
    failed: str | None = None,
    fellback: str | None = None,
    day: str | None = None,
) -> HTMLResponse:
    """
    The latest 50 requests of a view, the latest begun first, by day, each opening onto its timeline (step 15); the
    questions narrowed to what a link asks for, and any view to a day. A view we don't have, or a link we didn't
    make, is a 404, and asks nothing.
    """
    # ① Checked here rather than by a Literal, whose 422 would be FastAPI's JSON: an address with no page is our 404.
    if show not in ACTIVITY_VIEWS:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    links = {"tool": tool, "asked": asked, "lane": lane, "ended": ended}
    narrowing = to_narrowing({**links, "refused": refused, "failed": failed, "fellback": fellback})
    if narrowing is not None and show != "questions":
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    on_day = to_day(day, datetime.now(UTC))
    # ② The requests the view's lines pick, over its time; then every line of theirs a timeline shows. Each query is
    # named by its view, its narrowing and whether it's a day's, so one's failure is never another's (issue 84).
    where = narrowing.where if narrowing is not None else ACTIVITY_VIEWS[show]
    name = f"activity-{show}{f'-{narrowing.kind}' if narrowing else ''}{'-day' if on_day else ''}"
    answers = await ask_axiom(request, {name: to_requests_query(where)}, on_day)
    request_ids = to_request_ids(answers.rows.get(name, []))
    is_full = len(request_ids) >= ACTIVITY_REQUESTS
    if request_ids:
        answers = await ask_axiom(request, {"activity-lines": to_timeline_query(request_ids)})
    lines = answers.rows.get("activity-lines", [])
    # ③ At the cap, the oldest request found may have lost its first lines: it's left out, and the page says so.
    is_cut = len(lines) >= ACTIVITY_REQUEST_LINES
    if is_cut:
        oldest = min(lines, key=lambda row: to_moment(row, "_time") or datetime.max.replace(tzinfo=UTC))
        request_ids = [request_id for request_id in request_ids if request_id != to_words(oldest, "requestId")]
    requests = to_activity_requests(request_ids, lines, request.app.state.settings)
    narrowed = [narrowing.words] if narrowing is not None else []
    if on_day is not None:
        narrowed.append(f"{to_day_words(on_day)} (UTC filter)")
    context = {
        "title": "Activity",
        "tracing_enabled": is_tracing_allowed(request.app.state.settings),
        "show": show,
        "tabs": [(label, to_activity_href(view, day=day), view == show) for view, label in ACTIVITY_TABS],
        "narrowed": narrowed,
        "everything": to_activity_href(show),
        "days": to_days(requests),
        "answers": answers,
        "is_cut": is_cut,
        "is_full": is_full,
        "lines_cap": ACTIVITY_REQUEST_LINES,
        "requests_cap": ACTIVITY_REQUESTS,
    }
    return respond(request, "activity.html", context, answers.notice is None)


type TraceReader = Callable[[Settings, UUID], Awaitable[TraceView]]


def get_activity_trace_reader() -> TraceReader:
    """The server-side reader used only when a visitor opens a trace."""
    return read_trace


@router.get("/activity/trace/{handle}", response_class=HTMLResponse)
async def activity_trace_page(
    request: Request, handle: str, reader: Annotated[TraceReader, Depends(get_activity_trace_reader)]
) -> HTMLResponse:
    """Read the signed Activity row's trace on demand, with independent capacity for these public requests."""
    settings: Settings = request.app.state.settings
    link = resolve_trace_link(settings, handle, datetime.now(UTC))
    if link is None:
        response = render_page(request, "not_found.html", {}, status_code=HTTPStatus.NOT_FOUND)
    else:
        trace_id, ref = link
        context: dict[str, object] = {"title": "LangSmith trace", "ref": ref, "menu_path": "/activity"}
        gate: RetrievalGate = request.app.state.trace_gate
        try:
            async with gate.reserve(request.client.host if request.client else "unknown"):
                trace = await reader(settings, trace_id)
            context.update(trace=trace, presentation=present_trace(trace))
            response = render_page(request, "activity_trace.html", context)
        except HTTPException as error:
            if error.status_code != HTTPStatus.TOO_MANY_REQUESTS:
                raise
            context["trace"] = {"status": "busy"}
            response = render_page(request, "activity_trace.html", context, status_code=error.status_code)
            response.headers.update(error.headers or {})
    response.headers["cache-control"] = NO_STORE
    return response


def to_day_words(day: date) -> str:
    """A day as Activity says what it's narrowed to: "On Monday 2 November 2026"."""
    return f"On {day:%A} {day.day} {day:%B %Y}"


def measured_duration(row: Row, field: str) -> str:
    """Use an explicit missing value when Axiom has no duration sample."""
    return to_duration(to_number(row, field)) if row.get(field) is not None else "Unavailable"


def response_bars(rows: Sequence[Row]) -> list[Bar]:
    """Separate completed agent answers, conditions briefings, clarification replies and older unknown events."""
    labels = {
        "agent": "Agent answers",
        "cached": "Cached weather answers",
        "briefing": "Park conditions briefings",
        "intake": "Clarifications and guidance",
        "unknown": "Unclassified older responses",
    }
    whole = sum(to_number(row, "responses") for row in rows)
    return [
        Bar(
            labels.get(to_words(row, "responseWorkflow"), "Unclassified older responses"),
            to_count(to_number(row, "responses"), "response"),
            to_share(to_number(row, "responses"), whole),
            f"P50 {measured_duration(row, 'p50')} · P95 {measured_duration(row, 'p95')}",
        )
        for row in rows
    ]


def service_bars(rows: Sequence[Row]) -> list[Bar]:
    """Keep each service's full outcome vocabulary, including empty, partial, disabled and failed results."""
    groups: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        groups.setdefault((to_words(row, "event"), to_words(row, "tool")), []).append(row)
    averages = {
        key: to_share(sum(to_number(row, "totalMs") for row in calls), sum(to_number(row, "calls") for row in calls))
        for key, calls in groups.items()
    }
    longest = max(averages.values(), default=0)
    bars = []
    for (event, tool), calls in sorted(groups.items()):
        count = sum(to_number(row, "calls") for row in calls)
        total_ms = sum(to_number(row, "totalMs") for row in calls)
        slowest = max((to_number(row, "slowestMs") for row in calls), default=0)
        outcomes = " · ".join(
            f"{round(to_number(row, 'calls')):,} {to_words(row, 'status').replace('_', ' ') or 'unknown'}"
            for row in sorted(calls, key=lambda row: to_words(row, "status"))
        )
        prefix = {"nps.alerts": "NPS notices", "nws.alerts": "NWS weather alerts"}.get(event)
        label = f"{prefix} · {tool}" if prefix else tool
        bars.append(
            Bar(
                label,
                f"{to_duration(to_share(total_ms, count))} average · slowest {to_duration(slowest)}",
                to_share(averages[event, tool], longest),
                f"{to_count(count, 'call')} · {outcomes}",
                to_narrowed_href("tool", tool),
            )
        )
    return bars


@router.get("/performance", response_class=HTMLResponse)
async def performance_page(request: Request) -> HTMLResponse:
    """Show model latency separately from deterministic replies and each service's recorded outcomes."""
    queries = {
        "answers": ANSWERS,
        "workflows": WORKFLOWS,
        "endings": ENDINGS,
        "tool-calls": TOOL_CALLS,
        "service-calls": SERVICE_CALLS,
        "weather-answers": WEATHER_ANSWERS,
    }
    answers = await ask_axiom(request, queries)
    [summary] = answers.rows.get("answers") or [{}]
    questions = to_counts(
        [row for row in answers.rows.get("endings", []) if to_words(row, "event") == "chat.request"], "lane"
    )
    tiles = [
        Tile("Model answers", f"{round(to_number(summary, 'answers')):,}", "completed agent turns"),
        Tile("P50", measured_duration(summary, "p50"), "half took less"),
        Tile("P95", measured_duration(summary, "p95")),
        Tile("P99", measured_duration(summary, "p99")),
        Tile(
            "Tool calls",
            f"{to_number(summary, 'avgToolCalls'):.1f}" if summary.get("avgToolCalls") is not None else "Unavailable",
            "per completed agent turn",
        ),
        Tile(
            "Tokens",
            f"{round(to_number(summary, 'avgTokensIn')):,} in"
            if summary.get("avgTokensIn") is not None
            else "Unavailable",
            f"{round(to_number(summary, 'avgTokensOut')):,} out, per recorded agent turn"
            if summary.get("avgTokensOut") is not None
            else "usage was not recorded",
        ),
    ]
    tool_calls = answers.rows.get("tool-calls", [])
    whole = sum(questions.values())
    context = {
        "title": "Performance",
        "answers": answers,
        "tiles": tiles,
        "model_answers": to_number(summary, "answers"),
        "responses": response_bars(answers.rows.get("workflows", [])),
        "services": service_bars(answers.rows.get("service-calls", [])),
        "tools": to_tool_bars(tool_calls, "tool"),
        "lanes": to_tool_bars(tool_calls, "lane"),
        "questions": [
            Bar(to_lane_label(lane), f"{round(count):,}", to_share(count, whole), href=to_narrowed_href("asked", lane))
            for lane, count in questions.items()
        ],
        "weather": to_cache_bars(answers.rows.get("weather-answers", [])),
        "days": OBSERVABILITY_DAYS,
    }
    return respond(request, "performance.html", context, answers.notice is None)


@router.get("/evaluations", response_class=HTMLResponse)
async def evaluations_page(request: Request) -> HTMLResponse:
    """The golden questions and their last run, kept in the repository; how live answers ended, and why, over 7 days."""
    answers = await ask_axiom(request, {"endings": ENDINGS, "reasons": REASONS})
    reasons = answers.rows.get("reasons", [])
    last_run = read_kept_run()
    kept = last_run.results if last_run is not None else []
    results = {result.id: result for result in kept}
    context = {
        "title": "Evaluations",
        "answers": answers,
        "goldens": [(golden, results.get(golden.id)) for golden in read_goldens()],
        "scorecards": public_reports(),
        "last_run": last_run,
        "passed": sum(result.passed for result in kept),
        "endings": to_endings(answers.rows.get("endings", [])),
        "refusals": to_reasons(reasons, "chat.rejected", "code"),
        "failures": to_reasons(reasons, "chat.failed", "errorClass"),
        "fallbacks": to_reasons(reasons, "lane.fallback", "errorClass"),
        "days": OBSERVABILITY_DAYS,
    }
    return respond(request, "evaluations.html", context, answers.notice is None)


@router.get("/health", response_class=HTMLResponse)
async def health_page(request: Request) -> HTMLResponse:
    """
    The checks now, as /api/health finds them; how often they passed each day, the last 7 (the 7 days before now
    reach into an eighth, a part of it); and the weather MCP endpoint for the current environment.
    """
    state = request.app.state
    settings: Settings = state.settings
    report, answers = await asyncio.gather(to_report(request), ask_axiom(request, {"health-days": HEALTH_DAYS}))
    days = [
        Bar(
            f"{moment:%A} {moment.day} {moment:%B}" if (moment := to_moment(row, "day")) else "unknown day",
            f"{round(to_number(row, 'runs') - to_number(row, 'down')):,} of {round(to_number(row, 'runs')):,} passed",
            to_share(to_number(row, "runs") - to_number(row, "down"), to_number(row, "runs")),
            # Step 15: the day's runs on Activity; on a day with failures, its errors, where they aren't buried under
            # the runs that passed.
            href=to_activity_href("errors" if to_number(row, "down") else "health", day=f"{moment:%Y-%m-%d}")
            if moment
            else "",
        )
        for row in answers.rows.get("health-days", [])[:OBSERVABILITY_DAYS]
    ]
    if settings.environment == "preview":
        host = settings.vercel_url or settings.vercel_branch_url
        mcp_url = f"https://{host}{MCP_PATH}" if host else MCP_PATH
    elif settings.environment == "production" and settings.vercel_project_production_url:
        mcp_url = f"https://{settings.vercel_project_production_url}{MCP_PATH}"
    else:
        mcp_url = state.to_mcp_url(request, settings) or MCP_PATH
    # The JSON monitor omits disabled travel providers. Show them as off to visitors without probing them.
    checks = dict(report.checks)
    for name in TRAVEL_CHECKS:
        checks.setdefault(name, CheckResult("off"))
    context = {
        "title": "Health",
        "answers": answers,
        "report": report,
        "checks": checks,
        "check_labels": CHECK_LABELS,
        "lane_labels": LANE_LABELS,
        "status_words": STATUS_WORDS,
        "days": days,
        "history_days": OBSERVABILITY_DAYS,
        "mcp_url": mcp_url,
        "mcp_tools": WEATHER_TOOLS,
    }
    return respond(request, "health.html", context, answers.notice is None and report.status == "ok")
