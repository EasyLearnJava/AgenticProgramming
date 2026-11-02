"""
nimbus/observability.py: the Observability pages (step 14). Activity: the latest lines, a filter at a time.
Performance: how long answers and tools take, each lane, the cache. Evaluations: the golden questions' last run, and how
live answers end. Health: the checks now, how often they passed, and our MCP server. Their numbers come from Axiom,
asked with a token that can only query, over the last 7 days; each query names the fields it reads, never a request's
id, its path, or anything a visitor typed, which the lines never hold anyway (step 11). A page's queries answer it for a
minute on each copy of the app, and Vercel's CDN keeps the page a minute more; a page Axiom couldn't answer is never
kept.
"""

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Final

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from starlette.datastructures import State

from nimbus.axiom_query import AxiomQuery, Row
from nimbus.config import Settings
from nimbus.constants import (
    ACTIVITY_LINES,
    MCP_PATH,
    NO_STORE,
    OBSERVABILITY_CACHE_CONTROL,
    OBSERVABILITY_DAYS,
    OBSERVABILITY_RUN_SECONDS,
)
from nimbus.errors import AXIOM_NOT_CONNECTED, ObservabilityError
from nimbus.goldens import LastRun, read_goldens, read_last_run
from nimbus.health import to_report
from nimbus.lanes import LANES
from nimbus.pages import render_page
from nimbus.tools import WEATHER_TOOLS
from nimbus.utils import to_ms

router = APIRouter()
log = structlog.get_logger()

MS_PER_SECOND = 1000
LANE_LABELS: Final = {lane.id: lane.label for lane in LANES}
CHECK_LABELS: Final = {
    "open-meteo": "Open-Meteo",
    "our-mcp": "Our MCP server",
    "apify-rest": "Apify's REST API",
    "apify-mcp": "Apify's MCP server",
}
STATUS_WORDS: Final = {"ok": "working", "down": "not answering", "off": "off"}
# A failure that needs a look: Axiom refused our token, or our query. Each is an error once on each copy of the app,
# which reaches Sentry; then a warning, as the health check's (issue 74).
NEEDS_A_LOOK: Final = frozenset({"axiom_refused", "axiom_bad_query"})
# A refused token is one fault, whichever query met it: it's kept by its code, so it reaches Sentry once on each copy,
# not once for each query; a refused query, by the query's name.
TOKEN_FAULTS: Final = frozenset({"axiom_refused"})


