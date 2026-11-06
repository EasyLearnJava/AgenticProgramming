"""
tests/unit/test_mcp_lane.py: the MCP · no auth lane (step 9), against our own MCP server in this process, as the chat
reaches it: our four tools, each call a tools/call whose answer becomes the tool's run, with the request the client
sent and the one the server sent Open-Meteo, and the cache's part; a failure as the same error as on REST; a server
that can't be reached, or lacks one of our tools, McpLaneError; an error the answer raises, as itself, never wrapped;
the secret masked; the chip's request the one the lane sends; and where the lane finds the server, never where
a request's Host says.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool, ToolException
from mcp_types import CallToolResult, TextContent
from pydantic import SecretStr
from starlette.requests import Request
from structlog.testing import capture_logs

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.errors import WEATHER_UNREACHABLE, AnswerTimeoutError, McpLaneError
from nimbus.mcp_lane import (
    MASKED_BYPASS,
    open_mcp_lane,
    to_self_mcp_url,
    to_tool_run,
    to_tools_call,
    to_wire_request,
    unwrap,
)
from nimbus.tools import WEATHER_TOOLS, ToolCallRecord
from tests.fakes import FakeCacheStore, OpenMeteoRecordings

LOCAL_MCP = "http://127.0.0.1:8000/api/mcp"
DELHI = {"latitude": 28.65, "longitude": 77.23}


def lane_app(settings: Settings, open_meteo: OpenMeteoRecordings, without: str | None = None) -> FastAPI:
    """
    Our app, its tools calling the stand-in for Open-Meteo, one of its MCP tools taken away if a test says so. Built
    before a test captures its logs: building it sets the logging up again.
    """
    app = create_app(settings)
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    if without is not None:
        app.state.mcp_server.remove_tool(without)
    return app


def through_the_lane[T](
    app: FastAPI, run: Callable[[list[StructuredTool]], Awaitable[T]], secret: SecretStr | None = None
) -> T:
    """
    Runs with the lane open on the app's MCP server, in this process. An error the lane lets out is raised again once
    the app's lifespan has ended: the SDK's session manager, which the lifespan runs, would wrap it in a group.
    """

    async def go() -> T:
        failure: Exception
        async with app.router.lifespan_context(app):
            http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app))
            try:
                async with open_mcp_lane(LOCAL_MCP, http, secret) as tools:
                    return await run(tools)
            except Exception as error:
                failure = error
        raise failure

    return asyncio.run(go())


async def call(tools: list[StructuredTool], name: str, args: dict[str, Any]) -> ToolMessage:
    """One tool call, as the agent makes it: a ToolMessage, with the call's record as its artifact."""
    tool = next(tool for tool in tools if tool.name == name)
    message = await tool.ainvoke({"type": "tool_call", "id": "call-0-0", "name": name, "args": args})
    assert isinstance(message, ToolMessage)
    return message


def record_of(message: ToolMessage) -> ToolCallRecord:
    """The record a call's message carries."""
    assert isinstance(message.artifact, ToolCallRecord)
    return message.artifact


async def keep(tools: list[StructuredTool]) -> list[StructuredTool]:
    """The lane's tools, as they are."""
    return tools


def test_the_lane_offers_our_four_tools_with_their_own_names_and_inputs(settings: Settings) -> None:
    tools = through_the_lane(lane_app(settings, OpenMeteoRecordings()), keep)
    assert [(tool.name, tool.args_schema) for tool in tools] == [
        (tool.name, tool.input_model) for tool in WEATHER_TOOLS
    ]


