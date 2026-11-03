"""
tests/unit/test_health.py: GET /api/health (step 12): which lanes work, through the app's own ways out, played back.
Without Apify's token, the lanes with no auth work and those with auth are off; Open-Meteo down takes every lane down,
our MCP server unreachable the MCP lanes, a token Apify refuses the lanes with auth, at error; 503 for any of them,
never kept; each check within its 8 s; a run's report answering its own address for a minute, another's never; Apify's
MCP server checked against our pin; HEAD, as monitors send it.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import cast

import httpx2
import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus import health
from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.constants import HEALTH_CACHE_CONTROL
from nimbus.errors import AuthError
from nimbus.health import Check, CheckName, check_lanes, make_checks, run_check
from tests.fakes import ApifyRecordings, FakeCacheStore, OpenMeteoRecordings, make_apify_mcp_stand_in

LOCAL_MCP = "http://127.0.0.1:8000/api/mcp"
TOKEN = SecretStr("test-apify-token")


def make_app(
    settings: Settings,
    open_meteo: OpenMeteoRecordings,
    apify: ApifyRecordings | None = None,
    mcp_url: str | None = None,
) -> FastAPI:
    """The app with every way out played back: Open-Meteo, our own MCP server in this process, and Apify, if given."""
    app = create_app(settings.model_copy(update={"apify_token": TOKEN}) if apify else settings)
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    app.state.to_mcp_url = lambda _request, _settings: mcp_url
    app.state.make_mcp_http_client = lambda: httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app))
    if apify is not None:
        app.state.make_apify_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(apify))
    return app


def test_without_apify_s_token_the_lanes_with_no_auth_work_and_those_with_auth_are_off(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    with TestClient(make_app(settings, open_meteo, mcp_url=LOCAL_MCP)) as client:
        answer = client.get("/api/health")
    assert answer.status_code == 200
    assert answer.headers["cache-control"] == HEALTH_CACHE_CONTROL
    body = answer.json()
    assert (body["status"], body["commit"], body["environment"]) == ("ok", "c7165ac", "production")
    assert datetime.fromisoformat(body["checkedAt"]).tzinfo is not None
    assert body["lanes"] == {"rest-no-auth": "ok", "rest-with-auth": "off", "mcp-no-auth": "ok", "mcp-with-auth": "off"}
    assert {name: check["status"] for name, check in body["checks"].items()} == {
        "open-meteo": "ok",
        "our-mcp": "ok",
        "apify-rest": "off",
        "apify-mcp": "off",
        "park-index": "ok",
    }
    assert isinstance(body["checks"]["open-meteo"]["ms"], int)
    # Open-Meteo itself, its cache skipped: the geocoding of Paris, asked by this run and the MCP server's none.
    assert [request.url.params["name"] for request in open_meteo.requests] == ["Paris"]


def test_open_meteo_down_takes_every_lane_down_and_a_503_is_never_kept(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    open_meteo.failing = frozenset({"/v1/search"})
    with TestClient(make_app(settings, open_meteo, mcp_url=LOCAL_MCP)) as client, capture_logs() as lines:
        answer = client.get("/api/health")
    assert answer.status_code == 503
    assert answer.headers["cache-control"] == "no-store"
    body = answer.json()
    assert body["status"] == "down"
    assert (body["lanes"]["rest-no-auth"], body["lanes"]["mcp-no-auth"]) == ("down", "down")
    assert body["checks"]["open-meteo"]["errorClass"] == "UpstreamUnavailableError"
    [line] = [line for line in lines if line["event"] == "health.check" and line["check"] == "open-meteo"]
    assert (line["status"], line["log_level"]) == ("down", "warning")


def test_our_mcp_server_out_of_reach_takes_the_mcp_lanes_down(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    with TestClient(make_app(settings, open_meteo, mcp_url=None)) as client:
        body = client.get("/api/health").json()
    assert body["lanes"] == {
        "rest-no-auth": "ok",
        "rest-with-auth": "off",
        "mcp-no-auth": "down",
        "mcp-with-auth": "off",
    }
    assert body["checks"]["our-mcp"]["errorClass"] == "McpLaneError"


def test_a_token_apify_refuses_takes_the_lanes_with_auth_down_at_error(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    app = make_app(settings, open_meteo, apify=ApifyRecordings(401), mcp_url=LOCAL_MCP)
    with TestClient(app) as client, capture_logs() as lines:
        answer = client.get("/api/health")
    assert answer.status_code == 503
    body = answer.json()
    assert (body["lanes"]["rest-with-auth"], body["lanes"]["mcp-with-auth"]) == ("down", "down")
    assert body["checks"]["apify-rest"]["errorClass"] == "AuthError"
    [line] = [line for line in lines if line["event"] == "health.check" and line["check"] == "apify-rest"]
    assert line["log_level"] == "error"
    assert "test-apify-token" not in str(lines)


def test_with_apify_s_token_its_rest_door_reads_the_account_and_runs_nothing(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    apify = ApifyRecordings()
    with TestClient(make_app(settings, open_meteo, apify=apify, mcp_url=LOCAL_MCP)) as client:
        body = client.get("/api/health").json()
    assert body["checks"]["apify-rest"]["status"] == "ok"
    rest = [request for request in apify.requests if request.url.host == "api.apify.com"]
    assert [(request.method, request.url.path) for request in rest] == [("GET", "/v2/users/me")]


@pytest.mark.parametrize(("pinned", "expected"), [(True, "ok"), (False, "down")])
def test_with_apify_s_token_its_mcp_server_is_checked_against_our_pin(
    settings: Settings, pinned: bool, expected: str
) -> None:
    stand_in = make_apify_mcp_stand_in(pinned=pinned)
    state = SimpleNamespace(
        settings=settings.model_copy(update={"apify_token": TOKEN}),
        make_apify_http_client=lambda: httpx2.AsyncClient(transport=httpx2.ASGITransport(app=stand_in)),
    )
    request = cast(Request, SimpleNamespace(app=SimpleNamespace(state=state)))

    async def go() -> str:
        async with stand_in.router.lifespan_context(stand_in):
            return (await run_check("apify-mcp", make_checks(request, None)["apify-mcp"], {})).status

    assert asyncio.run(go()) == expected


def test_each_check_has_its_time_and_no_more(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "HEALTH_CHECK_SECONDS", 0.05)

    async def slow() -> None:
        await asyncio.sleep(5)

    async def fine() -> None:
        return None

    checks: dict[CheckName, Check] = {"open-meteo": fine, "our-mcp": slow, "apify-rest": None, "apify-mcp": None}
    with capture_logs() as lines:
        report = asyncio.run(check_lanes(checks, {}))
    assert report.checks["our-mcp"].error_class == "UpstreamTimeoutError"
    assert dict(report.lanes) == {
        "rest-no-auth": "ok",
        "rest-with-auth": "off",
        "mcp-no-auth": "down",
        "mcp-with-auth": "off",
    }
    [done] = [line for line in lines if line["event"] == "health.done"]
    assert done["status"] == "down"


def test_a_run_answers_its_own_address_for_a_minute_and_never_another_s(
    settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    app = make_app(settings, open_meteo, mcp_url=LOCAL_MCP)
    with TestClient(app) as client:
        first, second = client.get("/api/health").json(), client.get("/api/health").json()
        app.state.to_mcp_url = lambda _request, _settings: "http://127.0.0.1:8001/api/mcp"
        client.get("/api/health")
    assert first["checkedAt"] == second["checkedAt"]
    assert len(open_meteo.requests) == 2


def test_answers_head_as_uptime_monitors_send_it(settings: Settings, open_meteo: OpenMeteoRecordings) -> None:
    with TestClient(make_app(settings, open_meteo, mcp_url=LOCAL_MCP)) as client:
        answer = client.head("/api/health")
    assert answer.status_code == 200
    assert answer.content == b""


def test_a_check_that_keeps_failing_reaches_sentry_once_on_each_copy() -> None:
    # The review of step 12: a refused token at error each run, every 5 minutes an uptime monitor asks, would use up
    # Sentry's free quota in days. It's an error when it's new on this copy, then a warning, until the check passes.
    async def refused() -> None:
        raise AuthError

    async def fine() -> None:
        return None

    failing: dict[CheckName, str] = {}
    checks: dict[CheckName, Check] = {"open-meteo": fine, "our-mcp": fine, "apify-rest": refused, "apify-mcp": None}

    def levels() -> list[str]:
        """The apify-rest check's line's level, run once."""
        with capture_logs() as lines:
            asyncio.run(check_lanes(checks, failing))
        return [line["log_level"] for line in lines if line.get("check") == "apify-rest"]

    assert levels() + levels() == ["error", "warning"]
    checks["apify-rest"] = fine
    assert levels() == ["info"]
    checks["apify-rest"] = refused
    assert levels() == ["error"]


def test_each_line_a_check_writes_names_its_check_and_no_other_line_does() -> None:
    seen: dict[str, object] = {}

    async def check() -> None:
        seen.update(structlog.contextvars.get_contextvars())

    asyncio.run(run_check("open-meteo", check, {}))
    assert seen == {"check": "open-meteo"}
    assert "check" not in structlog.contextvars.get_contextvars()
