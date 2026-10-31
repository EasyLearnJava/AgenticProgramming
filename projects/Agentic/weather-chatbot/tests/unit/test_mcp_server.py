"""
tests/unit/test_mcp_server.py: our MCP server (step 8), through the official SDK's client. In this process: its four
tools, each input schema its tool's own model (the contract: a changed schema fails here), and its answers: the
weather, the summary and _meta, the cache's the second time, and our sentence and class when Open-Meteo fails. Over
HTTP, through the whole app, as any MCP client reaches /api/mcp: the protocol it agrees, a body's limit, no batch, and
no CORS allowance for a page elsewhere.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult
from starlette.datastructures import State
from structlog.testing import capture_logs

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.errors import UpstreamUnavailableError
from nimbus.mcp_server import make_mcp_server
from nimbus.tools import WEATHER_TOOLS
from tests.fakes import FakeCacheStore, FakeModel, OpenMeteoRecordings

DELHI = {"latitude": 28.65, "longitude": 77.23}
# On a computer, the app takes MCP requests only by the names 127.0.0.1 and localhost (issue 62).
LOCAL = "http://127.0.0.1:8000"
JSON_RPC = {
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
    "host": "127.0.0.1:8000",
}


def in_process[T](open_meteo: OpenMeteoRecordings, run: Callable[[Client], Awaitable[T]]) -> T:
    """Runs a client against the server in this process, its tools calling the stand-in for Open-Meteo."""
    state = State()
    state.settings = Settings(_env_file=None, vercel_git_commit_sha="c7165ac9d2b84e1f")
    state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    state.weather_cache = WeatherCache(FakeCacheStore())

    async def go() -> T:
        async with Client(make_mcp_server(state)) as client:
            return await run(client)

    return asyncio.run(go())


def call(open_meteo: OpenMeteoRecordings, name: str, arguments: dict[str, Any]) -> CallToolResult:
    """One tool call, in this process."""
    return in_process(open_meteo, lambda client: client.call_tool(name, arguments))


def test_the_server_offers_our_four_tools_each_with_its_own_input_schema() -> None:
    listed = in_process(OpenMeteoRecordings(), lambda client: client.list_tools())
    assert [tool.name for tool in listed.tools] == [tool.name for tool in WEATHER_TOOLS]
    for offered, ours in zip(listed.tools, WEATHER_TOOLS, strict=True):
        schema = ours.input_model.model_json_schema()
        assert offered.description == ours.description
        assert offered.input_schema["properties"] == schema["properties"]
        assert offered.input_schema.get("required", []) == schema.get("required", [])
        assert offered.annotations is not None
        assert (offered.annotations.read_only_hint, offered.annotations.open_world_hint) == (True, True)


def test_a_call_answers_with_the_weather_its_summary_and_its_request_in_meta() -> None:
    open_meteo = OpenMeteoRecordings()
    with capture_logs() as lines:
        result = call(open_meteo, "get_air_quality", DELHI)
    assert result.is_error is False
    assert [getattr(block, "text", None) for block in result.content] == ["US AQI 131 · European AQI 45"]
    assert result.structured_content is not None
    assert result.meta is not None
    assert result.meta["fromCache"] is False
    assert result.meta["request"]["url"] == str(open_meteo.requests[0].url)
    [line] = [line for line in lines if line["event"] == "mcp.call"]
    assert {key: line[key] for key in ("tool", "status", "fromCache")} == {
        "tool": "get_air_quality",
        "status": "ok",
        "fromCache": False,
    }
    assert "28.65" not in str(line)


def test_the_same_call_again_comes_from_the_cache_without_asking_open_meteo() -> None:
    open_meteo = OpenMeteoRecordings()

    async def twice(client: Client) -> list[CallToolResult]:
        return [await client.call_tool("get_air_quality", DELHI) for _ in range(2)]

    first, again = in_process(open_meteo, twice)
    assert first.meta is not None
    assert again.meta is not None
    assert (first.meta["fromCache"], again.meta["fromCache"]) == (False, True)
    assert again.structured_content == first.structured_content
    assert len(open_meteo.requests) == 1


def test_a_tool_that_fails_answers_with_our_sentence_and_its_class_in_meta() -> None:
    open_meteo = OpenMeteoRecordings(failing=frozenset({"/v1/air-quality"}))
    with capture_logs() as lines:
        result = call(open_meteo, "get_air_quality", DELHI)
    assert result.is_error is True
    assert [getattr(block, "text", None) for block in result.content] == [UpstreamUnavailableError().user_message]
    assert result.meta is not None
    assert result.meta["errorClass"] == "UpstreamUnavailableError"
    # The SDK adds the server's name and version: the build that answered.
    assert result.meta["io.modelcontextprotocol/serverInfo"] == {"name": "nimbus-weather", "version": "c7165ac"}
    [line] = [line for line in lines if line["event"] == "mcp.call"]
    assert (line["status"], line["errorClass"]) == ("failed", "UpstreamUnavailableError")


def test_input_its_model_refuses_is_an_error_that_names_the_field() -> None:
    result = call(OpenMeteoRecordings(), "get_air_quality", {"latitude": 99, "longitude": 77.23})
    assert result.is_error is True
    assert "latitude" in getattr(result.content[0], "text", "")


def make_app(settings: Settings, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore) -> FastAPI:
    """The whole app, its tools calling the stand-in for Open-Meteo."""
    app = create_app(settings)
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(cache_store)
    return app


def test_an_mcp_client_reaches_the_server_over_http_through_the_app(
    settings: Settings, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore
) -> None:
    app = make_app(settings, open_meteo, cache_store)

    async def go() -> tuple[str, Any, list[str], CallToolResult]:
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=LOCAL) as http,
            Client(streamable_http_client(f"{LOCAL}/api/mcp", http_client=http)) as client,
        ):
            listed = await client.list_tools()
            result = await client.call_tool("get_air_quality", DELHI)
            return client.protocol_version, client.server_info, [tool.name for tool in listed.tools], result

    version, server, names, result = asyncio.run(go())
    assert version == "2026-07-28"
    assert server is not None
    assert (server.name, server.version) == ("nimbus-weather", "c7165ac")
    assert names == [tool.name for tool in WEATHER_TOOLS]
    assert result.structured_content is not None
    assert result.is_error is False


def test_a_body_over_8_kib_is_refused_with_the_security_headers(client: TestClient) -> None:
    response = client.post("/api/mcp", content=b'{"padding": "' + b"a" * 9000 + b'"}', headers=JSON_RPC)
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


def test_a_batch_of_messages_is_refused(client: TestClient) -> None:
    batch: list[dict[str, Any]] = [{"jsonrpc": "2.0", "id": n, "method": "tools/list", "params": {}} for n in (1, 2)]
    response = client.post("/api/mcp", json=batch, headers=JSON_RPC)
    assert response.status_code == 400


@pytest.mark.parametrize("method", ["OPTIONS", "POST"])
def test_a_page_elsewhere_gets_no_cors_allowance(client: TestClient, method: str) -> None:
    headers = {"origin": "https://elsewhere.example", "access-control-request-method": "POST", **JSON_RPC}
    response = client.request(method, "/api/mcp", headers=headers, content=b"{}")
    assert "access-control-allow-origin" not in response.headers


def test_each_request_stands_alone_with_no_session_and_gets_json(client: TestClient) -> None:
    # A client of the 2025 protocol, asking for the tools with no handshake first: no session to keep, on any copy.
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    response = client.post("/api/mcp", json=request, headers={**JSON_RPC, "mcp-protocol-version": "2025-11-25"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert "mcp-session-id" not in response.headers
    assert [tool["name"] for tool in response.json()["result"]["tools"]] == [tool.name for tool in WEATHER_TOOLS]


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_a_get_is_refused_at_once_as_the_server_offers_no_stream(
    settings: Settings, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore, method: str
) -> None:
    # The SDK would answer a GET with a stream that never ends (issue 61): 2 s is ample for a 405.
    app = make_app(settings, open_meteo, cache_store)

    async def go() -> httpx2.Response:
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=LOCAL) as http,
        ):
            return await asyncio.wait_for(http.request(method, "/api/mcp", headers=JSON_RPC), timeout=2)

    response = asyncio.run(go())
    assert (response.status_code, response.headers["allow"]) == (405, "POST")


def test_on_a_computer_a_page_that_rebinds_its_name_to_the_app_is_refused(client: TestClient) -> None:
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {**JSON_RPC, "host": "rebound.example:8000", "origin": "http://rebound.example:8000"}
    response = client.post("/api/mcp", json=request, headers=headers)
    assert response.status_code == 421


def test_on_vercel_the_host_is_not_checked_as_its_edge_sends_only_our_names(
    chat_model: FakeModel, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore
) -> None:
    settings = Settings(_env_file=None, is_vercel=True, vercel_env="production")
    app = make_app(settings, open_meteo, cache_store)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {**JSON_RPC, "host": "weather-chatbot-hazel.vercel.app", "mcp-protocol-version": "2025-11-25"}
    with TestClient(app) as vercel_client:
        response = vercel_client.post("/api/mcp", json=request, headers=headers)
    assert response.status_code == 200
