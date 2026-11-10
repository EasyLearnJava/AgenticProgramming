"""
nimbus/answer.py: the answer: the agent's run, as events for the page: each tool call as the model asks for it and as
it ends, and the model's words as it writes them; within the answer's caps, its tokens counted, and every failure
turned into one of our errors. And the finished answer's Markdown, made into HTML that can only ever be text and links.
"""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator, Collection, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, aclosing, asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx2
import structlog
from langchain_core.exceptions import (
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)
from langchain_core.exceptions import ModelTimeoutError as LangChainModelTimeoutError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool, ToolException
from langgraph.graph.state import CompiledStateGraph
from langsmith import tracing_context
from langsmith.run_trees import RunTree
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from nimbus.agent import make_agent, to_agent_config
from nimbus.cache import WeatherCache
from nimbus.constants import ANSWER_TIMEOUT_SECONDS, AUTH_ANSWER_TIMEOUT_SECONDS
from nimbus.errors import (
    WEATHER_UNEXPECTED,
    WEATHER_UNREACHABLE,
    AnswerTimeoutError,
    ConfigError,
    ModelBusyError,
    ModelFailedError,
    NimbusError,
    UpstreamUnavailableError,
)
from nimbus.lanes import REST_NO_AUTH, Lane
from nimbus.model import Tracer
from nimbus.nps_alerts import AlertsCallRecord, NpsAlertsService
from nimbus.open_meteo import OpenMeteoClient
from nimbus.park_tools import (
    PARK_GUIDANCE_UNAVAILABLE,
    KnowledgeCallRecord,
    KnowledgeService,
    make_alert_tools,
    make_park_tools,
    resolve_park,
    undecided_park_query,
)
from nimbus.tools import WEATHER_TOOLS, ToolCallRecord, ToolContext, WeatherTool, make_tools
from nimbus.travel.models import TravelCallRecord
from nimbus.travel.service import TravelTurn
from nimbus.travel.tools import make_travel_tools

# What a link in an answer carries: it opens in a new tab, so the chat stays, and it tells the other site nothing.
LINK_REL = "nofollow noopener noreferrer"
# How Gemini says a key isn't one: a 400 whose details give this reason (it names no provider's class here).
BAD_KEY_REASON = "API_KEY_INVALID"


@dataclass
class AnswerStats:
    """Per-turn token counts, a weather lane failure, and the root ID when this turn starts a traced graph."""

    tokens_in: int = 0
    tokens_out: int = 0
    usage_recorded: bool = False
    agent_started: bool = False
    lane_error: NimbusError | None = None
    trace_id: UUID | None = None


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
    record: ToolCallRecord | KnowledgeCallRecord | AlertsCallRecord | TravelCallRecord | None
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
        stats.usage_recorded = True
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
                record = (
                    message.artifact
                    if isinstance(
                        message.artifact, (ToolCallRecord, KnowledgeCallRecord, AlertsCallRecord, TravelCallRecord)
                    )
                    else None
                )
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
    lane: Lane = REST_NO_AUTH,
    deadline: float | None = None,
    *,
    parent: RunTree | None = None,
) -> AsyncGenerator[AnswerEvent]:
    """
    The agent's run, as events: each tool call as it starts and ends, each piece of the words as the model writes it;
    within 30 s in all. LangSmith traces the run only with a tracer, whose client hides its inputs and outputs, in its
    project: under the parent, the chat request's root, when there is one, else as a root of its own. A failure
    becomes ours: ModelBusyError, AnswerTimeoutError, ConfigError or ModelFailedError.
    """
    if deadline is None:
        deadline = asyncio.get_running_loop().time() + to_answer_seconds(lane)
    client, project = (tracer.client, tracer.project) if tracer is not None else (None, None)
    nested = parent if tracer is not None else None
    # Whether the model has written words yet, and whether a tool call has started since: the words that follow it
    # start a paragraph of their own, rather than running on from "Let me check." (issue 53).
    wrote_words = break_due = False
    try:
        with tracing_context(
            enabled=tracer is not None,
            client=client,
            project_name=project,
            parent=nested if nested is not None else False,
        ):
            # The run's stream is closed however this one ends, so no call to Gemini or Open-Meteo outlives the answer.
            # Two kinds of item: "messages", the model's chunks as it writes; "updates", each node's result as it ends.
            config = to_agent_config(lane)
            if nested is not None:
                # The request's root is already queued: the graph's runs nest under it, and its ID finds them all.
                stats.trace_id = nested.trace_id
            elif tracer is not None:
                stats.trace_id = uuid4()
                config["run_id"] = stats.trace_id
            stats.agent_started = True
            run = agent.astream({"messages": list(messages)}, config, stream_mode=["messages", "updates"])
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
    finally:
        # A root of the graph's own is sent from here; a nested graph's runs are sent with the request's root.
        if tracer is not None and stats.trace_id is not None and nested is None:
            tracer.defer_flush()


