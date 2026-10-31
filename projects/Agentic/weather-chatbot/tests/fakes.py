"""
tests/fakes.py: stand-ins for Gemini and Open-Meteo, for the unit and browser tests, which never call either: Gemini
needs a key and costs quota, and Open-Meteo's weather changes by the hour.

- FakeModel: a LangChain chat model that calls the tools it's told to, a round at a time, then streams a known answer a
  word at a time, after a pause each. It reports each chunk's share of the tokens, as Gemini does (a delta, not a
  running total), says whether its stream was closed, and can fail on cue.
- OpenMeteoRecordings: an httpx2 handler that answers each request with Open-Meteo's recorded answer for what it asks
  (tests/fixtures/open_meteo/), after a pause; or with a 503, for the paths it's told to fail.
- ApifyRecordings and make_apify_mcp_stand_in(): Apify's REST API, and its MCP server, played back (step 10): a run's
  items from the Actor's recorded answers (tests/fixtures/apify/), moved to the place and days asked; or a failure.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import httpx2
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import agenerate_from_stream
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent
from pydantic import BaseModel, Field
from starlette.applications import Starlette

ANSWER = (
    "Tomorrow, Friday 30 October, Paris, France will be **mainly clear**, from 6 to 15 °C, with no rain expected "
    "(Paris time)."
)
# A word, with the space before it.
PIECE = re.compile(r"\s*\S+")
# The tokens in: the prompt, all in a call's first chunk. The tokens out: one a word, and one a tool call.
TOKENS_IN = 412
TOKENS_OUT = len(PIECE.findall(ANSWER))
# The Paris question's two rounds of tools, as Gemini makes them: the place, then its forecast.
PARIS_STEPS: list[list[dict[str, Any]]] = [
    [{"name": "geocode_location", "args": {"query": "Paris"}}],
    [
        {
            "name": "get_forecast",
            "args": {"latitude": 48.85341, "longitude": 2.3488, "days": 2, "include_hourly": False, "units": "metric"},
        },
    ],
]
FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"


class FakeModel(BaseChatModel):
    """A chat model that calls its scripted tools, then streams its answer; it keeps every list of messages it got."""

    answer: str = ANSWER
    tool_steps: list[list[dict[str, Any]]] = Field(default_factory=list)
    step_words: str = ""
    delay: float = 0.0
    fail_after_first_word: BaseException | None = None
    seen: list[list[BaseMessage]] = Field(default_factory=list)
    bound_tools: list[str] = Field(default_factory=list)
    tool_choice: str | None = None
    tool_choices: list[str | None] = Field(default_factory=list)
    closed: bool = False

    @property
    def _llm_type(self) -> str:
        """The model's kind, for LangChain."""
        return "nimbus-fake"

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None, **_kwargs: Any) -> "FakeModel":
        """
        Keeps the tools' names, as Gemini would get them, and the tool choice of each call: "none" turns calling them
        off, as it does Gemini's. The script decides the calls.
        """
        self.bound_tools = [tool.name for tool in tools]
        self.tool_choice = tool_choice
        self.tool_choices.append(tool_choice)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Not used: the app runs the model asynchronously."""
        raise NotImplementedError

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Not used: the app runs the model asynchronously."""
        raise NotImplementedError

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """The whole of one call, from its stream, when no one is streaming it."""
        return await agenerate_from_stream(self._astream(messages, stop, run_manager, **kwargs))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """
        This call's part: the next round of tool calls, if the script has one, after any words written first, as
        Gemini sometimes writes them; else the answer a word at a time, each after the pause, each with its share of the
        tokens. It marks itself closed however it ends.
        """
        self.seen.append(messages)
        # The calls so far for this question: the answers after it, not the conversation's earlier ones.
        question_at = max((i for i, message in enumerate(messages) if isinstance(message, HumanMessage)), default=-1)
        step = sum(1 for message in messages[question_at + 1 :] if isinstance(message, AIMessage))
        try:
            if step < len(self.tool_steps) and self.tool_choice != "none":
                await asyncio.sleep(self.delay)
                if self.step_words:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=self.step_words))
                calls = self.tool_steps[step]
                chunks = [
                    tool_call_chunk(
                        name=call["name"], args=json.dumps(call["args"]), id=f"call-{step}-{index}", index=index
                    )
                    for index, call in enumerate(calls)
                ]
                usage = UsageMetadata(
                    input_tokens=TOKENS_IN, output_tokens=len(calls), total_tokens=TOKENS_IN + len(calls)
                )
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content="", tool_call_chunks=chunks, usage_metadata=usage)
                )
                return
            for index, piece in enumerate(PIECE.findall(self.answer)):
                await asyncio.sleep(self.delay)
                tokens_in = TOKENS_IN if index == 0 else 0
                usage = UsageMetadata(input_tokens=tokens_in, output_tokens=1, total_tokens=tokens_in + 1)
                yield ChatGenerationChunk(message=AIMessageChunk(content=piece, usage_metadata=usage))
                if index == 0 and self.fail_after_first_word is not None:
                    raise self.fail_after_first_word
        finally:
            self.closed = True


