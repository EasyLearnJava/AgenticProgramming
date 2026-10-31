"""
tools/call_mcp.py: calls an MCP server as any MCP client would, with the official SDK's client: the protocol it agreed,
the server's name, its tools, then one tool's answer: the summary, the weather and _meta. Our own server is at
/api/mcp, on your computer once the app runs, or on the live site. From the project's folder, in bash:

    uv run python -m tools.call_mcp http://127.0.0.1:8000/api/mcp geocode_location '{"query": "Paris", "count": 1}'
"""

import asyncio
import json
import sys

from mcp.client import Client

USAGE = "usage: uv run python -m tools.call_mcp <server's URL> <tool> '<input as JSON>'"


async def run(url: str, name: str, arguments: str) -> int:
    """Connects, lists the tools, calls the one named with the input given, and prints it all. Exit 1 on its error."""
    async with Client(url) as client:
        server = client.server_info
        print(f"protocol {client.protocol_version} · server {server.name if server else 'unnamed'}")
        listed = await client.list_tools()
        print("tools:", ", ".join(tool.name for tool in listed.tools))
        result = await client.call_tool(name, json.loads(arguments))
    print("isError:", result.is_error)
    for block in result.content:
        print("text:", getattr(block, "text", block))
    if result.structured_content is not None:
        print("structuredContent:", json.dumps(result.structured_content, indent=2, ensure_ascii=False))
    print("_meta:", json.dumps(result.meta, indent=2, ensure_ascii=False))
    return 1 if result.is_error else 0


def main() -> int:
    """The server's URL, the tool's name and its input, from the command line."""
    # Windows writes a pipe in its own code page, which has no → or °: UTF-8, as on every other system.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if len(sys.argv) != 4:
        print(USAGE)
        return 2
    return asyncio.run(run(sys.argv[1], sys.argv[2], sys.argv[3]))


if __name__ == "__main__":
    sys.exit(main())
