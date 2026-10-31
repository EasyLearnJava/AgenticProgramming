"""
tools/run_tool.py: runs one weather tool on its own, against Open-Meteo itself, as the agent would: the request as it
went out, the chip's summary, what the model would read, and the request's log line. No model and no key: Open-Meteo
needs neither. From the project's folder, in bash:

    uv run python -m tools.run_tool geocode_location '{"query": "Paris", "count": 2}'
"""

import asyncio
import json
import sys

import httpx2

from nimbus.config import Settings
from nimbus.logger import configure_logging
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import WEATHER_TOOLS, ToolContext

USAGE = "usage: uv run python -m tools.run_tool <tool> '<input as JSON>'"


async def run(name: str, arguments: str) -> int:
    """Runs the tool named with the input given; prints what it sent and what it gives back. Exit 2 on bad usage."""
    tools = {tool.name: tool for tool in WEATHER_TOOLS}
    if name not in tools:
        print(f"{USAGE}\ntools: {', '.join(tools)}")
        return 2
    tool = tools[name]
    params = tool.input_model.model_validate(json.loads(arguments))
    async with httpx2.AsyncClient() as http:
        tool_run = await tool.run(params, ToolContext(OpenMeteoClient(http)))
    print(tool_run.request.to_text())
    print(f"→ {tool_run.summary}")
    print(json.dumps(json.loads(tool_run.output.model_dump_json()), indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    """The tool's name and its input, from the command line."""
    # Windows writes a pipe in its own code page, which has no → or °: UTF-8, as on every other system.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if len(sys.argv) != 3:
        print(USAGE)
        return 2
    configure_logging(Settings(_env_file=None))
    return asyncio.run(run(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