@cache
def _read_answer(name: str) -> str:
    """One of Open-Meteo's recorded answers, as its file holds it."""
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


def open_meteo_answer(name: str) -> Any:
    """One of Open-Meteo's recorded answers, read afresh each time, so a test can change its copy."""
    return json.loads(_read_answer(name))


class FakeCacheStore:
    """
    Vercel's Runtime Cache, played in memory: each value kept through JSON, as the real one keeps it, with its time to
    live; a read or a write fails, or is slow, when a test says so.
    """

    def __init__(self) -> None:
        """Empty, and working."""
        self.items: dict[str, object] = {}
        self.ttls: dict[str, object] = {}
        self.error: Exception | None = None
        self.delay = 0.0

    async def get(self, key: str) -> object:
        """The value kept under the key, or None."""
        await self._wait_or_fail()
        return self.items.get(key)

    async def set(self, key: str, value: object, options: dict[str, object] | None = None) -> None:
        """Keeps the value under the key, through JSON, with options' time to live."""
        await self._wait_or_fail()
        self.items[key] = json.loads(json.dumps(value))
        self.ttls[key] = (options or {}).get("ttl")

    async def _wait_or_fail(self) -> None:
        """The delay a test gave, then the error it gave, if any."""
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error


class OpenMeteoRecordings:
    """Open-Meteo, played back: each request gets the recorded answer for what it asks, after the pause."""

    def __init__(self, delay: float = 0.0, failing: frozenset[str] = frozenset()) -> None:
        """The pause before each answer, and the paths that answer 503 instead ("/v1/forecast", say)."""
        self.delay = delay
        self.failing = failing
        self.requests: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """The recorded answer for the request, or a 503 for a failing path."""
        self.requests.append(request)
        await asyncio.sleep(self.delay)
        if request.url.path in self.failing:
            return httpx2.Response(503)
        return httpx2.Response(200, json=open_meteo_answer(self._to_name(request)))

    @staticmethod
    def _to_name(request: httpx2.Request) -> str:
        """Which recorded answer a request gets: the place it names, the weather now, the air, or a forecast."""
        path, params = request.url.path, request.url.params
        if path == "/v1/search":
            name = "geocode-" + params.get("name", "").lower().replace(", ", "-").replace(" ", "-")
            return name if (FIXTURES / f"{name}.json").exists() else "geocode-hogwarts"
        if path == "/v1/air-quality":
            return "air-delhi"
        if "current" in params:
            return "current-tokyo"
        return "forecast-dallas-imperial" if params.get("temperature_unit") == "fahrenheit" else "forecast-paris"


APIFY_FIXTURES = Path(__file__).parent / "fixtures" / "apify"