def make_http_client() -> httpx2.AsyncClient:
    """
    A new HTTP client, for one answer's calls to Open-Meteo: httpx2's own limits, and the system's certificates. The
    app keeps this factory in its state, and the tests give it one that plays Open-Meteo back.
    """
    return httpx2.AsyncClient()


def to_answer_seconds(lane: Lane) -> float:
    """How long an answer on the lane may take: 30 s, or 50 s on a lane with auth, which runs an Actor (step 10)."""
    return AUTH_ANSWER_TIMEOUT_SECONDS if lane.auth else ANSWER_TIMEOUT_SECONDS


@asynccontextmanager
async def rest_tools(
    http_client: httpx2.AsyncClient, weather_cache: WeatherCache | None = None
) -> AsyncIterator[list[StructuredTool]]:
    """
    REST · no auth's four tools, which call Open-Meteo through the HTTP client given, open for as long as the answer
    is, and closed with it; and keep its answers in the cache given (step 7).
    """
    async with http_client as http:
        yield make_tools(ToolContext(OpenMeteoClient(http, cache=weather_cache)))


@asynccontextmanager
async def lazy_weather_tools(
    context: AbstractAsyncContextManager[list[StructuredTool]], lane: Lane, stats: AnswerStats | None = None
) -> AsyncIterator[list[StructuredTool]]:
    """Open a selected weather lane only when used, sharing one cancellation-safe lifetime across concurrent calls."""
    # ① A document-only question never contacts MCP or Apify. Concurrent weather calls share one setup operation.
    lock = asyncio.Lock()
    opened: dict[str, StructuredTool] | None = None
    failed = False
    ready: asyncio.Future[list[StructuredTool]] = asyncio.get_running_loop().create_future()
    close = asyncio.Event()
    owner: asyncio.Task[None] | None = None

    async def own_lane() -> None:
        """Enter and exit SDK context managers in the same task, as AnyIO's cancel scopes require."""
        try:
            async with context as tools:
                if not ready.done():
                    ready.set_result(tools)
                await close.wait()
        except Exception as error:
            if not ready.done():
                ready.set_exception(error)
            else:
                raise

    try:

        def wrap(definition: WeatherTool) -> StructuredTool:
            """Give a weather tool its existing schema and defer its lane's setup until invocation."""

            async def call(**kwargs: Any) -> tuple[str, ToolCallRecord]:
                """Run the selected lane's real tool and preserve its wire artifact and recoverable errors."""
                nonlocal opened, failed, owner
                async with lock:
                    if opened is None and not failed:
                        try:
                            owner = asyncio.create_task(own_lane())
                            tools = await asyncio.shield(ready)
                            opened = {tool.name: tool for tool in tools}
                        except Exception as error:
                            failed = True
                            if stats is not None:
                                stats.lane_error = (
                                    error if isinstance(error, NimbusError) else UpstreamUnavailableError()
                                )
                            structlog.get_logger().error(
                                "lane.open.failed", lane=lane.id, status="failed", errorClass=type(error).__name__
                            )
                if opened is None:
                    raise ToolException(WEATHER_UNREACHABLE)
                target = opened.get(definition.name)
                if target is None:
                    raise ToolException(WEATHER_UNEXPECTED)
                # ② A tool-call envelope retains the underlying artifact; a bare dict would discard it.
                result = await target.ainvoke(
                    {"type": "tool_call", "id": "weather-operation", "name": definition.name, "args": kwargs}
                )
                if not isinstance(result, ToolMessage):
                    raise ToolException(WEATHER_UNEXPECTED)
                if result.status == "error":
                    raise ToolException(str(result.content))
                if not isinstance(result.artifact, ToolCallRecord):
                    raise ToolException(WEATHER_UNEXPECTED)
                return str(result.content), result.artifact

            return StructuredTool.from_function(
                coroutine=call,
                name=definition.name,
                description=definition.description,
                args_schema=definition.input_model,
                response_format="content_and_artifact",
                handle_tool_error=True,
            )

        # ③ The exit stack closes an opened lane when the answer ends or is cancelled.
        yield [wrap(definition) for definition in WEATHER_TOOLS]
    finally:
        close.set()
        if owner is not None:
            if not ready.done():
                owner.cancel()
            with suppress(asyncio.CancelledError):
                await owner


