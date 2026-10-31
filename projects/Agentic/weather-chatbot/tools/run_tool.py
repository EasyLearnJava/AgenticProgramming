"""
tools/run_tool.py: runs one weather tool on its own, against Open-Meteo itself, as the agent would: the request as it
went out, the chip's summary, what the model would read, and the request's log line. No model and no key: Open-Meteo
needs neither. With --again, it runs a second time, as the next question would, and the cache answers (step 7). From
the project's folder, in bash:

    uv run python -m tools.run_tool geocode_location '{"query": "Paris", "count": 2}'
    uv run python -m tools.run_tool geocode_location '{"query": "Paris", "count": 1}' --again
"""

import asyncio
import json
import sys

import httpx2

from nimbus.cache import make_weather_cache
from nimbus.config import Settings
from nimbus.logger import configure_logging
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import WEATHER_TOOLS, ToolContext

USAGE = "usage: uv run python -m tools.run_tool <tool> '<input as JSON>' [--again]"


async def run(name: str, arguments: str, *, again: bool = False) -> int:
    """
    Runs the tool named with the input given, its answers kept in the cache; prints what it sent and what it gives
    back; again, runs it once more and says where that answer came from. Exit 2 on bad usage.
    """
    tools = {tool.name: tool for tool in WEATHER_TOOLS}
    if name not in tools:
        print(f"{USAGE}\ntools: {', '.join(tools)}")
        return 2
    tool = tools[name]
    params = tool.input_model.model_validate(json.loads(arguments))
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


def main() -> int:
    """The tool's name and its input, from the command line."""
    # Windows writes a pipe in its own code page, which has no → or °: UTF-8, as on every other system.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    arguments = sys.argv[1:]
    again = arguments[-1:] == ["--again"]
    if again:
        arguments = arguments[:-1]
    if len(arguments) != 2:
        print(USAGE)
        return 2
    configure_logging(Settings(_env_file=None))
    return asyncio.run(run(arguments[0], arguments[1], again=again))


if __name__ == "__main__":
    sys.exit(main())
