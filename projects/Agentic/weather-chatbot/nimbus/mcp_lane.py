"""
nimbus/mcp_lane.py: the MCP · no auth lane (step 9): the agent reaches its four tools through our own MCP server, on
this same deployment, with the official SDK's client. langchain-mcp-adapters, which the plan named, still imports the
SDK's version 1 (issue 63), so the lane makes its LangChain tools itself, from our own definitions: the names,
descriptions and inputs REST · no auth has, each call a tools/call to the server. It connects and lists the server's
tools within 6 s, and checks our four are there; each call has 8 s, as on REST. A chip shows the JSON-RPC request as
the client sent it, its secret masked, then the request the server sent Open-Meteo, from the answer's _meta. A call
that fails raises the same error as on REST, by its class's name; one the lane can't make is McpLaneError.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Final

import httpx2
from langchain_core.tools import StructuredTool, ToolException
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import LATEST_PROTOCOL_VERSION, CallToolResult, TextContent
from pydantic import BaseModel, RootModel, SecretStr, ValidationError
from starlette.requests import Request

from nimbus.config import Settings
from nimbus.constants import BYPASS_HEADER, MCP_CONNECT_SECONDS, MCP_PATH, TOOL_TIMEOUT_SECONDS
from nimbus.errors import (
    ContractError,
    McpLaneError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.lanes import MCP_NO_AUTH
from nimbus.open_meteo import WireRequest
from nimbus.tools import WEATHER_TOOLS, ToolRun, WeatherTool, to_langchain_tool

# The errors a tool's answer can name, by its class's name: the ones REST · no auth raises.
KNOWN_ERRORS: Final[dict[str, Callable[[], UpstreamError]]] = {
    error.__name__: error
    for error in (UpstreamTimeoutError, UpstreamUnavailableError, UpstreamRateLimitedError, ContractError)
}
# What a chip shows in place of the secret that gets a call past Vercel's protection, and of any credential or cookie
# the client might carry.
MASKED_BYPASS: Final = "<VERCEL_AUTOMATION_BYPASS_SECRET>"
MASKED_HEADERS: Final = {BYPASS_HEADER: MASKED_BYPASS, "authorization": "<masked>", "cookie": "<masked>"}


class McpOutput(RootModel[dict[str, Any]]):
    """A tool's structured content, as our MCP server sent it: what the model reads."""


def make_mcp_http_client() -> httpx2.AsyncClient:
    """
    A new HTTP client, for one answer's calls to our MCP server: httpx2's own limits, and the system's certificates.
    The app keeps this factory in its state, and the tests give it one that calls the app in memory.
    """
    return httpx2.AsyncClient()


def to_self_mcp_url(request: Request, settings: Settings) -> str | None:
    """
    Where the lane finds our MCP server: on this same deployment, so a preview talks to its own. On Vercel, at the
    address the question came to, if it's one of the deployment's own names, as Vercel gives them; else at the
    deployment's own URL, so a forged Host can't send the call elsewhere. On a computer, at the address the app listens
    on, never one a request names. None if Vercel gave no name.
    """
    if settings.is_vercel:
        own = {settings.vercel_project_production_url, settings.vercel_branch_url, settings.vercel_url} - {None}
        asked = (request.headers.get("x-forwarded-host"), request.headers.get("host"))
        host = next((name for name in asked if name in own), settings.vercel_url)
        return None if host is None else f"https://{host}{MCP_PATH}"
    server_host, port = request.scope.get("server") or ("127.0.0.1", 80)
    name = f"[{server_host}]" if ":" in server_host else server_host
    return f"http://{name}:{port}{MCP_PATH}"


def to_tools_call(url: str, name: str, arguments: dict[str, Any]) -> WireRequest:
    """
    A tools/call request, as this lane makes it, for the compare view: the address, the headers MCP's 2026-07-28 version
    names each request with, and the JSON-RPC message; the SDK's client adds its own headers and the protocol's _meta.
    """
    headers = {
        "content-type": "application/json",
        "mcp-protocol-version": LATEST_PROTOCOL_VERSION,
        "mcp-method": "tools/call",
        "mcp-name": name,
    }
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    return WireRequest(method="POST", url=url, headers=headers, body=json.dumps(message, indent=2))


def to_wire_request(request: httpx2.Request) -> WireRequest:
    """A request the client sent, for a chip: its method, address and headers, any secret masked, and its body."""
    headers = {name: MASKED_HEADERS.get(name.lower(), value) for name, value in request.headers.items()}
    body = json.dumps(json.loads(request.content), indent=2, ensure_ascii=False)
    return WireRequest(method=request.method, url=str(request.url), headers=headers, body=body)


def find_call(sent: list[httpx2.Request], name: str, arguments: dict[str, Any]) -> httpx2.Request | None:
    """The tools/call request the client sent for this call: the newest with its tool and its input."""
    for request in reversed(sent):
        try:
            message = json.loads(request.content)
        except ValueError:
            continue
        params = message.get("params") if isinstance(message, dict) else None
        if not isinstance(params, dict) or message.get("method") != "tools/call":
            continue
        if (params.get("name"), params.get("arguments")) == (name, arguments):
            return request
    return None


