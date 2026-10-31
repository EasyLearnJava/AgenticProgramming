"""
nimbus/mcp_server.py: our own MCP server (step 8), at /api/mcp, for any MCP client: the official MCP SDK's MCPServer,
which was FastMCP before the SDK's version 2. It offers the same four weather tools the agent calls over REST, each
from the same definition, its input schema made from the tool's own model. It keeps no session, since Vercel's copies
share no memory, and answers in JSON. Each answer carries the weather as structured content, the chip's one-line
summary as text, and, in _meta, the request that fetched it and whether the cache gave it; a tool that fails answers
with our sentence and its error's class, never an error's own text. Each call writes one mcp.call line, which never
holds the call's input.
"""

import inspect
import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated, Any

import structlog
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import INVALID_REQUEST, CallToolResult, TextContent, ToolAnnotations
from starlette.datastructures import State
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from nimbus.config import Settings
from nimbus.constants import MCP_BODY_MAX_BYTES, MCP_LOCAL_HOSTS, MCP_PATH, MCP_SERVER_NAME
from nimbus.errors import UpstreamError
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import WEATHER_TOOLS, ToolContext, WeatherTool, run_in_time
from nimbus.utils import to_ms

log = structlog.get_logger()

# What an MCP client, and its model, read first: what the tools are for, and in what order to call them.
INSTRUCTIONS = (
    "Weather from Open-Meteo, which needs no key. geocode_location finds a place's latitude and longitude from its "
    "name; get_forecast, get_current_weather and get_air_quality take them. Times are in the place's own zone."
)
# Each tool only reads, and reaches outside the app, to Open-Meteo.
TOOL_ANNOTATIONS = ToolAnnotations(read_only_hint=True, open_world_hint=True)
# A GET's answer, as the SDK words a method it refuses: the server offers no stream (issue 61).
NO_STREAM = {"jsonrpc": "2.0", "id": None, "error": {"code": INVALID_REQUEST, "message": "Method Not Allowed"}}

ToolContextFactory = Callable[[], AbstractAsyncContextManager[ToolContext]]


def to_signature(tool: WeatherTool) -> inspect.Signature:
    """The tool's input model as keyword arguments, from which the SDK makes the same input schema as the model's."""
    parameters = [
        inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=Annotated[field.annotation, field])
        for name, field in tool.input_model.model_fields.items()
    ]
    return inspect.Signature(parameters, return_annotation=CallToolResult)


def to_mcp_function(tool: WeatherTool, tool_context: ToolContextFactory) -> Callable[..., Awaitable[CallToolResult]]:
    """One of our tools as the server's function: its input checked by its own model, run within its 8 s."""

    async def call(**kwargs: Any) -> CallToolResult:
        """Runs the tool: its answer, or our sentence and the error's class; one mcp.call line, timed."""
        params = tool.input_model.model_validate(kwargs)
        started = time.perf_counter()
        try:
            async with tool_context() as context:
                tool_run = await run_in_time(tool, params, context)
        except UpstreamError as error:
            ms = to_ms(time.perf_counter() - started)
            log.info("mcp.call", tool=tool.name, status="failed", ms=ms, errorClass=type(error).__name__)
            return CallToolResult(
                content=[TextContent(type="text", text=error.user_message)],
                is_error=True,
                meta={"errorClass": type(error).__name__},
            )
        ms = to_ms(time.perf_counter() - started)
        log.info("mcp.call", tool=tool.name, status="ok", ms=ms, fromCache=tool_run.from_cache)
        return CallToolResult(
            content=[TextContent(type="text", text=tool_run.summary)],
            structured_content=json.loads(tool_run.output.model_dump_json()),
            meta={"request": tool_run.request.model_dump(), "fromCache": tool_run.from_cache},
        )

    call.__signature__ = to_signature(tool)  # type: ignore[attr-defined]
    return call


def make_tool_context(state: State) -> ToolContextFactory:
    """
    Each call's context: a new HTTP client from the app's factory, closed with the call, and the app's cache; both read
    from the app's state when the call comes, so a test's own are the ones used.
    """

    @asynccontextmanager
    async def tool_context() -> AsyncIterator[ToolContext]:
        """The context for one call."""
        async with state.make_http_client() as http:
            yield ToolContext(OpenMeteoClient(http, cache=state.weather_cache))

    return tool_context


def make_mcp_server(state: State) -> MCPServer:
    """
    The server, offering our four tools, which run with the app's HTTP clients and its cache; its version is the
    commit Vercel built, as the logs give it, or "local" on a computer.
    """
    server = MCPServer(MCP_SERVER_NAME, version=state.settings.commit or "local", instructions=INSTRUCTIONS)
    tool_context = make_tool_context(state)
    for tool in WEATHER_TOOLS:
        server.add_tool(
            to_mcp_function(tool, tool_context),
            name=tool.name,
            description=tool.description,
            annotations=TOOL_ANNOTATIONS,
        )
    return server


async def refuse_stream(_request: Request) -> Response:
    """
    A GET, or a HEAD, at /api/mcp: 405, as the server offers no stream. The SDK would answer a GET with a stream that
    never ends, and on Vercel a client leaving never reaches the app (issue 32): each GET would hold a copy 300 s.
    """
    return JSONResponse(NO_STREAM, status_code=405, headers={"Allow": "POST"})


def to_routes(server: MCPServer, settings: Settings) -> list[BaseRoute]:
    """
    The routes at /api/mcp: first ours, refusing a GET (issue 61); then the SDK's: no session, since Vercel's copies
    share no memory; JSON, not a stream; a body of at most 8 KiB. On a computer, the SDK checks the Host and the
    Origin, so a page that rebinds its own name to 127.0.0.1 can't reach the app (issue 62). On Vercel, its edge sends
    the app only our own names, and a page elsewhere can't send JSON without a CORS preflight, which gets no allowance.
    """
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=not settings.is_vercel,
        allowed_hosts=list(MCP_LOCAL_HOSTS),
        allowed_origins=[f"http://{host}" for host in MCP_LOCAL_HOSTS],
    )
    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
        max_request_body_size=MCP_BODY_MAX_BYTES,
        transport_security=security,
    )
    return [Route(MCP_PATH, endpoint=refuse_stream, methods=["GET", "HEAD"]), *app.routes]
