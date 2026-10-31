"""
tests/unit/test_apify.py: Apify's two doors (step 10), played back. REST: the run's request, its limits in the address,
the token only in a header, masked for the chip; each status as one of our errors, Apify's own words logged for an
account's problem only. MCP, against a stand-in of Apify's MCP server with sessions: call-actor, then get-dataset-items;
our pin; an error result that says the account can't pay; a run still going, or failed; a dataset bigger than one
read; a server that refuses the token.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from structlog.testing import capture_logs

from nimbus.apify import (
    APIFY_MCP_HOST,
    ActorRun,
    has_field,
    open_apify_mcp,
    run_actor_rest,
    to_run_url,
)
from nimbus.errors import (
    AuthError,
    BudgetExceededError,
    ContractError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from tests.fakes import ApifyRecordings, actor_items, apify_answer, make_apify_mcp_stand_in

TOKEN = SecretStr("test-apify-token")
DALLAS = {
    "locations": [{"name": "32.78, -96.8", "latitude": 32.78, "longitude": -96.8}],
    "forecastDays": 2,
    "mode": "daily",
}


def over_rest(recordings: ApifyRecordings) -> ActorRun:
    """One run over the REST door, against the recordings."""

    async def go() -> ActorRun:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(recordings)) as http:
            return await run_actor_rest(http, TOKEN, DALLAS)

    return asyncio.run(go())


def test_a_run_over_rest_pins_its_limits_sends_the_token_in_a_header_and_masks_it_for_the_chip() -> None:
    recordings = ApifyRecordings()
    with capture_logs() as lines:
        run = over_rest(recordings)
    [sent] = recordings.requests
    assert str(sent.url) == to_run_url()
    assert sent.url.params["build"] == "1.0.9"
    assert (sent.url.params["timeout"], sent.url.params["maxTotalChargeUsd"]) == ("18", "0.01")
    assert sent.headers["authorization"] == "Bearer test-apify-token"
    assert json.loads(sent.content) == DALLAS
    assert run.items == actor_items(DALLAS)
    assert run.request.headers["authorization"] == "Bearer <APIFY_TOKEN>"
    assert "test-apify-token" not in run.request.to_text()
    assert "test-apify-token" not in str(lines)
    [line] = lines
    assert (line["event"], line["upstream"], line["status"], line["items"]) == ("upstream.http", "apify", "ok", 2)


@pytest.mark.parametrize(
    ("status", "error", "words"),
    [
        (401, AuthError, "user-or-token-not-found (User was not found or authentication token is not valid)"),
        (402, BudgetExceededError, "stand-in-error (Paris, quoted)"),
        (403, AuthError, "stand-in-error (Paris, quoted)"),
        (408, UpstreamTimeoutError, "stand-in-error"),
        (429, UpstreamRateLimitedError, "stand-in-error"),
        (503, UpstreamUnavailableError, "stand-in-error"),
        (400, ContractError, "stand-in-error"),
    ],
)
def test_each_status_is_one_of_our_errors_and_only_an_account_s_problem_keeps_apify_s_message(
    status: int, error: type[UpstreamError], words: str
) -> None:
    with capture_logs() as lines, pytest.raises(error):
        over_rest(ApifyRecordings(status))
    [line] = lines
    assert (line["httpStatus"], line["errorClass"], line["apifyError"]) == (status, error.__name__, words)


def through_mcp[T](stand_in: Starlette, run: Callable[[Any], Awaitable[T]]) -> T:
    """Runs with a connection open to the stand-in of Apify's MCP server, in this process."""

    async def go() -> T:
        failure: Exception
        async with stand_in.router.lifespan_context(stand_in):
            http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=stand_in))
            try:
                async with open_apify_mcp(http, TOKEN) as apify:
                    return await run(apify)
            except Exception as error:
                failure = error
        raise failure

    return asyncio.run(go())


def test_a_run_over_mcp_is_call_actor_then_get_dataset_items_and_the_chip_gets_call_actor_s_request() -> None:
    with capture_logs() as lines:
        run = through_mcp(make_apify_mcp_stand_in(), lambda apify: apify.run_actor(DALLAS))
    assert run.items == actor_items(DALLAS)
    sent = json.loads(run.request.body or "{}")
    assert (sent["method"], sent["params"]["name"]) == ("tools/call", "call-actor")
    arguments = sent["params"]["arguments"]
    assert (arguments["actor"], arguments["input"], arguments["waitSecs"]) == (
        "gochujang/open-meteo-weather-forecast",
        DALLAS,
        18,
    )
    assert arguments["callOptions"] == {"build": "1.0.9", "timeout": 18, "maxTotalChargeUsd": 0.01}
    assert run.request.headers["authorization"] == "<masked>"
    assert run.request.headers["mcp-session-id"] == "<masked>"
    assert "test-apify-token" not in run.request.to_text()
    assert "test-apify-token" not in str(lines)
    events = [(line["event"], line.get("tool"), line["status"]) for line in lines]
    assert events == [
        ("lane.connect", None, "ok"),
        ("upstream.mcp", "call-actor", "ok"),
        ("upstream.mcp", "get-dataset-items", "ok"),
    ]
    assert {line["host"] for line in lines} == {APIFY_MCP_HOST}


@pytest.mark.parametrize(
    ("stand_in", "error"),
    [
        (make_apify_mcp_stand_in(pinned=False), ContractError),
        (make_apify_mcp_stand_in(error_text="Not enough usage credit to run the Actor."), BudgetExceededError),
        (make_apify_mcp_stand_in(error_text="Input is not valid."), ContractError),
        (make_apify_mcp_stand_in(run_status="RUNNING"), UpstreamTimeoutError),
        (make_apify_mcp_stand_in(run_status="FAILED"), UpstreamUnavailableError),
        (make_apify_mcp_stand_in(total_items=500), ContractError),
    ],
    ids=["no-pin", "credit-used-up", "another-error", "still-running", "failed", "more-than-one-read"],
)
def test_a_run_over_mcp_that_can_t_be_trusted_is_one_of_our_errors(stand_in: Starlette, error: type[Exception]) -> None:
    with pytest.raises(error):
        through_mcp(stand_in, lambda apify: apify.run_actor(DALLAS))


def test_a_server_that_refuses_the_token_gives_a_connection_whose_run_is_an_auth_error() -> None:
    async def refuse(_request: Request) -> JSONResponse:
        recorded = apify_answer("mcp-401-no-token")
        return JSONResponse(recorded["body"], status_code=401)

    stand_in = Starlette(routes=[Route("/", refuse, methods=["GET", "POST", "DELETE"])])
    with capture_logs() as lines, pytest.raises(AuthError):
        through_mcp(stand_in, lambda apify: apify.run_actor(DALLAS))
    [line] = lines
    assert (line["event"], line["status"], line["errorClass"]) == ("lane.connect", "failed", "AuthError")


def test_a_field_is_found_through_refs_and_optional_unions() -> None:
    schema = {
        "properties": {"callOptions": {"anyOf": [{"$ref": "#/$defs/CallOptions"}, {"type": "null"}]}},
        "$defs": {"CallOptions": {"properties": {"build": {"type": "string"}}}},
    }
    assert has_field(schema, "callOptions.build")
    assert not has_field(schema, "callOptions.timeout")
    assert not has_field({}, "actor")