def test_a_call_goes_to_our_server_as_a_tools_call_and_brings_back_the_weather(settings: Settings) -> None:
    open_meteo = OpenMeteoRecordings()
    app = lane_app(settings, open_meteo)
    with capture_logs() as lines:
        message = through_the_lane(app, lambda tools: call(tools, "get_air_quality", DELHI))
    record = record_of(message)
    assert json.loads(str(message.content))["us_aqi"] is not None
    assert (record.lane, record.summary, record.from_cache) == ("mcp-no-auth", "US AQI 131 · European AQI 45", False)
    assert (record.request.method, record.request.url) == ("POST", LOCAL_MCP)
    sent = json.loads(record.request.body or "{}")
    assert (sent["method"], sent["params"]["name"], sent["params"]["arguments"]) == (
        "tools/call",
        "get_air_quality",
        DELHI,
    )
    assert record.upstream_request is not None
    assert record.upstream_request.url == str(open_meteo.requests[0].url)
    [line] = [line for line in lines if line["event"] == "tool.call"]
    assert (line["tool"], line["lane"], line["status"]) == ("get_air_quality", "mcp-no-auth", "ok")


def test_the_same_call_again_says_the_cache_answered(settings: Settings) -> None:
    open_meteo = OpenMeteoRecordings()

    async def twice(tools: list[StructuredTool]) -> list[ToolMessage]:
        return [await call(tools, "get_air_quality", DELHI) for _ in range(2)]

    first, again = through_the_lane(lane_app(settings, open_meteo), twice)
    assert (record_of(first).from_cache, record_of(again).from_cache) == (False, True)
    assert len(open_meteo.requests) == 1


def test_a_call_open_meteo_fails_is_the_same_error_as_on_rest(settings: Settings) -> None:
    app = lane_app(settings, OpenMeteoRecordings(failing=frozenset({"/v1/air-quality"})))
    with capture_logs() as lines:
        message = through_the_lane(app, lambda tools: call(tools, "get_air_quality", DELHI))
    assert (message.status, message.content) == ("error", WEATHER_UNREACHABLE)
    [line] = [line for line in lines if line["event"] == "tool.call"]
    assert (line["lane"], line["status"], line["errorClass"]) == ("mcp-no-auth", "failed", "UpstreamUnavailableError")


def test_an_error_the_answer_raises_comes_out_as_itself_never_wrapped(settings: Settings) -> None:
    # The SDK's client runs in a task group, which would wrap it: the chat must still know it (issue 64).
    async def time_out(_tools: list[StructuredTool]) -> None:
        raise AnswerTimeoutError

    with pytest.raises(AnswerTimeoutError):
        through_the_lane(lane_app(settings, OpenMeteoRecordings()), time_out)


def test_unwrap_gives_the_error_in_a_group_of_one_or_a_bigger_one_s_ending_else_mcp_lane_error() -> None:
    error = McpLaneError()
    assert unwrap(BaseExceptionGroup("outer", [BaseExceptionGroup("inner", [error])])) is error
    closing = GeneratorExit()
    assert unwrap(BaseExceptionGroup("two", [McpLaneError(), BaseExceptionGroup("in", [closing])])) is closing
    two = ExceptionGroup("two", [McpLaneError(), AnswerTimeoutError()])
    failure = unwrap(two)
    assert isinstance(failure, McpLaneError)
    assert failure.__cause__ is two


def test_an_error_answer_naming_no_class_we_know_is_a_tool_error_with_the_server_s_text() -> None:
    # Our schema and the server's agree today; if they drift, the server refuses the input with a text of its own.
    text = "Error executing tool get_forecast: 1 validation error for get_forecastArguments"
    result = CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)
    with pytest.raises(ToolException, match="validation error"):
        to_tool_run(result, to_tools_call(LOCAL_MCP, "get_forecast", {}))


def test_a_chip_masks_a_credential_and_a_cookie_as_well_as_the_bypass_secret() -> None:
    headers = {"authorization": "Bearer t0ken", "cookie": "_vercel_jwt=abc", "x-vercel-protection-bypass": "s3cret"}
    request = httpx2.Request("POST", LOCAL_MCP, headers=headers, content=b'{"jsonrpc": "2.0"}')
    shown = to_wire_request(request).headers
    assert (shown["authorization"], shown["cookie"], shown["x-vercel-protection-bypass"]) == (
        "<masked>",
        "<masked>",
        MASKED_BYPASS,
    )


