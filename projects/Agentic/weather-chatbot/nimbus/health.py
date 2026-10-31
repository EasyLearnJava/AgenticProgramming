"""
nimbus/health.py: GET /api/health: which lanes work (step 12), for the status dots and an uptime monitor; it answers
HEAD too, which uptime monitors often send. Four checks, at once, each within 8 s, none of which costs: Open-Meteo
geocodes Paris, its cache skipped, so an outage shows; our MCP server is connected to and offers our four tools, as the
MCP lanes need; Apify's REST door reads the account behind the token, which runs nothing; Apify's MCP server is
connected to with the token, its tools checked against our pin. A lane works when every check its answers depend on
passes; without Apify's token, the lanes with auth are off. 200 when every lane that's on works, else 503, with the
same report, so a monitor needs only the status. A run's report answers every request through the same address to
this copy of the app for a minute, and Vercel's CDN keeps a 200 for one more.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nimbus.apify import check_apify_token, open_apify_mcp
from nimbus.auth_lanes import NEEDS_A_LOOK
from nimbus.config import Settings
from nimbus.constants import HEALTH_CACHE_CONTROL, HEALTH_CHECK_SECONDS, HEALTH_PLACE, HEALTH_RUN_SECONDS, NO_STORE
from nimbus.errors import ContractError, UpstreamError, UpstreamTimeoutError, UpstreamUnavailableError
from nimbus.lanes import LaneId
from nimbus.mcp_lane import open_mcp_runs
from nimbus.open_meteo import OpenMeteoClient
from nimbus.utils import to_iso, to_ms

router = APIRouter()
log = structlog.get_logger()

type CheckName = Literal["open-meteo", "our-mcp", "apify-rest", "apify-mcp"]
type Status = Literal["ok", "down", "off"]
# A check passes when it returns, within its time; None is a check that's off (no token).
type Check = Callable[[], Awaitable[None]] | None

# The checks each lane's answers depend on: its own door, and Open-Meteo, which every lane geocodes with, the lanes
# with auth too (MCP · with auth through our own MCP server).
CHECKS_BY_LANE: Final[Mapping[LaneId, tuple[CheckName, ...]]] = {
    "rest-no-auth": ("open-meteo",),
    "rest-with-auth": ("apify-rest", "open-meteo"),
    "mcp-no-auth": ("our-mcp", "open-meteo"),
    "mcp-with-auth": ("apify-mcp", "our-mcp", "open-meteo"),
}


@dataclass(frozen=True)
class CheckResult:
    """How a check went: it passed, failed with one of our errors' classes, or was off; and its time, if it ran."""

    status: Status
    ms: int | None = None
    error_class: str | None = None

    def to_json(self) -> dict[str, object]:
        """The result as the report shows it."""
        shown: dict[str, object] = {"status": self.status}
        if self.ms is not None:
            shown["ms"] = self.ms
        if self.error_class is not None:
            shown["errorClass"] = self.error_class
        return shown


@dataclass(frozen=True)
class HealthReport:
    """What a run found: overall, each check, and each lane; and when it ran."""

    status: Literal["ok", "down"]
    checks: Mapping[CheckName, CheckResult]
    lanes: Mapping[LaneId, Status]
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def to_failure(error: Exception) -> UpstreamError:
    """A check's failure as one of our errors: as it is, if it's one; past its time, a timeout; else unavailable."""
    if isinstance(error, UpstreamError):
        return error
    return UpstreamTimeoutError() if isinstance(error, TimeoutError) else UpstreamUnavailableError()


async def run_check(name: CheckName, check: Check) -> CheckResult:
    """
    One check, within its 8 s: how it went, and one health.check line; a failure at its class's level, so a token
    Apify refuses (AuthError) is an error, which reaches Sentry, before anyone picks a lane with auth.
    """
    if check is None:
        return CheckResult("off")
    started = time.perf_counter()
    try:
        async with asyncio.timeout(HEALTH_CHECK_SECONDS):
            await check()
    except Exception as error:
        failure = to_failure(error)
        ms = to_ms(time.perf_counter() - started)
        write = log.error if isinstance(failure, NEEDS_A_LOOK) else log.warning
        write("health.check", check=name, status="down", ms=ms, errorClass=type(failure).__name__)
        return CheckResult("down", ms, type(failure).__name__)
    ms = to_ms(time.perf_counter() - started)
    log.info("health.check", check=name, status="ok", ms=ms)
    return CheckResult("ok", ms)