def apify_answer(name: str) -> Any:
    """One of Apify's recorded answers."""
    return json.loads((APIFY_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def actor_items(actor_input: dict[str, Any]) -> list[dict[str, Any]]:
    """
    The Actor's recorded answer for Dallas, moved to the place asked, which it echoes: one item a day, as many days as
    asked; or, hourly, the recorded day's 24 hours for each day asked.
    """
    location = actor_input["locations"][0]
    place = {"location": location["name"], "latitude": location["latitude"], "longitude": location["longitude"]}
    days = actor_input["forecastDays"]
    if actor_input["mode"] == "daily":
        first = apify_answer("actor-dallas-daily")[0]
        start = date.fromisoformat(first["date"])
        return [{**first, **place, "date": (start + timedelta(days=n)).isoformat()} for n in range(days)]
    hours = apify_answer("actor-dallas-hourly")
    start = date.fromisoformat(hours[0]["datetime"][:10])
    return [
        {**hour, **place, "datetime": f"{(start + timedelta(days=n)).isoformat()}{hour['datetime'][10:]}"}
        for n in range(days)
        for hour in hours
    ]


class ApifyRecordings:
    """
    Apify's REST API, played back: a run answers 201 with the Actor's items for the place and days asked; or, if a test
    sets one, an error status, with Apify's recorded 401 or a body of the same shape.
    """

    def __init__(self, status: int = 201) -> None:
        """The status each run gets: 201, a run's items."""
        self.status = status
        self.requests: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """A run's answer."""
        self.requests.append(request)
        if self.status == 401:
            return httpx2.Response(401, json=apify_answer("error-401-fake-token"))
        if self.status >= 400:
            return httpx2.Response(self.status, json={"error": {"type": "stand-in-error", "message": "Paris, quoted"}})
        return httpx2.Response(201, json=actor_items(json.loads(request.content)))


class CallOptions(BaseModel):
    """call-actor's limits, as Apify's MCP server takes them."""

    build: str
    timeout: int
    maxTotalChargeUsd: float  # noqa: N815 - Apify's own name


def make_apify_mcp_stand_in(
    *, run_status: str = "SUCCEEDED", error_text: str | None = None, total_items: int | None = None, pinned: bool = True
) -> Starlette:
    """
    Apify's MCP server, played back, with sessions as Apify's has: call-actor, the Actor's own tool, and
    get-dataset-items. A run's answer holds its status and its dataset's id; reading the dataset gives the items. A
    test can set the run's status, an error result's words, a dataset bigger than one read, or a call-actor that
    lacks the three limits.
    """
    server = MCPServer("apify-stand-in")
    asked: dict[str, Any] = {}

    async def call_actor(
        actor: str,
        input: dict[str, Any],
        waitSecs: int,  # noqa: N803 - Apify's own name
        callOptions: CallOptions,  # noqa: N803 - Apify's own name
    ) -> CallToolResult:
        """Runs the Actor: its status and its storages."""
        if error_text is not None:
            return CallToolResult(content=[TextContent(type="text", text=error_text)], is_error=True)
        asked["input"] = input
        run = {"status": run_status, "storages": {"datasets": {"default": {"id": "dataset-1"}}}}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(run))], structured_content=run)

    async def call_actor_unpinned(actor: str, input: dict[str, Any]) -> CallToolResult:
        """A call-actor that takes no limits."""
        return await call_actor(actor, input, 18, CallOptions(build="1.0.9", timeout=18, maxTotalChargeUsd=0.01))

    async def actor_tool(locations: list[dict[str, Any]], forecastDays: int, mode: str) -> str:  # noqa: N803
        """The Actor's own tool, listed for the pin; the lane never calls it."""
        return "unused"

    async def get_dataset_items(datasetId: str, limit: int) -> CallToolResult:  # noqa: N803
        """The run's items."""
        items = actor_items(asked["input"])[:limit]
        read = {"items": items, "totalItemCount": total_items if total_items is not None else len(items)}
        return CallToolResult(content=[TextContent(type="text", text="items")], structured_content=read)

    server.add_tool(call_actor if pinned else call_actor_unpinned, name="call-actor")
    server.add_tool(actor_tool, name="gochujang--open-meteo-weather-forecast")
    server.add_tool(get_dataset_items, name="get-dataset-items")
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return server.streamable_http_app(streamable_http_path="/", transport_security=security)