def to_tool_run(result: CallToolResult, call: WireRequest) -> ToolRun:
    """
    A tools/call's answer as the tool's run: the weather for the model, the summary, whether the cache gave it, and the
    request the server sent Open-Meteo. An answer that's an error raises the same error as on REST, by its class's
    name; one that names none we know is the server refusing the call, such as its input: a tool error, with the
    server's own text for the model, which a chip shows as a call made the wrong way. One with no weather, McpLaneError.
    """
    meta = result.meta or {}
    if result.is_error:
        known = KNOWN_ERRORS.get(str(meta.get("errorClass")))
        if known is None:
            raise ToolException(next((b.text for b in result.content if isinstance(b, TextContent)), ""))
        raise known()
    if result.structured_content is None:
        raise McpLaneError
    summary = next((block.text for block in result.content if isinstance(block, TextContent)), "")
    try:
        upstream: WireRequest | None = WireRequest.model_validate(meta.get("request"))
    except ValidationError:
        upstream = None
    output = McpOutput(result.structured_content)
    return ToolRun(output, call, summary, from_cache=meta.get("fromCache") is True, upstream_request=upstream)


def make_mcp_run(
    tool: WeatherTool, client: Client, url: str, sent: list[httpx2.Request]
) -> Callable[[BaseModel], Awaitable[ToolRun]]:
    """How the lane runs one of our tools: a tools/call to the server, within 8 s, its answer as the tool's run."""

    async def run(params: BaseModel) -> ToolRun:
        """One call: past its 8 s, UpstreamTimeoutError; a call that can't be made, McpLaneError."""
        arguments = params.model_dump(mode="json")
        try:
            async with asyncio.timeout(TOOL_TIMEOUT_SECONDS):
                result = await client.call_tool(tool.name, arguments)
        except TimeoutError as error:
            raise UpstreamTimeoutError from error
        except Exception as error:
            raise McpLaneError from error
        request = find_call(sent, tool.name, arguments)
        call = to_wire_request(request) if request is not None else to_tools_call(url, tool.name, arguments)
        return to_tool_run(result, call)

    return run


def to_leaves(group: BaseExceptionGroup) -> list[BaseException]:
    """The errors in a group, however deep, in order."""
    leaves: list[BaseException] = []
    for error in group.exceptions:
        leaves.extend(to_leaves(error) if isinstance(error, BaseExceptionGroup) else [error])
    return leaves


def unwrap(group: BaseExceptionGroup) -> BaseException:
    """
    The error to raise for a group the SDK's task group made: the one inside a group of one, however deep. From a
    bigger group, a cancellation or a closing if it holds one, so the answer still ends as it must; else McpLaneError,
    the group as its cause.
    """
    leaves = to_leaves(group)
    if len(leaves) == 1:
        return leaves[0]
    ending = next((error for error in leaves if isinstance(error, (GeneratorExit, asyncio.CancelledError))), None)
    if ending is not None:
        return ending
    failure = McpLaneError()
    failure.__cause__ = group
    return failure


@asynccontextmanager
async def open_mcp_lane(
    url: str | None, http_client: httpx2.AsyncClient, bypass_secret: SecretStr | None = None
) -> AsyncIterator[list[StructuredTool]]:
    """
    The lane's four tools, on one connection to the server at the URL, open for as long as the answer is, and closed
    with it, however it ends. Connecting and listing its tools have 6 s; a server that can't be reached, or doesn't
    offer our four, is McpLaneError. Each request the client sends is kept, for the chips; the secret that gets a call
    past Vercel's protection goes with each, if the deployment has one.
    """
    sent: list[httpx2.Request] = []

    async def keep(request: httpx2.Request) -> None:
        """Keeps a request as it goes out."""
        sent.append(request)

    hooks = http_client.event_hooks
    http_client.event_hooks = {"request": [*hooks.get("request", []), keep], "response": hooks.get("response", [])}
    if bypass_secret is not None:
        http_client.headers[BYPASS_HEADER] = bypass_secret.get_secret_value()
    try:
        async with http_client as http, AsyncExitStack() as stack:
            if url is None:
                raise McpLaneError
            try:
                async with asyncio.timeout(MCP_CONNECT_SECONDS):
                    client = await stack.enter_async_context(Client(streamable_http_client(url, http_client=http)))
                    listed = await client.list_tools()
            except Exception as error:
                raise McpLaneError from error
            offered = {tool.name for tool in listed.tools}
            if not {tool.name for tool in WEATHER_TOOLS} <= offered:
                raise McpLaneError
            runs = {tool.name: make_mcp_run(tool, client, url, sent) for tool in WEATHER_TOOLS}
            yield [to_langchain_tool(tool, runs[tool.name], MCP_NO_AUTH) for tool in WEATHER_TOOLS]
    except BaseExceptionGroup as group:
        # The SDK's client runs in a task group, which wraps whatever leaves it, the answer's own errors among them: the
        # one inside goes on as it was, its cause kept, so the chat still knows it (issue 64).
        inner = unwrap(group)
        raise inner from inner.__cause__