# ① The queries: each over the dataset, each naming the fields it reads. _time, event, level, status and ms are on every
# request's own line (http.request), so the dataset has them once the app has answered once; any other comes from
# rarer lines, which a young dataset may never have had, and Axiom refuses a query that names a field it has never
# seen: those are read through column_ifexists, which gives a default instead. status holds a number on some lines
# (http.request's 200) and words on others, so it's compared as words. Activity's filters, each a where clause of our
# own, are chosen by name, never written from the address; "all" leaves the health checks to their own filter, since
# every page's dots and every uptime ping add one.
QUESTION_EVENTS: Final = ("chat.request", "chat.done", "chat.aborted", "chat.failed", "chat.rejected")
TOOL_EVENTS: Final = ("tool.call", "lane.fallback")
ACTIVITY_EVENTS: Final = (*QUESTION_EVENTS, *TOOL_EVENTS, "health.done")
EVERY_LINES_FIELDS: Final = frozenset({"_time", "event", "level", "status", "ms"})
STATUS: Final = "tostring(status)"
ACTIVITY_FIELDS: Final = (
    "_time",
    "event",
    "level",
    "lane",
    "tool",
    "status",
    "ms",
    "errorClass",
    "code",
    "toolCalls",
    "tokensIn",
    "tokensOut",
    "fromLane",
    "toLane",
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


ACTIVITY_FILTERS: Final[Mapping[str, str]] = {
    "all": to_in("event", (*QUESTION_EVENTS, *TOOL_EVENTS)),
    "questions": to_in("event", QUESTION_EVENTS),
    "tools": to_in("event", TOOL_EVENTS),
    "health": 'event == "health.done"',
    "errors": (
        f'{to_in("event", ACTIVITY_EVENTS)} and (level == "error" or {STATUS} in ("failed", "down") '
        'or event == "lane.fallback")'
    ),
}
ACTIVITY_TABS: Final = (
    ("all", "All"),
    ("questions", "Questions"),
    ("tools", "Tools"),
    ("health", "Health"),
    ("errors", "Errors"),
)
ANSWERS: Final = (
    'where event == "chat.done"',
    "summarize answers = count(), p50 = percentile(ms, 50), p95 = percentile(ms, 95), p99 = percentile(ms, 99), "
    f"avgToolCalls = avg({to_field('toolCalls', '0')}), avgTokensIn = avg({to_field('tokensIn', '0')}), "
    f"avgTokensOut = avg({to_field('tokensOut', '0')})",
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


def to_activity_query(show: str) -> tuple[str, ...]:
    """Activity's query for a filter: its lines, the latest first, at most 50, with only the fields it shows."""
    return (
        f"where {ACTIVITY_FILTERS[show]}",
        "sort by _time desc",
        f"take {ACTIVITY_LINES}",
        f"project {', '.join(to_named(name) for name in ACTIVITY_FIELDS)}",
    )


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


async def run_query(state: State, name: str, apl: str) -> list[Row]:
    """
    The query's rows over the last 7 days, and one observability.query line: its name, how it went, its time; a
    failure by its class and code, at error when it needs a look and is new on this copy, else a warning: a query that
    keeps failing would send Sentry an event every minute, and use up its free quota. failing keeps each query's
    failure, until it answers; a refused token, once for every query, until any answers.
    """
    axiom: AxiomQuery = state.axiom_query
    failing: dict[str, str] = state.observability_failures
    started = time.perf_counter()
    end = datetime.now(UTC)
    try:
        rows = await axiom.run(apl, end - timedelta(days=OBSERVABILITY_DAYS), end)
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


async def ask(request: Request, name: str, apl: str) -> list[Row]:
    """
    The query's rows: from the run of the same query that started within the last minute on this copy of the app,
    waited for if it's still going; else a new run. A failed run answers for its minute too, so an Axiom that's
    failing isn't asked again at every visit.
    """
    state = request.app.state
    runs: dict[str, QueryRun] = state.observability_runs
    run = runs.get(apl)
    now = time.monotonic()
    if (
        run is None
        or now - run.started >= OBSERVABILITY_RUN_SECONDS
        or run.task.get_loop() is not asyncio.get_running_loop()
    ):
        run = runs[apl] = QueryRun(now, asyncio.create_task(run_query(state, name, apl)))
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


async def ask_axiom(request: Request, queries: Mapping[str, Sequence[str]]) -> Answers:
    """Each query's rows, all at once; none, with its sentence, when Axiom isn't connected or one query failed."""
    state = request.app.state
    dataset = state.settings.axiom_dataset
    if state.axiom_query is None or dataset is None:
        return Answers({}, AXIOM_NOT_CONNECTED)
    names = list(queries)
    found = await asyncio.gather(
        *(ask(request, name, to_apl(dataset, queries[name])) for name in names), return_exceptions=True
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
    """A line of a breakdown: what it is, its value in words, its share of the largest or the whole, and a note."""

    label: str
    value: str
    share: float
    note: str = ""


# ④ Activity: a line each, in words, grouped by day.
@dataclass(frozen=True)
class ActivityLine:
    """One line of Activity: when, what happened, the rest in words, and how it went: ok, warn, bad or idle."""

    at: datetime
    what: str
    detail: str
    tone: str


def to_activity_line(row: Row) -> ActivityLine | None:
    """A line of Activity from Axiom's row; None for an event Activity doesn't show, or one with no time."""
    at = to_moment(row, "_time")
    if at is None:
        return None
    event, took = to_words(row, "event"), to_duration(to_number(row, "ms"))
    lane, error_class = to_lane_label(to_words(row, "lane")), to_words(row, "errorClass")
    if event == "chat.request":
        return ActivityLine(at, "Question", f"on {lane}", "idle")
    if event == "chat.done":
        tokens_in, tokens_out = (round(to_number(row, name)) for name in ("tokensIn", "tokensOut"))
        calls = to_count(to_number(row, "toolCalls"), "tool call")
        detail = f"in {took} · {calls} · {tokens_in:,} tokens in, {tokens_out:,} out"
        return ActivityLine(at, "Answered", detail, "ok")
    if event == "chat.aborted":
        return ActivityLine(at, "Stopped", f"after {took}", "idle")
    if event == "chat.failed":
        return ActivityLine(at, "Failed", f"{error_class} after {took}", "bad")
    if event == "chat.rejected":
        return ActivityLine(at, "Refused", to_words(row, "code"), "warn")
    if event == "tool.call":
        tool = to_words(row, "tool")
        if to_words(row, "status") == "failed":
            return ActivityLine(at, tool, f"failed on {lane}: {error_class}, after {took}", "bad")
        return ActivityLine(at, tool, f"on {lane} in {took}", "ok")
    if event == "lane.fallback":
        moved = f"{to_lane_label(to_words(row, 'fromLane'))} to {to_lane_label(to_words(row, 'toLane'))}"
        return ActivityLine(at, "Fell back", f"{moved}: {error_class}", "warn")
    if event == "health.done":
        status = to_words(row, "status")
        return ActivityLine(
            at, "Health check", f"{STATUS_WORDS.get(status, status)} in {took}", "ok" if status == "ok" else "bad"
        )
    return None


def to_days(lines: Sequence[ActivityLine]) -> list[tuple[str, list[ActivityLine]]]:
    """The lines grouped by their day in UTC, in the order they came: the latest first."""
    days: dict[str, list[ActivityLine]] = {}
    for line in lines:
        days.setdefault(f"{line.at:%A} {line.at.day} {line.at:%B %Y}", []).append(line)
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
        Bar(label, f"{round(counts.get(event, 0)):,}", to_share(counts.get(event, 0), whole), note)
        for label, event, note in endings
    ]


def to_tool_bars(rows: Sequence[Row], key: str) -> list[Bar]:
    """Tool calls by a field (tool or lane): each one's average time and slowest, its calls and failures."""
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
        )
        for name, (calls, failed, _total_ms, slowest) in sorted(totals.items(), key=lambda item: -averages[item[0]])
    ]


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
    """Why lines of one event happened, by a field (a refusal's code, a failure's class): the most common first."""
    counts: dict[str, float] = {}
    for row in rows:
        if to_words(row, "event") == event:
            reason = to_words(row, key) or "none given"
            counts[reason] = counts.get(reason, 0) + to_number(row, "lines")
    whole = sum(counts.values())
    return [
        Bar(name, f"{round(count):,}", to_share(count, whole))
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
async def activity_page(request: Request, show: str = "all") -> HTMLResponse:
    """The latest 50 lines of a filter, in words, the latest first, by day; a filter we don't have is a 404."""
    # Checked here rather than by a Literal, whose 422 would be FastAPI's JSON: an address with no page is our 404 page.
    if show not in ACTIVITY_FILTERS:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    answers = await ask_axiom(request, {f"activity-{show}": to_activity_query(show)})
    lines = [line for row in answers.rows.get(f"activity-{show}", []) if (line := to_activity_line(row)) is not None]
    context = {
        "title": "Activity",
        "show": show,
        "tabs": ACTIVITY_TABS,
        "days": to_days(lines),
        "answers": answers,
    }
    return respond(request, "activity.html", context, answers.notice is None)


@router.get("/performance", response_class=HTMLResponse)
async def performance_page(request: Request) -> HTMLResponse:
    """How long answers take, each tool and each lane, and Open-Meteo's answers from the cache, over 7 days."""
    answers = await ask_axiom(
        request, {"answers": ANSWERS, "endings": ENDINGS, "tool-calls": TOOL_CALLS, "weather-answers": WEATHER_ANSWERS}
    )
    [summary] = answers.rows.get("answers") or [{}]
    questions = {
        to_lane_label(lane): count
        for lane, count in to_counts(
            [row for row in answers.rows.get("endings", []) if to_words(row, "event") == "chat.request"], "lane"
        ).items()
    }
    tiles = [
        Tile("Answers", f"{round(to_number(summary, 'answers')):,}", "ended well"),
        Tile("P50", to_duration(to_number(summary, "p50")), "half took less"),
        Tile("P95", to_duration(to_number(summary, "p95"))),
        Tile("P99", to_duration(to_number(summary, "p99"))),
        Tile("Tool calls", f"{to_number(summary, 'avgToolCalls'):.1f}", "an answer"),
        Tile(
            "Tokens",
            f"{round(to_number(summary, 'avgTokensIn')):,} in",
            f"{round(to_number(summary, 'avgTokensOut')):,} out, an answer",
        ),
    ]
    tool_calls = answers.rows.get("tool-calls", [])
    whole = sum(questions.values())
    context = {
        "title": "Performance",
        "answers": answers,
        "tiles": tiles,
        "tools": to_tool_bars(tool_calls, "tool"),
        "lanes": to_tool_bars(tool_calls, "lane"),
        "questions": [Bar(lane, f"{round(count):,}", to_share(count, whole)) for lane, count in questions.items()],
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
    reach into an eighth, a part of it); and our MCP server, at the production address, which names no deployment,
    else where the MCP lanes find it.
    """
    state = request.app.state
    settings: Settings = state.settings
    report, answers = await asyncio.gather(to_report(request), ask_axiom(request, {"health-days": HEALTH_DAYS}))
    days = [
        Bar(
            f"{moment:%A} {moment.day} {moment:%B}" if (moment := to_moment(row, "day")) else "unknown day",
            f"{round(to_number(row, 'runs') - to_number(row, 'down')):,} of {round(to_number(row, 'runs')):,} passed",
            to_share(to_number(row, "runs") - to_number(row, "down"), to_number(row, "runs")),
        )
        for row in answers.rows.get("health-days", [])[:OBSERVABILITY_DAYS]
    ]
    production = settings.vercel_project_production_url
    context = {
        "title": "Health",
        "answers": answers,
        "report": report,
        "check_labels": CHECK_LABELS,
        "lane_labels": LANE_LABELS,
        "status_words": STATUS_WORDS,
        "days": days,
        "history_days": OBSERVABILITY_DAYS,
        "mcp_url": f"https://{production}{MCP_PATH}" if production else state.to_mcp_url(request, settings) or MCP_PATH,
        "mcp_tools": WEATHER_TOOLS,
    }
    return respond(request, "health.html", context, answers.notice is None and report.status == "ok")
