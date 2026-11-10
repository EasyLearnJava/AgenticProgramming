"""
nimbus/health.py: GET/HEAD /api/health checks weather lanes, the enabled park index and travel providers. Checks run
concurrently within eight seconds. Open-Meteo geocodes Paris, the Nimbus MCP server lists weather tools, and the
Apify checks validate configured access. Index readiness checks Qdrant publication without inference. Optional
flight and hotel providers list search tools and report their status separately. A failed weather or index check
returns HTTP 503. Each weather lane retains its own status.
Reports are shared for one minute per address on this app instance, with a successful response cached at the CDN.
"""

import asyncio
import re
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
from nimbus.errors import (
    ContractError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.lanes import LaneId
from nimbus.mcp_lane import open_mcp_runs
from nimbus.open_meteo import OpenMeteoClient
from nimbus.parks import ParkKnowledge
from nimbus.travel.mcp_client import TravelProviderError, check_provider
from nimbus.utils import to_iso, to_ms

router = APIRouter()
log = structlog.get_logger()

type CheckName = Literal["open-meteo", "our-mcp", "apify-rest", "apify-mcp", "park-index", "kiwi-mcp", "trivago-mcp"]
TRAVEL_CHECKS: Final[tuple[CheckName, ...]] = ("kiwi-mcp", "trivago-mcp")
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
    if isinstance(error, TravelProviderError):
        return {
            "timeout": UpstreamTimeoutError,
            "invalid_response": ContractError,
            "rate_limited": UpstreamRateLimitedError,
            "unavailable": UpstreamUnavailableError,
        }[error.reason]()
    if isinstance(error, UpstreamError):
        return error
    return UpstreamTimeoutError() if isinstance(error, TimeoutError) else UpstreamUnavailableError()


async def run_check(name: CheckName, check: Check, failing: dict[CheckName, str]) -> CheckResult:
    """
    One check, within its 8 s: how it went, and one health.check line. A failure that needs a look, a token Apify
    refuses (AuthError), say, is an error, which reaches Sentry before anyone picks a lane with auth; but only when it's
    new on this copy of the app (failing keeps each check's failure, until it passes): a check that keeps failing would
    send an event every run, and use up Sentry's free quota. Then it's a warning, still a line.
    """
    if check is None:
        return CheckResult("off")
    started = time.perf_counter()
    try:
        # Each line the check writes names it (step 14): its geocoding skips the cache, and Performance's count of
        # Open-Meteo's answers from the cache leaves it out.
        async with asyncio.timeout(HEALTH_CHECK_SECONDS):
            with structlog.contextvars.bound_contextvars(check=name):
                await check()
    except Exception as error:
        failure = to_failure(error)
        ms = to_ms(time.perf_counter() - started)
        error_class = type(failure).__name__
        is_new = failing.get(name) != error_class
        failing[name] = error_class
        write = log.error if isinstance(failure, NEEDS_A_LOOK) and is_new else log.warning
        write("health.check", check=name, status="down", ms=ms, errorClass=error_class)
        return CheckResult("down", ms, error_class)
    failing.pop(name, None)
    ms = to_ms(time.perf_counter() - started)
    log.info("health.check", check=name, status="ok", ms=ms)
    return CheckResult("ok", ms)


def to_lane_status(lane: LaneId, checks: Mapping[CheckName, CheckResult]) -> Status:
    """A lane's status: off when a check it needs is off, down when one failed, else ok."""
    statuses = [checks[name].status for name in CHECKS_BY_LANE[lane]]
    if "off" in statuses:
        return "off"
    return "down" if "down" in statuses else "ok"


async def check_lanes(checks: Mapping[CheckName, Check], failing: dict[CheckName, str]) -> HealthReport:
    """Runs every check at once, each within its time, and says what works; one health.done line."""
    started = time.perf_counter()
    names = list(checks)
    runs = (run_check(name, checks[name], failing) for name in names)
    results = dict(zip(names, await asyncio.gather(*runs), strict=True))
    lanes = {lane: to_lane_status(lane, results) for lane in CHECKS_BY_LANE}
    # Optional search providers have individual readiness results. Weather uptime tracks core dependencies.
    core = (result for name, result in results.items() if name not in TRAVEL_CHECKS)
    status: Literal["ok", "down"] = "down" if any(result.status == "down" for result in core) else "ok"
    log.info("health.done", status=status, ms=to_ms(time.perf_counter() - started), lanes=lanes)
    return HealthReport(status, results, lanes)


def make_checks(request: Request, mcp_url: str | None) -> dict[CheckName, Check]:
    """Probe the weather services, enabled park index and enabled travel providers' tool catalogs."""
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

    async def park_index() -> None:
        """Verify the Qdrant publication without generating embeddings or changing stored records."""
        if not isinstance(state.park_knowledge, ParkKnowledge) or await state.park_knowledge.health() != "ready":
            raise ContractError

    checks: dict[CheckName, Check] = {
        "open-meteo": open_meteo,
        "our-mcp": our_mcp,
        "apify-rest": apify_rest if token is not None else None,
        "apify-mcp": apify_mcp if token is not None else None,
        "park-index": park_index if settings.parks_enabled else None,
    }
    if settings.flights_enabled:
        checks["kiwi-mcp"] = lambda: check_provider("kiwi")
    if settings.hotels_enabled:
        checks["trivago-mcp"] = lambda: check_provider("trivago")
    return checks


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
        checking = check_lanes(make_checks(request, mcp_url), state.health_failures)
        run = runs[mcp_url or ""] = HealthRun(now, asyncio.create_task(checking))
    # Shielded: a request that goes away doesn't stop the run the others wait for.
    return await asyncio.shield(run.task)


@router.get("/api/build")
async def build_identity(request: Request) -> JSONResponse:
    """Identify the code being evaluated without running upstream health probes."""
    settings: Settings = request.app.state.settings
    sha = settings.vercel_git_commit_sha or ""
    return JSONResponse(
        {
            "environment": settings.environment,
            "commit": sha if re.fullmatch(r"[a-f0-9]{40}", sha) else None,
            "deployment": settings.public_deployment,
        },
        headers={"cache-control": NO_STORE},
    )


@router.api_route("/api/health", methods=["GET", "HEAD"])
async def health(request: Request) -> JSONResponse:
    """Report core health, optional provider checks, weather lanes and the current build to uptime monitors."""
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
