"""
nimbus/auth_lanes.py: the two lanes with auth (step 10), REST · with auth and MCP · with auth. Each runs get_forecast
through Apify's Actor, over Apify's REST API or its MCP server (nimbus/apify.py); the Actor has no geocoding, no weather
now and no air, so the lane's other three tools are its twin's, the same door with no auth. When the Actor's call
fails, the forecast doesn't: one lane.fallback line says why, and the twin's get_forecast answers in its own 8 s, if the
answer still has 12 s; the chip says so. A run is never retried or cached: each one costs, and the twin answers anyway.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, Final

import httpx2
import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, SecretStr

from nimbus.actor import summarize_actor_forecast, to_actor_input, to_forecast
from nimbus.apify import ActorRun, open_apify_mcp, run_actor_rest
from nimbus.cache import WeatherCache
from nimbus.constants import APIFY_RUNS_PER_ANSWER, APIFY_RUNS_PER_DAY, AUTH_TOOL_SECONDS, FALLBACK_MIN_LEFT_SECONDS
from nimbus.errors import (
    APIFY_ANSWER_RUNS_USED,
    APIFY_BUSY,
    APIFY_CREDIT_USED,
    APIFY_DAY_RUNS_USED,
    APIFY_TOKEN_REFUSED,
    APIFY_TOO_SLOW,
    APIFY_UNEXPECTED,
    APIFY_UNREACHABLE,
    AuthError,
    BudgetExceededError,
    ContractError,
    RunsUsedUpError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.lanes import MCP_NO_AUTH, MCP_WITH_AUTH, REST_NO_AUTH, REST_WITH_AUTH, Lane
from nimbus.mcp_lane import open_mcp_runs
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import (
    GET_FORECAST,
    WEATHER_TOOLS,
    ForecastInput,
    Run,
    ToolContext,
    ToolRun,
    rest_runs,
    to_langchain_tool,
    utc_now,
)
from nimbus.utils import to_ms

log = structlog.get_logger()

# Why a forecast fell back, as its chip says it, by the Actor call's error.
REASONS: Final[dict[type[UpstreamError], str]] = {
    AuthError: APIFY_TOKEN_REFUSED,
    BudgetExceededError: APIFY_CREDIT_USED,
    UpstreamTimeoutError: APIFY_TOO_SLOW,
    UpstreamRateLimitedError: APIFY_BUSY,
    UpstreamUnavailableError: APIFY_UNREACHABLE,
    ContractError: APIFY_UNEXPECTED,
}
# The failures that need someone to look: the token, and an answer we can't read; the others pass.
NEEDS_A_LOOK: Final = (AuthError, ContractError)

RunActor = Callable[[dict[str, Any]], Awaitable[ActorRun]]


@dataclass
class RunBudget:
    """
    The Actor runs an answer may still start (issue 66): 2 an answer, and 25 a day across the app, counted in the
    weather's cache, which every copy shares. The day's count is near enough: two copies starting at once may both
    take the last run, and a cache that fails counts nothing, while the answer's 2 still hold.
    """

    cache: WeatherCache | None
    now: Callable[[], datetime]
    left_in_answer: int = APIFY_RUNS_PER_ANSWER

    async def take(self) -> None:
        """Takes one run; with none left, RunsUsedUpError, saying whose: the answer's, or the day's."""
        if self.left_in_answer <= 0:
            raise RunsUsedUpError(APIFY_ANSWER_RUNS_USED)
        self.left_in_answer -= 1
        if self.cache is None:
            return
        now = self.now().astimezone(UTC)
        key = f"apify-runs:{now.date().isoformat()}"
        kept = await self.cache.get(key)
        runs = kept if isinstance(kept, int) else 0
        if runs >= APIFY_RUNS_PER_DAY:
            raise RunsUsedUpError(APIFY_DAY_RUNS_USED)
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        await self.cache.set(key, runs + 1, max(1, int((midnight - now).total_seconds())))


def make_actor_run(
    lane: Lane,
    twin: Lane,
    run_actor: RunActor,
    twin_run: Run,
    deadline: float,
    now: Callable[[], datetime],
    budget: RunBudget,
) -> Run:
    """
    get_forecast on a lane with auth: a run from the budget, the Actor's run within 20 s, its items as the forecast; a
    failure, or no run left, falls back to the twin's get_forecast, if the answer still has 12 s, with the reason for
    the chip.
    """

    async def run(params: BaseModel) -> ToolRun:
        """The forecast, by the Actor; or by the twin, saying why."""
        forecast = params if isinstance(params, ForecastInput) else ForecastInput.model_validate(params.model_dump())
        try:
            await budget.take()
            async with asyncio.timeout(AUTH_TOOL_SECONDS):
                actor_run = await run_actor(to_actor_input(forecast))
            output = to_forecast(actor_run.items, forecast, now())
            return ToolRun(output, actor_run.request, summarize_actor_forecast(output))
        except TimeoutError as error:
            failure: UpstreamError = UpstreamTimeoutError()
            failure.__cause__ = error
        except UpstreamError as error:
            failure = error
        left = deadline - asyncio.get_running_loop().time()
        falls_back = left >= FALLBACK_MIN_LEFT_SECONDS
        write = log.error if isinstance(failure, NEEDS_A_LOOK) else log.warning
        moved = {"fromLane": lane.id, "toLane": twin.id, "errorClass": type(failure).__name__}
        write("lane.fallback", **moved, fellBack=falls_back, msLeft=to_ms(left))
        if not falls_back:
            raise failure
        answer = await twin_run(forecast)
        reason = REASONS.get(type(failure), APIFY_UNREACHABLE)
        if isinstance(failure, RunsUsedUpError):
            reason = failure.reason
        return replace(answer, lane_id=twin.id, fallback_note=f"{reason}, so {twin.label} answered")

    return run


def to_auth_tools(
    lane: Lane,
    twin: Lane,
    twin_runs: dict[str, Run],
    run_actor: RunActor,
    deadline: float,
    now: Callable[[], datetime],
    cache: WeatherCache | None,
) -> list[StructuredTool]:
    """
    The lane's four tools, for one answer: get_forecast by the Actor, from this answer's run budget, falling back to
    the twin's; the other three, the twin's.
    """
    budget = RunBudget(cache, now)
    forecast = make_actor_run(lane, twin, run_actor, twin_runs[GET_FORECAST.name], deadline, now, budget)
    runs = {**twin_runs, GET_FORECAST.name: forecast}
    return [to_langchain_tool(tool, runs[tool.name], lane if tool is GET_FORECAST else twin) for tool in WEATHER_TOOLS]


@asynccontextmanager
async def open_rest_with_auth(
    http_client: httpx2.AsyncClient,
    weather_cache: WeatherCache | None,
    apify_http_client: httpx2.AsyncClient,
    token: SecretStr,
    deadline: float,
) -> AsyncIterator[list[StructuredTool]]:
    """REST · with auth: the Actor over Apify's REST API; the other tools, and the fallback, REST · no auth's."""
    async with http_client as http, apify_http_client as apify_http:
        context = ToolContext(OpenMeteoClient(http, cache=weather_cache))
        run_actor = partial(run_actor_rest, apify_http, token)
        runs = rest_runs(context)
        yield to_auth_tools(REST_WITH_AUTH, REST_NO_AUTH, runs, run_actor, deadline, context.now, weather_cache)


@asynccontextmanager
async def open_mcp_with_auth(
    url: str | None,
    mcp_http_client: httpx2.AsyncClient,
    bypass_secret: SecretStr | None,
    apify_http_client: httpx2.AsyncClient,
    token: SecretStr,
    deadline: float,
    weather_cache: WeatherCache | None,
) -> AsyncIterator[list[StructuredTool]]:
    """MCP · with auth: the Actor through Apify's MCP server; the other tools, and the fallback, MCP · no auth's."""
    async with (
        open_mcp_runs(url, mcp_http_client, bypass_secret) as twin_runs,
        open_apify_mcp(apify_http_client, token) as apify,
    ):
        yield to_auth_tools(MCP_WITH_AUTH, MCP_NO_AUTH, twin_runs, apify.run_actor, deadline, utc_now, weather_cache)
