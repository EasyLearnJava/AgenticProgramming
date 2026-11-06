"""Fixed external travel MCP endpoints using isolated, bounded Streamable HTTP sessions."""

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Final, Literal

import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_types import CallToolResult, TextContent

from nimbus.mcp_lane import to_leaves
from nimbus.travel.models import TRAVEL_TIMEOUT_SECONDS, Provider

type Failure = Literal["invalid_response", "timeout", "rate_limited", "unavailable"]
travel_mcp_active: ContextVar[bool] = ContextVar("travel_mcp_active", default=False)
CHECK_SECONDS: Final = 6.0
MAX_RESPONSE_BYTES: Final = 1024 * 1024
ENDPOINTS: Final = {"kiwi": "https://mcp.kiwi.com", "trivago": "https://mcp.trivago.com/mcp"}
SEARCH_TOOLS: Final = {
    "kiwi": frozenset({"search-flight"}),
    "trivago": frozenset({"trivago-accommodation-search", "trivago-accommodation-radius-search"}),
}


class TravelProviderError(Exception):
    """A sanitized failure code, safe for the tool layer to return."""

    def __init__(self, reason: Failure) -> None:
        """Retain just the normalized reason."""
        super().__init__(reason)
        self.reason = reason


@dataclass
class _Exchange:
    """Preserve HTTP status before the SDK translates it to a JSON-RPC error."""

    failure: Failure | None = None

    async def inspect(self, response: httpx2.Response) -> None:
        """Enforce the byte budget for JSON and SSE, including chunked replies."""
        if response.request.method == "POST" and response.status_code >= 400:
            self.failure = "rate_limited" if response.status_code == 429 else "unavailable"
        size = response.headers.get("content-length", "")
        if (
            response.is_redirect
            or response.headers.get("content-encoding", "identity").lower() != "identity"
            or (size.isdecimal() and (len(size) > 12 or int(size) > MAX_RESPONSE_BYTES))
        ):
            self.failure = "invalid_response"
            await response.aclose()
            raise TravelProviderError("invalid_response")
        if isinstance(response.stream, httpx2.AsyncByteStream):
            response.stream = _LimitedStream(response.stream, self)


class _LimitedStream(httpx2.AsyncByteStream):
    """Wrap the response before the SDK reads it. The client asks for identity encoding."""

    def __init__(self, stream: httpx2.AsyncByteStream, exchange: _Exchange) -> None:
        """Take ownership of a single upstream response stream."""
        self.stream = stream
        self.exchange = exchange

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Hand through only bytes within the per-response budget."""
        seen = 0
        async for chunk in self.stream:
            seen += len(chunk)
            if seen > MAX_RESPONSE_BYTES:
                self.exchange.failure = "invalid_response"
                raise TravelProviderError("invalid_response")
            yield chunk

    async def aclose(self) -> None:
        """Release the wrapped network response."""
        await self.stream.aclose()


@asynccontextmanager
async def _session(provider: Provider, required: frozenset[str], seconds: float) -> AsyncIterator[Client]:
    """Open, negotiate and validate only the fixed provider's tools, within a single deadline."""
    exchange = _Exchange()
    token = travel_mcp_active.set(True)
    try:
        # ① A dedicated client has no credentials, bypass, proxy, visitor headers or shared cookies.
        async with (
            asyncio.timeout(seconds),
            httpx2.AsyncClient(
                verify=ssl.create_default_context(),
                trust_env=False,
                headers={"accept-encoding": "identity"},
                timeout=seconds,
                event_hooks={"response": [exchange.inspect]},
            ) as http,
            Client(
                streamable_http_client(ENDPOINTS[provider], http_client=http, max_sse_event_size=MAX_RESPONSE_BYTES),
                mode="legacy",
            ) as client,
        ):
            # ② The SDK negotiates the handshake-era version these services support. Never import remote tools.
            if not required <= {tool.name for tool in (await client.list_tools()).tools}:
                raise TravelProviderError("invalid_response")
            yield client
    except Exception as error:
        # ③ AnyIO can wrap a tool exception on session exit. Cancellation must continue through every layer.
        failures = to_leaves(error) if isinstance(error, BaseExceptionGroup) else [error]
        known = next((item.reason for item in failures if isinstance(item, TravelProviderError)), None)
        timed_out = any(isinstance(item, (TimeoutError, httpx2.TimeoutException)) for item in failures)
        reason: Failure = exchange.failure or known or ("timeout" if timed_out else "unavailable")
        raise TravelProviderError(reason) from None
    finally:
        travel_mcp_active.reset(token)


def to_payload(result: CallToolResult) -> dict[str, Any]:
    """Read the structured payload, or its JSON text equivalent, without forwarding provider instructions."""
    if result.is_error:
        raise TravelProviderError("unavailable")
    if result.structured_content is not None:
        if isinstance(result.structured_content, dict):
            return result.structured_content
        raise TravelProviderError("invalid_response")
    blocks = [block.text for block in result.content if isinstance(block, TextContent)]
    if len(blocks) == 1:
        try:
            value = json.loads(blocks[0])
        except (ValueError, RecursionError):
            value = None
        if isinstance(value, dict):
            return value
    raise TravelProviderError("invalid_response")


async def call_search(provider: Provider, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call one approved search operation. Keep the 14-second budget across connection, search and cleanup."""
    if name not in SEARCH_TOOLS[provider]:
        raise TravelProviderError("invalid_response")
    async with _session(provider, frozenset({name}), TRAVEL_TIMEOUT_SECONDS) as client:
        return to_payload(await client.call_tool(name, arguments))


async def check_provider(provider: Provider) -> None:
    """Check search-tool availability using discovery alone."""
    async with _session(provider, SEARCH_TOOLS[provider], CHECK_SECONDS):
        pass
