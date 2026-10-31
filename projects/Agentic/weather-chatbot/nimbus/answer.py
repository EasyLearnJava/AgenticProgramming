"""
nimbus/answer.py: the answer: the agent's run, as events for the page: each tool call as the model asks for it and as
it ends, and the model's words as it writes them; within the answer's caps, its tokens counted, and every failure
turned into one of our errors. And the finished answer's Markdown, made into HTML that can only ever be text and links.
"""

import asyncio
from collections.abc import AsyncGenerator, Iterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any, cast

import httpx2
from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)
from langchain_core.exceptions import ModelTimeoutError as LangChainModelTimeoutError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from nimbus.agent import AGENT_CONFIG, make_agent
from nimbus.constants import ANSWER_TIMEOUT_SECONDS
from nimbus.errors import AnswerTimeoutError, ConfigError, ModelBusyError, ModelFailedError, NimbusError
from nimbus.model import Tracer
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import ToolCallRecord, ToolContext, make_tools

# What a link in an answer carries: it opens in a new tab, so the chat stays, and it tells the other site nothing.
LINK_REL = "nofollow noopener noreferrer"
# How Gemini says a key isn't one: a 400 whose details give this reason (it names no provider's class here).
BAD_KEY_REASON = "API_KEY_INVALID"


@dataclass
class AnswerStats:
    """What the model reported about an answer: its tokens in and out, added up chunk by chunk, over all its calls."""

    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(frozen=True)
class ToolStarted:
    """The model asked for a tool: the call's id, the tool's name, and its input."""

    call_id: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ToolEnded:
    """
    A tool call ended: its id and tool, what the model read (the weather, or our sentence), the record of its request
    when it's done, and whether it failed.
    """

    call_id: str
    name: str
    content: str
    record: ToolCallRecord | None
    failed: bool


# What an answer gives the page, as it comes: a tool call starting or ending, or a piece of the model's words.
type AnswerEvent = ToolStarted | ToolEnded | str
# What sets words written before a tool call apart from the words after it: a new paragraph.
PARAGRAPH_BREAK = "\n\n"


def is_set_up_wrong(error: BaseException) -> bool:
    """
    Whether a model's error says this deployment is set up wrong: a key refused (401, 403, or Gemini's 400 with
    API_KEY_INVALID), or a model name the provider doesn't know (404).
    """
    if isinstance(error, (ModelAuthenticationError, ModelPermissionDeniedError, ModelNotFoundError)):
        return True
    return isinstance(error, ModelInvalidRequestError) and BAD_KEY_REASON in f"{error} {error.__cause__}"


def _from_message(payload: tuple[Any, Any], stats: AnswerStats) -> Iterator[str]:
    """A chunk of the model's words: its share of the tokens, added up, and its text, if it has any."""
    chunk, _metadata = payload
    if not isinstance(chunk, AIMessageChunk):
        return
    if chunk.usage_metadata is not None:
        stats.tokens_in += chunk.usage_metadata["input_tokens"]
        stats.tokens_out += chunk.usage_metadata["output_tokens"]
    if chunk.text:
        yield chunk.text


def _from_update(payload: dict[str, Any]) -> Iterator[ToolStarted | ToolEnded]:
    """A node's update: the model's tool calls, once it has asked for them; a tool's message, once its call ended."""
    for update in payload.values():
        if not isinstance(update, dict):
            continue
        for message in update.get("messages", []):
            if isinstance(message, ToolMessage):
                record = message.artifact if isinstance(message.artifact, ToolCallRecord) else None
                failed = message.status == "error"
                yield ToolEnded(message.tool_call_id, message.name or "", str(message.content), record, failed)
            elif isinstance(message, AIMessage):
                for call in message.tool_calls:
                    yield ToolStarted(call["id"] or "", call["name"], call["args"])


