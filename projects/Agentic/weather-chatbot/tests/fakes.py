"""
tests/fakes.py: stand-ins for Gemini and Open-Meteo, for the unit and browser tests, which never call either: Gemini
needs a key and costs quota, and Open-Meteo's weather changes by the hour.

- FakeModel: a LangChain chat model that calls the tools it's told to, a round at a time, then streams a known answer a
  word at a time, after a pause each. It reports each chunk's share of the tokens, as Gemini does (a delta, not a
  running total), says whether its stream was closed, and can fail on cue.
- OpenMeteoRecordings: an httpx2 handler that answers each request with Open-Meteo's recorded answer for what it asks
  (tests/fixtures/open_meteo/), after a pause; or with a 503, for the paths it's told to fail.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator, Sequence
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
from pydantic import Field

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