async def stream_weather_answer(
    model: BaseChatModel,
    messages: Sequence[BaseMessage],
    stats: AnswerStats,
    tracer: Tracer | None,
    tools: AbstractAsyncContextManager[list[StructuredTool]],
    lane: Lane = REST_NO_AUTH,
    deadline: float | None = None,
    *,
    knowledge: KnowledgeService | None = None,
    alerts: NpsAlertsService | None = None,
    travel: TravelTurn | None = None,
    parent: RunTree | None = None,
) -> AsyncGenerator[AnswerEvent]:
    """
    The answer, by the agent with the four weather tools of the question's lane (step 9), open for as long as the
    answer is, and closed with it; its runs nest under the parent, the chat request's root, when there is one. Setup
    failures remain in per-turn state so chat can report their original class.
    """
    latest = messages[-1] if messages else None
    if (
        knowledge is not None
        and isinstance(latest, HumanMessage)
        and isinstance(latest.content, str)
        and (query := undecided_park_query(latest.content))
    ):
        # A genuine local registry call, observed in Activity and the chat chip. Neither park was chosen.
        name, call_id = "resolve_destination", uuid4().hex
        yield ToolStarted(call_id, name, {"query": query})
        try:
            content, record = await resolve_park(knowledge, query)
            status = json.loads(content).get("status", "unavailable")
        except ToolException:
            status = "unavailable"
        if status == "unavailable":
            yield ToolEnded(call_id, name, PARK_GUIDANCE_UNAVAILABLE, None, True)
            yield "The park guidance is unavailable right now. Which park would you like to check?"
        else:
            yield ToolEnded(call_id, name, content, record, False)
            if status == "ambiguous":
                yield f"Preparation guidance depends on the destination. Which park are you visiting, {query}?"
            else:
                yield "I couldn't verify both destinations in the park guides. Which park would you like to check?"
        return
    context = lazy_weather_tools(tools, lane, stats) if knowledge is not None or travel is not None else tools
    async with context as weather_tools:
        knowledge_tools = make_park_tools(knowledge) if knowledge is not None else []
        notice_tools = make_alert_tools(alerts) if alerts is not None and knowledge is not None else []
        travel_tools = make_travel_tools(travel) if travel is not None else []
        agent = make_agent(model, [*weather_tools, *knowledge_tools, *notice_tools, *travel_tools])
        async with aclosing(stream_answer(agent, messages, stats, tracer, lane, deadline, parent=parent)) as events:
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


def is_weather_authority(url: str) -> bool:
    """Recognize reviewed weather-alert publishers, separate from park preparation citations."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname
        in {
            "www.weather.gov",
            "weather.gov",
            "www.nhc.noaa.gov",
            "www.metoffice.gov.uk",
            "weather.gc.ca",
            "www.bom.gov.au",
        }
        and not parts.username
        and not parts.password
        and port in (None, 443)
        and parts.path in ("", "/")
        and not parts.query
        and not parts.fragment
    )


def render_answer(text: str, *, park_sources: Collection[str] | None = None) -> Markup:
    """
    The finished answer's HTML, from the model's Markdown. Safe to put in a template as it is: with raw HTML off, every
    tag in it is markdown-it's own, and markdown-it never makes a link of a javascript: address.
    """
    # Exact evidence URLs and the reviewed weather homepages are clickable. Keep other labels as plain text.
    park_sources = park_sources or ()
    tokens = ANSWER_MARKDOWN.parse(text)
    for block in tokens:
        if not block.children:
            continue
        children = []
        permitted = True
        for token in block.children:
            if token.type == "link_open":
                value = token.attrGet("href")
                href = value if isinstance(value, str) else ""
                permitted = href in park_sources or is_weather_authority(href)
                if permitted:
                    children.append(token)
            elif token.type == "link_close":
                if permitted:
                    children.append(token)
                permitted = True
            else:
                children.append(token)
        block.children = children
    return Markup(ANSWER_MARKDOWN.renderer.render(tokens, ANSWER_MARKDOWN.options, {}))  # noqa: S704