async def stream_answer(
    agent: CompiledStateGraph[Any, Any, Any, Any],
    messages: Sequence[BaseMessage],
    stats: AnswerStats,
    tracer: Tracer | None,
) -> AsyncGenerator[AnswerEvent]:
    """
    The agent's run, as events: each tool call as it starts and ends, each piece of the words as the model writes it;
    within 30 s in all. LangSmith traces the run only with a tracer, whose client hides its inputs and outputs, in its
    project. A failure becomes ours: ModelBusyError, AnswerTimeoutError, ConfigError or ModelFailedError.
    """
    deadline = asyncio.get_running_loop().time() + ANSWER_TIMEOUT_SECONDS
    client, project = (tracer.client, tracer.project) if tracer is not None else (None, None)
    # Whether the model has written words yet, and whether a tool call has started since: the words that follow it
    # start a paragraph of their own, rather than running on from "Let me check." (issue 53).
    wrote_words = break_due = False
    try:
        with tracing_context(enabled=tracer is not None, client=client, project_name=project):
            # The run's stream is closed however this one ends, so no call to Gemini or Open-Meteo outlives the answer.
            # Two kinds of item: "messages", the model's chunks as it writes; "updates", each node's result as it ends.
            run = agent.astream({"messages": list(messages)}, AGENT_CONFIG, stream_mode=["messages", "updates"])
            stream = cast("AsyncGenerator[tuple[str, Any]]", run)
            async with aclosing(stream) as items:
                while True:
                    # ① The next item, before the deadline: only this wait is timed, never the time the page takes
                    # between two events, so a deadline that passes lands here, as ours to name (issue 38).
                    async with asyncio.timeout_at(deadline):
                        item = await anext(items, None)
                    if item is None:
                        return
                    mode, payload = item
                    if mode == "messages":
                        # ② The words and their tokens.
                        for piece in _from_message(payload, stats):
                            yield f"{PARAGRAPH_BREAK}{piece}" if break_due else piece
                            wrote_words, break_due = True, False
                    else:
                        # ③ The tool calls, starting and ending.
                        for event in _from_update(payload):
                            break_due = break_due or (wrote_words and isinstance(event, ToolStarted))
                            yield event
    # ④ A failure, as one of ours; the model's own error is kept as its cause, for the logs' class. A sixth call to the
    # model (LangGraph's GraphRecursionError) is a failure too.
    except NimbusError:
        raise
    except (TimeoutError, LangChainModelTimeoutError) as error:
        raise AnswerTimeoutError from error
    except ModelRateLimitError as error:
        raise ModelBusyError from error
    except Exception as error:
        if is_set_up_wrong(error):
            raise ConfigError from error
        raise ModelFailedError from error


def make_http_client() -> httpx2.AsyncClient:
    """
    A new HTTP client, for one answer's calls to Open-Meteo: httpx2's own limits, and the system's certificates. The
    app keeps this factory in its state, and the tests give it one that plays Open-Meteo back.
    """
    return httpx2.AsyncClient()


async def stream_weather_answer(
    model: BaseChatModel,
    messages: Sequence[BaseMessage],
    stats: AnswerStats,
    tracer: Tracer | None,
    http_client: httpx2.AsyncClient,
) -> AsyncGenerator[AnswerEvent]:
    """
    The answer, by the agent with the four weather tools, which call Open-Meteo through the HTTP client given, open for
    as long as the answer is, and closed with it.
    """
    async with http_client as http:
        agent = make_agent(model, make_tools(ToolContext(OpenMeteoClient(http))))
        async with aclosing(stream_answer(agent, messages, stats, tracer)) as events:
            async for event in events:
                yield event


def _link_open(renderer: RendererHTML, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
    """Renders a link's opening tag: in a new tab, telling the other site nothing (LINK_REL)."""
    tokens[idx].attrSet("rel", LINK_REL)
    tokens[idx].attrSet("target", "_blank")
    return renderer.renderToken(tokens, idx, options, env)


def _create_markdown() -> MarkdownIt:
    """CommonMark with raw HTML off and pictures off: an answer can hold text, emphasis, lists, code and links."""
    markdown = MarkdownIt("commonmark", {"html": False}).disable("image")
    markdown.add_render_rule("link_open", _link_open)
    return markdown


ANSWER_MARKDOWN = _create_markdown()


def render_answer(text: str) -> Markup:
    """
    The finished answer's HTML, from the model's Markdown. Safe to put in a template as it is: with raw HTML off, every
    tag in it is markdown-it's own, and markdown-it never makes a link of a javascript: address.
    """
    return Markup(ANSWER_MARKDOWN.render(text))  # noqa: S704