def test_the_bypass_secret_goes_with_each_call_and_a_chip_shows_it_masked(settings: Settings) -> None:
    secret = SecretStr("s3cret-bypass-value")
    app = lane_app(settings, OpenMeteoRecordings())
    message = through_the_lane(app, lambda tools: call(tools, "get_air_quality", DELHI), secret)
    request = record_of(message).request
    assert request.headers["x-vercel-protection-bypass"] == MASKED_BYPASS
    assert "s3cret-bypass-value" not in request.to_text()


def test_a_server_without_one_of_our_tools_is_mcp_lane_error(settings: Settings) -> None:
    with pytest.raises(McpLaneError):
        through_the_lane(lane_app(settings, OpenMeteoRecordings(), without="get_air_quality"), keep)


@pytest.mark.parametrize("url", [LOCAL_MCP, None], ids=["refused", "no-address"])
def test_a_server_that_cant_be_reached_is_mcp_lane_error(url: str | None) -> None:
    async def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    async def go() -> None:
        async with open_mcp_lane(url, httpx2.AsyncClient(transport=httpx2.MockTransport(refuse))):
            pass

    with pytest.raises(McpLaneError):
        asyncio.run(go())


def test_the_chip_s_request_is_the_one_the_lane_sends(settings: Settings) -> None:
    # The chip's message and headers, as the lane makes them; the SDK's client adds its own beside them.
    message = through_the_lane(lane_app(settings, OpenMeteoRecordings()), lambda t: call(t, "get_air_quality", DELHI))
    sent = record_of(message).request
    shown = to_tools_call(LOCAL_MCP, "get_air_quality", DELHI)
    assert (shown.method, shown.url) == (sent.method, sent.url)
    assert {name: sent.headers.get(name) for name in shown.headers} == shown.headers
    sent_body, shown_body = json.loads(sent.body or "{}"), json.loads(shown.body or "{}")
    assert sent_body["method"] == shown_body["method"]
    assert {key: sent_body["params"][key] for key in ("name", "arguments")} == shown_body["params"]


def to_request(host: str, server: tuple[str, int] = ("127.0.0.1", 8000), forwarded: str | None = None) -> Request:
    """A request to the chat, with a Host header, maybe Vercel's forwarded one, as served on the address given."""
    headers = [(b"host", host.encode())]
    if forwarded is not None:
        headers.append((b"x-forwarded-host", forwarded.encode()))
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": headers, "server": server})


VERCEL = Settings(
    _env_file=None,
    is_vercel=True,
    vercel_url="weather-chatbot-abc123-silverado.vercel.app",
    vercel_project_production_url="weather-chatbot-hazel.vercel.app",
)


@pytest.mark.parametrize(
    ("request_", "settings", "url"),
    [
        (to_request("weather-chatbot-hazel.vercel.app"), VERCEL, "https://weather-chatbot-hazel.vercel.app/api/mcp"),
        (
            to_request("internal", forwarded="weather-chatbot-hazel.vercel.app"),
            VERCEL,
            "https://weather-chatbot-hazel.vercel.app/api/mcp",
        ),
        (to_request("evil.example"), VERCEL, "https://weather-chatbot-abc123-silverado.vercel.app/api/mcp"),
        (to_request("evil.example"), Settings(_env_file=None, is_vercel=True), None),
        (to_request("evil.example"), Settings(_env_file=None), "http://127.0.0.1:8000/api/mcp"),
        (to_request("localhost", server=("::1", 5173)), Settings(_env_file=None), "http://[::1]:5173/api/mcp"),
    ],
    ids=[
        "vercel-its-production-name",
        "vercel-its-name-forwarded",
        "vercel-a-forged-name-gets-the-deployment-s-own",
        "vercel-with-no-name-none",
        "a-computer-its-own-address-never-the-host-s",
        "a-computer-ipv6",
    ],
)
def test_the_lane_finds_our_server_on_this_deployment_never_where_a_host_says(
    request_: Request, settings: Settings, url: str | None
) -> None:
    assert to_self_mcp_url(request_, settings) == url
