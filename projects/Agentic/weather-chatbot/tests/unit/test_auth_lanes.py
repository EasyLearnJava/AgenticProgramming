"""
tests/unit/test_auth_lanes.py: the lanes with auth (step 10): get_forecast by the Actor; a failure that falls back to
the twin with no auth, saying why, the forecast still given; with too little of the answer left, nothing falling back;
the other three tools the twin's; 50 s for an answer; a lane with auth closed with no token; and, through the chat, a
question on REST · with auth, from the Actor, then falling back when Apify refuses the token.
"""

import asyncio
from collections.abc import Callable, MutableMapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, SecretStr
from structlog.testing import capture_logs

from nimbus import auth_lanes
from nimbus.actor import to_actor_input
from nimbus.answer import to_answer_seconds
from nimbus.apify import ActorRun
from nimbus.app import create_app
from nimbus.auth_lanes import RunBudget, make_actor_run, to_auth_tools
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.errors import (
    AuthError,
    BudgetExceededError,
    ContractError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.lanes import LANES, REST_NO_AUTH, REST_WITH_AUTH, is_open
from nimbus.open_meteo import WireRequest
from nimbus.tools import WEATHER_TOOLS, ForecastInput, Run, ToolCallRecord, ToolRun
from tests.fakes import PARIS_STEPS, ApifyRecordings, FakeCacheStore, FakeModel, OpenMeteoRecordings, actor_items

PARIS = ForecastInput(latitude=48.85341, longitude=2.3488, days=2, include_hourly=False, units="metric")
NOW = datetime(2026, 10, 29, 15, tzinfo=UTC)
CALL = WireRequest(method="POST", url="https://api.apify.com/v2/acts", headers={}, body="{}")
TWIN = ToolRun(PARIS, WireRequest(method="GET", url="https://api.open-meteo.com/v1/forecast", headers={}), "twin's")
TOKEN = SecretStr("test-apify-token")


async def twin_run(_params: BaseModel) -> ToolRun:
    """The twin's forecast: always there."""
    return TWIN


async def actor_for_paris(actor_input: dict[str, Any]) -> ActorRun:
    """The Actor, answering for the place asked."""
    return ActorRun(actor_items(actor_input), CALL)


def run_on_rest_with_auth(run_actor: Any, seconds_left: float = 50) -> ToolRun:
    """get_forecast on REST · with auth, for Paris, with so many of the answer's seconds left."""

    async def go() -> ToolRun:
        deadline = asyncio.get_running_loop().time() + seconds_left
        budget = RunBudget(None, lambda: NOW)
        run = make_actor_run(REST_WITH_AUTH, REST_NO_AUTH, run_actor, twin_run, deadline, lambda: NOW, budget)
        return await run(PARIS)

    return asyncio.run(go())


def test_the_forecast_comes_from_the_actor() -> None:
    tool_run = run_on_rest_with_auth(actor_for_paris)
    assert (tool_run.request, tool_run.lane_id, tool_run.fallback_note) == (CALL, None, None)
    assert tool_run.summary.startswith("2 days · ")


@pytest.mark.parametrize(
    ("error", "reason", "level"),
    [
        (AuthError, "Apify didn't accept our token", "error"),
        (BudgetExceededError, "Apify's credit for this month is used up", "warning"),
        (UpstreamTimeoutError, "Apify took too long", "warning"),
        (UpstreamRateLimitedError, "Apify is busy", "warning"),
        (UpstreamUnavailableError, "Apify can't be reached", "warning"),
        (ContractError, "Apify answered in a way we didn't expect", "error"),
    ],
)
def test_a_failure_falls_back_to_the_twin_saying_why(error: type[UpstreamError], reason: str, level: str) -> None:
    make_error = cast("Callable[[], UpstreamError]", error)

    async def fail(_actor_input: dict[str, Any]) -> ActorRun:
        raise make_error()

    with capture_logs() as lines:
        tool_run = run_on_rest_with_auth(fail)
    assert tool_run.output is PARIS
    assert (tool_run.lane_id, tool_run.fallback_note) == ("rest-no-auth", f"{reason}, so REST · no auth answered")
    [line] = lines
    assert (line["event"], line["log_level"], line["fromLane"], line["toLane"]) == (
        "lane.fallback",
        level,
        "rest-with-auth",
        "rest-no-auth",
    )
    assert (line["errorClass"], line["fellBack"]) == (error.__name__, True)


def test_an_answer_the_actor_gives_for_another_place_falls_back_too() -> None:
    async def dallas(_actor_input: dict[str, Any]) -> ActorRun:
        return ActorRun(actor_items(to_actor_input(PARIS.model_copy(update={"latitude": 32.78}))), CALL)

    assert (
        run_on_rest_with_auth(dallas).fallback_note
        == "Apify answered in a way we didn't expect, so REST · no auth answered"
    )


def test_a_run_past_its_time_falls_back_as_too_slow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_lanes, "AUTH_TOOL_SECONDS", 0.05)

    async def slow(_actor_input: dict[str, Any]) -> ActorRun:
        await asyncio.sleep(2)
        return ActorRun([], CALL)

    assert run_on_rest_with_auth(slow).fallback_note == "Apify took too long, so REST · no auth answered"


def test_with_too_little_of_the_answer_left_nothing_falls_back() -> None:
    async def fail(_actor_input: dict[str, Any]) -> ActorRun:
        raise AuthError

    with capture_logs() as lines, pytest.raises(AuthError):
        run_on_rest_with_auth(fail, seconds_left=5)
    assert [line["fellBack"] for line in lines] == [False]


