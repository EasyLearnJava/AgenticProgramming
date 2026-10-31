"""
tools/run_tool.py: runs one weather tool on its own, against Open-Meteo itself, as the agent would: the request as it
went out, the chip's summary, what the model would read, and the request's log line. No model and no key: Open-Meteo
needs neither. With --again, it runs a second time, as the next question would, and the cache answers (step 7). With
--mcp and our MCP server's address, it runs through the MCP · no auth lane instead, as a chip shows it: the JSON-RPC
request the lane sent, then the one the server sent Open-Meteo (step 9). With --auth, get_forecast runs on REST · with
auth, through Apify's Actor, with APIFY_TOKEN from your settings, falling back to REST · no auth (step 10). From the
project's folder, in bash:

    uv run python -m tools.run_tool geocode_location '{"query": "Paris", "count": 2}'
    uv run python -m tools.run_tool geocode_location '{"query": "Paris", "count": 1}' --again
    uv run python -m tools.run_tool get_air_quality '{"latitude": 28.65, "longitude": 77.23}' \\
      --mcp http://127.0.0.1:8000/api/mcp
    uv run python -m tools.run_tool get_forecast \\
      '{"latitude": 48.85, "longitude": 2.35, "days": 2, "include_hourly": false, "units": "metric"}' --auth
"""

import asyncio
import json
import sys
from functools import partial

import httpx2
from pydantic import BaseModel

from nimbus.apify import make_apify_http_client, run_actor_rest
from nimbus.auth_lanes import to_auth_tools
from nimbus.cache import make_weather_cache
from nimbus.config import Settings
from nimbus.constants import AUTH_ANSWER_TIMEOUT_SECONDS
from nimbus.lanes import REST_NO_AUTH, REST_WITH_AUTH
from nimbus.logger import configure_logging
from nimbus.mcp_lane import open_mcp_lane
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import GET_FORECAST, WEATHER_TOOLS, ToolCallRecord, ToolContext, rest_runs

USAGE = (
    "usage: uv run python -m tools.run_tool <tool> '<input as JSON>' [--again | --mcp <MCP server's address> | --auth]"
)


async def run(name: str, arguments: str, *, again: bool = False, mcp_url: str | None = None, auth: bool = False) -> int:
    """
    Runs the tool named with the input given, its answers kept in the cache; prints what it sent and what it gives
    back; again, runs it once more and says where that answer came from; with an MCP address, runs it through the MCP
    lane. Exit 2 on bad usage.
    """
    tools = {tool.name: tool for tool in WEATHER_TOOLS}
    if name not in tools:
        print(f"{USAGE}\ntools: {', '.join(tools)}")
        return 2
    tool = tools[name]
    params = tool.input_model.model_validate(json.loads(arguments))
    if mcp_url is not None:
        return await run_on_mcp(name, params, mcp_url)
    if auth:
        return await run_on_rest_with_auth(name, params)
    async with httpx2.AsyncClient() as http:
        context = ToolContext(OpenMeteoClient(http, cache=make_weather_cache()))
        tool_run = await tool.run(params, context)
        print(tool_run.request.to_text())
        print(f"→ {tool_run.summary}")
        print(json.dumps(json.loads(tool_run.output.model_dump_json()), indent=2, ensure_ascii=False))
        if again:
            again_run = await tool.run(params, context)
            where = "from the cache" if again_run.from_cache else "from Open-Meteo"
            print(f"Again → {again_run.summary} · {where}")
    return 0


async def run_on_mcp(name: str, params: BaseModel, mcp_url: str) -> int:
    """The tool through the MCP lane: the request the lane sent, the server's to Open-Meteo, and what came back."""
    async with open_mcp_lane(mcp_url, httpx2.AsyncClient()) as lane_tools:
        lane_tool = next(lane_tool for lane_tool in lane_tools if lane_tool.name == name)
        call = {"type": "tool_call", "id": "run-tool", "name": name, "args": params.model_dump(mode="json")}
        message = await lane_tool.ainvoke(call)
    record = message.artifact
    if not isinstance(record, ToolCallRecord):
        print(f"✗ {message.content}")
        return 1
    print(record.request.to_text())
    if record.upstream_request is not None:
        print("Then, from our MCP server:")
        print(record.upstream_request.to_text())
    print(f"→ {record.summary}")
    print(json.dumps(json.loads(message.content), indent=2, ensure_ascii=False))
    return 0


async def run_on_rest_with_auth(name: str, params: BaseModel) -> int:
    """get_forecast on REST · with auth: the Actor's run, or, if it fails, REST · no auth's forecast, saying why."""
    token = Settings().apify_token
    if name != GET_FORECAST.name or token is None:
        print("--auth runs get_forecast, with APIFY_TOKEN set in your environment or .env.local")
        return 2
    async with httpx2.AsyncClient() as http, make_apify_http_client() as apify_http:
        context = ToolContext(OpenMeteoClient(http, cache=make_weather_cache()))
        deadline = asyncio.get_running_loop().time() + AUTH_ANSWER_TIMEOUT_SECONDS
        run_actor = partial(run_actor_rest, apify_http, token)
        runs = rest_runs(context)
        tools = to_auth_tools(REST_WITH_AUTH, REST_NO_AUTH, runs, run_actor, deadline, context.now, None)
        forecast = next(tool for tool in tools if tool.name == name)
        call = {"type": "tool_call", "id": "run-tool", "name": name, "args": params.model_dump()}
        message = await forecast.ainvoke(call)
    record = message.artifact
    if not isinstance(record, ToolCallRecord):
        print(f"✗ {message.content}")
        return 1
    if record.fallback_note is not None:
        print(f"↩ {record.fallback_note}")
    print(record.request.to_text())
    print(f"→ {record.summary}")
    print(json.dumps(json.loads(message.content), indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    """The tool's name and its input, from the command line; then --again, or --mcp and an address, if given."""
    # Windows writes a pipe in its own code page, which has no → or °: UTF-8, as on every other system.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    arguments = sys.argv[1:]
    again = arguments[-1:] == ["--again"]
    if again:
        arguments = arguments[:-1]
    mcp_url = None
    if len(arguments) == 4 and arguments[2] == "--mcp":
        mcp_url, arguments = arguments[3], arguments[:2]
    auth = arguments[-1:] == ["--auth"]
    if auth:
        arguments = arguments[:-1]
    if len(arguments) != 2:
        print(USAGE)
        return 2
    configure_logging(Settings(_env_file=None))
    return asyncio.run(run(arguments[0], arguments[1], again=again, mcp_url=mcp_url, auth=auth))


if __name__ == "__main__":
    sys.exit(main())