def to_lane_status(lane: LaneId, checks: Mapping[CheckName, CheckResult]) -> Status:
    """A lane's status: off when a check it needs is off, down when one failed, else ok."""
    statuses = [checks[name].status for name in CHECKS_BY_LANE[lane]]
    if "off" in statuses:
        return "off"
    return "down" if "down" in statuses else "ok"


async def check_lanes(checks: Mapping[CheckName, Check]) -> HealthReport:
    """Runs every check at once, each within its time, and says what works; one health.done line."""
    started = time.perf_counter()
    names = list(checks)
    results = dict(zip(names, await asyncio.gather(*(run_check(name, checks[name]) for name in names)), strict=True))
    lanes = {lane: to_lane_status(lane, results) for lane in CHECKS_BY_LANE}
    status: Literal["ok", "down"] = "down" if "down" in lanes.values() else "ok"
    log.info("health.done", status=status, ms=to_ms(time.perf_counter() - started), lanes=lanes)
    return HealthReport(status, results, lanes)


def make_checks(request: Request, mcp_url: str | None) -> dict[CheckName, Check]:
    """The four checks, through the app's own ways out (the tests give their own); Apify's two, only with its token."""
    state = request.app.state
    settings: Settings = state.settings
    token = settings.apify_token

    async def open_meteo() -> None:
        """Geocodes the place, with no cache: no place at all is an answer we can't use."""
        async with state.make_http_client() as http:
            places = (await OpenMeteoClient(http).search_places(HEALTH_PLACE, 1, None)).data
        if not places:
            raise ContractError

    async def our_mcp() -> None:
        """Connects to our MCP server and checks it offers our four tools, as the MCP lanes do before an answer."""
        async with open_mcp_runs(mcp_url, state.make_mcp_http_client(), settings.vercel_automation_bypass_secret):
            pass

    async def apify_rest() -> None:
        """Reads the account behind the token: no Actor runs."""
        assert token is not None  # noqa: S101 - only made with the token
        async with state.make_apify_http_client() as http:
            await check_apify_token(http, token)

    async def apify_mcp() -> None:
        """Connects to Apify's MCP server with the token and checks its tools against our pin: no Actor runs."""
        assert token is not None  # noqa: S101 - only made with the token
        async with open_apify_mcp(state.make_apify_http_client(), token) as apify:
            if apify.client is None:
                raise apify.error or UpstreamUnavailableError()

    return {
        "open-meteo": open_meteo,
        "our-mcp": our_mcp,
        "apify-rest": apify_rest if token is not None else None,
        "apify-mcp": apify_mcp if token is not None else None,
    }


@dataclass
class HealthRun:
    """A run of the checks through one address: when it started, and the task that finds its report."""

    started: float
    task: asyncio.Task[HealthReport]


async def to_report(request: Request) -> HealthReport:
    """
    The report for this request: the run through its address that started within the last minute, on this copy of the
    app, waited for if it's still going; else a new run. One address's report never answers for another's.
    """
    state = request.app.state
    mcp_url = state.to_mcp_url(request, state.settings)
    runs: dict[str, HealthRun] = state.health_runs
    run = runs.get(mcp_url or "")
    now = time.monotonic()
    if run is None or now - run.started >= HEALTH_RUN_SECONDS or run.task.get_loop() is not asyncio.get_running_loop():
        run = runs[mcp_url or ""] = HealthRun(now, asyncio.create_task(check_lanes(make_checks(request, mcp_url))))
    # Shielded: a request that goes away doesn't stop the run the others wait for.
    return await asyncio.shield(run.task)


@router.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request) -> JSONResponse:
    """Which lanes work, and which build answers: 200 when every lane that's on works, kept a minute by Vercel's CDN."""
    settings: Settings = request.app.state.settings
    report = await to_report(request)
    body = {
        "status": report.status,
        "checkedAt": to_iso(report.checked_at),
        "commit": settings.commit,
        "environment": settings.environment,
        "checks": {name: result.to_json() for name, result in report.checks.items()},
        "lanes": dict(report.lanes),
    }
    ok = report.status == "ok"
    headers = {"cache-control": HEALTH_CACHE_CONTROL if ok else NO_STORE}
    return JSONResponse(body, status_code=200 if ok else 503, headers=headers)