def test_the_other_three_tools_are_the_twin_s() -> None:
    async def go() -> list[ToolMessage]:
        deadline = asyncio.get_running_loop().time() + 50
        runs: dict[str, Run] = {tool.name: twin_run for tool in WEATHER_TOOLS}
        tools = to_auth_tools(REST_WITH_AUTH, REST_NO_AUTH, runs, actor_for_paris, deadline, lambda: NOW, None)
        calls = {"geocode_location": {"query": "Paris"}, "get_forecast": PARIS.model_dump()}
        messages = []
        for tool in tools:
            if tool.name in calls:
                call = {"type": "tool_call", "id": "call-0-0", "name": tool.name, "args": calls[tool.name]}
                message = await tool.ainvoke(call)
                assert isinstance(message, ToolMessage)
                messages.append(message)
        return messages

    geocode, forecast = asyncio.run(go())
    assert isinstance(geocode.artifact, ToolCallRecord)
    assert isinstance(forecast.artifact, ToolCallRecord)
    assert (geocode.artifact.lane, forecast.artifact.lane) == ("rest-no-auth", "rest-with-auth")


def test_an_answer_on_a_lane_with_auth_has_50_seconds_and_30_elsewhere() -> None:
    assert (to_answer_seconds(REST_WITH_AUTH), to_answer_seconds(REST_NO_AUTH)) == (50, 30)


def test_a_lane_with_auth_is_open_only_with_apify_s_token(settings: Settings) -> None:
    with_token = settings.model_copy(update={"apify_token": TOKEN})
    assert [is_open(lane, settings) for lane in LANES] == [True, False, True, False]
    assert all(is_open(lane, with_token) for lane in LANES)


def apify_app(
    settings: Settings,
    chat_model: FakeModel,
    open_meteo: OpenMeteoRecordings,
    cache_store: FakeCacheStore,
    apify: ApifyRecordings,
) -> FastAPI:
    """The app with Apify's token, its tools calling the stand-ins for Open-Meteo and for Apify."""
    app = create_app(settings.model_copy(update={"apify_token": TOKEN}))
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(cache_store)
    app.state.make_apify_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(apify))
    return app


def ask_on_rest_with_auth(app: FastAPI, chat_model: FakeModel) -> tuple[str, list[MutableMapping[str, Any]]]:
    """The Paris question on REST · with auth: the answer's events, and the log lines."""
    chat_model.tool_steps = PARIS_STEPS
    with TestClient(app) as client, capture_logs() as lines:
        form = {"question": "Will it rain in Paris tomorrow?", "lane": "rest-with-auth"}
        answer = client.post("/api/chat", data=form)
    assert answer.status_code == 200
    return answer.text, lines


def test_a_question_on_rest_with_auth_gets_its_forecast_from_the_actor(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore
) -> None:
    apify = ApifyRecordings()
    text, lines = ask_on_rest_with_auth(apify_app(settings, chat_model, open_meteo, cache_store, apify), chat_model)
    assert "REST · with auth · api.apify.com · " in text
    assert "REST · no auth · geocoding-api.open-meteo.com · " in text
    assert len(apify.requests) == 1
    calls = {line["tool"]: line["lane"] for line in lines if line["event"] == "tool.call"}
    assert calls == {"geocode_location": "rest-no-auth", "get_forecast": "rest-with-auth"}


def test_a_question_on_rest_with_auth_falls_back_when_apify_refuses_the_token(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore
) -> None:
    app = apify_app(settings, chat_model, open_meteo, cache_store, ApifyRecordings(401))
    text, lines = ask_on_rest_with_auth(app, chat_model)
    assert "↩ Apify didn&#39;t accept our token, so REST · no auth answered" in text
    assert "REST · no auth · api.open-meteo.com · " in text
    [forecast] = [line for line in lines if line["event"] == "tool.call" and line["tool"] == "get_forecast"]
    assert (forecast["lane"], forecast["fallbackFrom"]) == ("rest-no-auth", "rest-with-auth")


def run_three_forecasts(cache: WeatherCache | None) -> tuple[list[ToolRun], int]:
    """Three forecasts in one answer, with the cache given: their runs, and how many reached the Actor."""
    started = 0

    async def counted(actor_input: dict[str, Any]) -> ActorRun:
        nonlocal started
        started += 1
        return await actor_for_paris(actor_input)

    async def go() -> list[ToolRun]:
        deadline = asyncio.get_running_loop().time() + 50
        budget = RunBudget(cache, lambda: NOW)
        run = make_actor_run(REST_WITH_AUTH, REST_NO_AUTH, counted, twin_run, deadline, lambda: NOW, budget)
        return [await run(PARIS) for _ in range(3)]

    return asyncio.run(go()), started


def test_an_answer_starts_two_actor_runs_at_most_then_the_twin_answers() -> None:
    first, second, third = (run.fallback_note for run in run_three_forecasts(None)[0])
    assert (first, second) == (None, None)
    assert third == "This answer's two Actor runs are used up, so REST · no auth answered"
    assert run_three_forecasts(None)[1] == 2


def test_the_day_s_runs_are_counted_in_the_cache_until_utc_midnight_and_capped_at_25() -> None:
    store = FakeCacheStore()
    cache = WeatherCache(store)
    runs, started = run_three_forecasts(cache)
    assert started == 2
    [ttl] = store.ttls.values()
    assert ttl == 9 * 60 * 60
    assert list(store.items.values()) == [2]
    store.items[next(iter(store.items))] = 25
    runs, started = run_three_forecasts(cache)
    assert started == 0
    assert runs[0].fallback_note == "Today's Actor runs are used up, so REST · no auth answered"
