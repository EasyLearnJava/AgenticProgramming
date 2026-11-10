"""
nimbus/chat.py: POST /api/chat: the chat's one route. The page's form posts a question, with the browser's locale and
time zone; the answer comes back as server-sent events, each holding HTML that htmx puts into the page: the question
and Nimbus's answer, empty and busy; a chip for each tool call, as the model asks for it and as it ends; each piece of
the answer as the model writes it; then the finished answer, its Markdown made HTML. A request that breaks a rule gets
our own sentence, as HTML, before any work is done. The answer is the agent's (nimbus/agent.py, nimbus/answer.py):
Gemini, with the four weather tools (nimbus/tools.py), told its rules by nimbus/prompts.py.
"""

import asyncio
import json
import re
import time
import zoneinfo
from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager, aclosing, nullcontext, suppress
from http import HTTPStatus
from typing import Annotated, Literal, Self
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from nimbus.answer import (
    AnswerEvent,
    AnswerStats,
    ToolEnded,
    ToolStarted,
    render_answer,
    rest_tools,
    stream_weather_answer,
    to_answer_seconds,
)
from nimbus.auth_lanes import open_mcp_with_auth, open_rest_with_auth
from nimbus.chips import ToolChip
from nimbus.config import Settings
from nimbus.constants import (
    CHAT_BODY_MAX_BYTES,
    CHAT_FORM_MAX_FIELDS,
    DEFAULT_LOCALE,
    DEFAULT_TIME_ZONE,
    ERROR_HEADER,
    EVENT_STREAM,
    FORM_MEDIA_TYPE,
    HISTORY_ANSWER_MAX_CHARS,
    HISTORY_MAX_CHARS,
    HISTORY_MAX_MESSAGES,
    NO_STORE,
    QUESTION_MAX_CHARS,
)
from nimbus.errors import (
    BODY_TOO_LARGE,
    EMPTY_QUESTION,
    HISTORY_TOO_LONG,
    HISTORY_UNREADABLE,
    LANE_CLOSED,
    LANE_NEEDS_TOKEN,
    QUESTION_TOO_LONG,
    UNREADABLE,
    ConfigError,
    InputError,
    NimbusError,
    to_user_message,
)
from nimbus.feedback import answer_ref
from nimbus.forecast_horizon import forecast_limit_reply
from nimbus.lanes import MCP_NO_AUTH, MCP_WITH_AUTH, REST_WITH_AUTH, Lane, LaneId, get_lane, is_open
from nimbus.mcp_lane import open_mcp_lane
from nimbus.memory.context import load_memory
from nimbus.memory.intake import memory_intent
from nimbus.memory.models import PreferenceProfile
from nimbus.memory.routes import view_context
from nimbus.nps_alerts import AlertsCallRecord
from nimbus.pages import templates
from nimbus.park_tools import KnowledgeCallRecord
from nimbus.prompts import to_messages
from nimbus.request_trace import CacheTraceStep, RequestTrace
from nimbus.semantic_cache.evidence import cached_cards
from nimbus.semantic_cache.identity import set_scope
from nimbus.semantic_cache.integration import CacheTurn
from nimbus.semantic_cache.integration import prepare as prepare_cache
from nimbus.travel import briefing
from nimbus.travel.city_intake import city_trip_reply
from nimbus.travel.hotel_intake import hotel_dates_reply
from nimbus.travel.models import TRAVEL_ANSWER_RESERVE_SECONDS, TravelCallRecord
from nimbus.travel.preferences import analyze_with_preferences
from nimbus.travel.service import TravelService
from nimbus.utils import is_usable_locale, new_turn_id, to_currency, to_ms, to_ref, to_sse_message
from nimbus.weather_cards import to_weather_cards

router = APIRouter()
# The status a request gets when the browser went before it was answered, as nginx logs it: no one reads it.
HTTP_CLIENT_CLOSED_REQUEST = 499
# Every time zone the IANA database names (tzdata's), read once: a time zone the page sends must be one of them.
TIME_ZONES = frozenset(zoneinfo.available_timezones())


class HistoryMessage(BaseModel):
    """One message of the conversation so far, as the page sends it back: who wrote it, and its text, trimmed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=HISTORY_ANSWER_MAX_CHARS)]


class ChatRequest(BaseModel):
    """
    What the chat's form sends, checked: the question, trimmed, 1 to 2,000 characters, and no field we don't know; the
    browser's locale and time zone, which come from the browser, not the visitor, and take the default when we can't use
    them (issue 40); and the conversation so far (step 6), untrusted: questions and answers in turn, capped.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_CHARS)]
    locale: str = DEFAULT_LOCALE
    time_zone: str = DEFAULT_TIME_ZONE
    history: tuple[HistoryMessage, ...] = ()
    lane: LaneId = "rest-no-auth"
    cache_receipt: str = Field(default="", max_length=64, pattern=r"^(?:[a-f0-9]{64})?$")

    @field_validator("history", mode="before")
    @classmethod
    def history_from_json(cls, value: object) -> object:
        """
        The conversation so far, which the page sends as JSON in one field; an empty field is no conversation. JSON
        nested deeper than Python can read is unreadable, like any other (issue 56).
        """
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value) if value.strip() else []
        except RecursionError as error:
            raise ValueError("history_unreadable") from error

    @model_validator(mode="after")
    def history_in_turns(self) -> Self:
        """
        The conversation's rules: a question, then its answer, in turn, the visitor's first; at most the last 10
        messages, a question at most 2,000 characters, all at most 16,000.
        """
        roles = [message.role for message in self.history]
        if roles != ["user", "assistant"] * (len(roles) // 2) or len(roles) % 2:
            raise ValueError("history_not_in_turns")
        too_long_question = any(m.role == "user" and len(m.text) > QUESTION_MAX_CHARS for m in self.history)
        total = sum(len(message.text) for message in self.history)
        if len(self.history) > HISTORY_MAX_MESSAGES or too_long_question or total > HISTORY_MAX_CHARS:
            raise ValueError("history_too_long")
        return self

    @field_validator("locale", mode="before")
    @classmethod
    def usable_locale(cls, value: object) -> object:
        """A language tag of at most 35 characters, letters, digits and hyphens; else the default."""
        return value if isinstance(value, str) and is_usable_locale(value) else DEFAULT_LOCALE

    @field_validator("time_zone", mode="before")
    @classmethod
    def usable_time_zone(cls, value: object) -> object:
        """A time zone the IANA database names, never a path; else the default."""
        return value if isinstance(value, str) and value in TIME_ZONES else DEFAULT_TIME_ZONE


class EventStream(StreamingResponse):
    """
    A stream of server-sent events, never cached, from a source that has already made its first event: so its own
    code is running, and however the stream ends, closing it runs that code's end, which logs how the answer ended,
    within its request, before the request's own line. A browser that has gone isn't an error.
    """

    media_type = EVENT_STREAM

    def __init__(self, first: str, source: AsyncGenerator[str]) -> None:
        """The stream of the source's first event, already made, then the rest."""
        self.source = source
        self.events = self.first_then_rest(first)
        super().__init__(self.events, headers={"cache-control": NO_STORE})

    async def first_then_rest(self, first: str) -> AsyncGenerator[str]:
        """The first event, then each of the source's others."""
        yield first
        async for event in self.source:
            yield event

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Streams the events until they end or the browser goes, which some servers report as a failed send; then,
        however that ended, closes the events and their source, which the browser may have left unread.
        """
        try:
            with suppress(ClientDisconnect):
                await super().__call__(scope, receive, send)
        finally:
            await self.events.aclose()
            await self.source.aclose()


def to_input_error(error: ValidationError) -> InputError:
    """
    The rule a form broke, from Pydantic's account of it: a field we don't know (the form can't be read); else too long
    a question, or none.
    """
    errors = error.errors()
    # ① The conversation so far: too long, or unreadable, whether its field or its turns broke the rule.
    history = [problem for problem in errors if not problem["loc"] or problem["loc"][0] == "history"]
    if history:
        if any("history_too_long" in problem["msg"] or problem["type"] == "string_too_long" for problem in history):
            return InputError("history_too_long", HISTORY_TOO_LONG)
        return InputError("history_unreadable", HISTORY_UNREADABLE)
    # ② The lane: one that isn't open yet, or none we know (step 9).
    if any(problem["loc"] and problem["loc"][0] == "lane" for problem in errors):
        return InputError("lane_closed", LANE_CLOSED)
    problems = {(str(problem["loc"][0]) if problem["loc"] else "", problem["type"]) for problem in errors}
    if any(field != "question" for field, _ in problems):
        return InputError("form_unreadable", UNREADABLE)
    if ("question", "string_too_long") in problems:
        return InputError("question_too_long", QUESTION_TOO_LONG)
    return InputError("question_empty", EMPTY_QUESTION)


async def read_body(request: Request, max_bytes: int) -> bytes:
    """
    The request's body; InputError (413) once it's longer than max_bytes: from its declared length, before a byte is
    read, if it has one; else as it's read, in chunks.
    """
    too_large = InputError("body_too_large", BODY_TOO_LARGE, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    declared = request.headers.get("content-length", "")
    if declared.isascii() and declared.isdecimal() and int(declared) > max_bytes:
        raise too_large
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


def to_defaulted(fields: Mapping[str, str], chat_request: ChatRequest) -> list[str]:
    """Which of the browser's values took the default, though the form sent one: for the logs."""
    sent = {name: fields.get(name, "") for name in ("locale", "time_zone")}
    return [name for name, value in sent.items() if value and value != getattr(chat_request, name)]


async def read_chat_request(request: Request) -> tuple[ChatRequest, list[str]]:
    """
    The question the chat's form sent, checked, and which of the browser's values took the default; InputError, with
    the broken rule's sentence, for any other request.
    """
    # ① A form, as the page sends it; anything else isn't read at all.
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != FORM_MEDIA_TYPE:
        raise InputError("not_a_form", UNREADABLE, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
    # ② Its body, at most 256 KiB, and its fields: UTF-8, each one once.
    body = await read_body(request, CHAT_BODY_MAX_BYTES)
    try:
        pairs = parse_qsl(body.decode(), keep_blank_values=True, errors="strict", max_num_fields=CHAT_FORM_MAX_FIELDS)
    except ValueError:  # UnicodeDecodeError is one, and so is a body with too many fields
        raise InputError("form_unreadable", UNREADABLE) from None
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InputError("form_unreadable", UNREADABLE)
    # ③ The question, trimmed, not empty, not too long; no other field; the locale and time zone, ones we can use.
    try:
        chat_request = ChatRequest.model_validate(fields)
    except ValidationError as error:
        raise to_input_error(error) from None
    return chat_request, to_defaulted(fields, chat_request)


def render_part(template: str, context: Mapping[str, object]) -> str:
    """Part of the chat's page, from its template, for one event; Jinja2 escapes every value put into it."""
    return templates.get_template(template).render(context).strip()


def to_tool_event(turn_id: str, chip: ToolChip, is_new: bool) -> str:
    """A tool call's event: its chip, new at the end of the turn's list, or in place of the one it was."""
    return to_sse_message(render_part("chat_tool.html", {"turn_id": turn_id, "chip": chip, "is_new": is_new}))


async def stream_turn(
    answer: AsyncGenerator[AnswerEvent],
    question: str,
    request_id: str,
    stats: AnswerStats,
    model_name: str,
    *,
    restrict_links: bool = False,
    memory_note: str = "",
    cache_turn: CacheTurn | None = None,
    request_trace: RequestTrace | None = None,
) -> AsyncGenerator[str]:
    """
    A turn of the chat, as server-sent events: the two messages; each tool call's chip as it starts and as it ends;
    each piece of the answer; then the answer's end, with every chip as it ended. Its ending lines name the chat
    request's trace, when there's one, else the graph's own.
    """
    log = structlog.get_logger()
    turn_id = new_turn_id()
    started = time.perf_counter()
    pieces: list[str] = []
    chips: dict[str, ToolChip] = {}
    evidence_urls: set[str] = set()
    # Whether the whole answer has been sent and logged: what follows (the cache save) can't change its ending.
    answered = False

    def ending() -> dict[str, object]:
        """What every line about the answer's end holds: its length, its time, its tool calls, its tokens, the model."""
        trace_id = request_trace.trace_id if request_trace is not None else stats.trace_id
        return {
            "workflow": "agent" if stats.agent_started else "intake",
            "answerChars": len("".join(pieces)),
            "answerRef": answer_ref(turn_id),
            "ms": to_ms(time.perf_counter() - started),
            "toolCalls": len(chips),
            **({"tokensIn": stats.tokens_in, "tokensOut": stats.tokens_out} if stats.usage_recorded else {}),
            "model": model_name,
            **({"traceId": str(trace_id)} if trace_id is not None else {}),
        }

    def final_chips() -> list[ToolChip]:
        """Every chip as the answer ended: a call still running then is marked stopped."""
        for chip in chips.values():
            chip.stop()
        return list(chips.values())

    try:
        # ① The question, and Nimbus's answer, still empty and marked busy, added to the conversation.
        yield to_sse_message(render_part("chat_turn.html", {"question": question, "turn_id": turn_id}))
        # ② Each tool call's chip, added as the model asks for the tool, then put in place of itself as the call ends;
        # each piece of the answer, added to it as the model writes it. The agent's stream is closed however the turn
        # ends.
        async with aclosing(answer) as events:
            async for event in events:
                if isinstance(event, ToolStarted):
                    restrict_links = restrict_links or event.name in {
                        "resolve_destination",
                        "search_park_guidance",
                        "get_park_alerts",
                        "search_flights",
                        "search_hotels",
                    }
                    chip = chips[event.call_id] = ToolChip.start(len(chips), event)
                    yield to_tool_event(turn_id, chip, is_new=True)
                elif isinstance(event, ToolEnded):
                    if event.name == "search_park_guidance" and isinstance(event.record, KnowledgeCallRecord):
                        evidence_urls.update(source.url for source in event.record.sources)
                    if isinstance(event.record, (AlertsCallRecord, TravelCallRecord)):
                        evidence_urls.update(event.record.sources)
                    if (ended := chips.get(event.call_id)) is not None:
                        ended.end(event)
                        yield to_tool_event(turn_id, ended, is_new=False)
                else:
                    pieces.append(event)
                    yield to_sse_message(render_part("chat_piece.html", {"turn_id": turn_id, "text": event}))
        # ③ The finished answer, its Markdown made HTML, no longer busy, in place of the one being written.
        if stats.lane_error is not None:
            raise stats.lane_error
        done: dict[str, object] = {
            "turn_id": turn_id,
            "answer": render_answer("".join(pieces), park_sources=evidence_urls if restrict_links else None),
            "chips": final_chips(),
            "weather_cards": to_weather_cards(list(chips.values())),
            "memory_note": memory_note,
        }
        if cache_turn is not None:
            # The receipt proves which conversation Nimbus produced; it doesn't depend on the save, so it can't wait.
            done["cache_receipt"] = cache_turn.receipt_for(str(done["answer"]))
        yield to_sse_message(render_part("chat_end.html", done))
        log.info("chat.done", **ending())
        answered = True
        # ⑥ Kept for reuse only once the visitor has the whole answer, so Qdrant's time never delays it. The stream
        # stays open until the save ends, within the save's own deadline.
        if cache_turn is not None:
            storing: AbstractContextManager[CacheTraceStep | None] = (
                request_trace.step("store") if request_trace is not None else nullcontext()
            )
            with storing as cache_step:
                completion = await cache_turn.completed(
                    "".join(pieces), list(chips.values()), str(done["answer"]), trace=cache_step
                )
                if cache_step is not None:
                    cache_step.outcome(completion.store.status, completion.store.reason)
    except (asyncio.CancelledError, GeneratorExit):
        # ④ Stop, or the page went away: nothing more can be sent. An answer already delivered has its ending.
        if not answered:
            log.info("chat.aborted", **ending())
        raise
    except Exception as error:
        if answered:
            # The answer was delivered and logged; a failure while keeping it for reuse changes nothing for it.
            log.warning("semantic_cache.store_failed", errorClass=type(error).__name__)
            return
        # ⑤ A failure: the answer so far, then our own sentence and the ref that finds the request's lines, never the
        # error's own text, which stays out of the logs too; the model's own error is logged by its class.
        cause = error.__cause__
        causes = {"causeClass": type(cause).__name__} if cause is not None else {}
        if request_trace is not None:
            request_trace.failed = True
        log.error("chat.failed", errorClass=type(error).__name__, **causes, **ending())
        note = f"{to_user_message(error)} (ref {to_ref(request_id)})"
        failed: dict[str, object] = {
            "turn_id": turn_id,
            "answer": render_answer("".join(pieces), park_sources=evidence_urls if restrict_links else None),
            "failed": True,
            "note": note,
            "chips": final_chips(),
            "weather_cards": to_weather_cards(list(chips.values())),
            "memory_note": memory_note,
        }
        yield to_sse_message(render_part("chat_end.html", failed))


def refusal(error: NimbusError) -> HTMLResponse:
    """Our own sentence for a request we can't answer, as Nimbus's message, marked as ours, with the error's status."""
    return HTMLResponse(
        render_part("chat_rejected.html", {"message": error.user_message}),
        status_code=error.status_code,
        headers={ERROR_HEADER: "1"},
    )


def open_lane_tools(request: Request, lane: Lane, deadline: float) -> AbstractAsyncContextManager[list[StructuredTool]]:
    """
    The lane's four tools, for one answer: on REST · no auth, calling Open-Meteo through a new HTTP client; on MCP ·
    no auth, calling our own MCP server on this same deployment (step 9); on the lanes with auth, the forecast through
    Apify's Actor, falling back to the twin before the deadline, and the other three the twin's (step 10).
    """
    state = request.app.state
    settings: Settings = state.settings
    bypass, token = settings.vercel_automation_bypass_secret, settings.apify_token
    if lane == MCP_NO_AUTH:
        return open_mcp_lane(state.to_mcp_url(request, settings), state.make_mcp_http_client(), bypass)
    if lane == REST_WITH_AUTH and token is not None:
        apify_http = state.make_apify_http_client()
        return open_rest_with_auth(state.make_http_client(), state.weather_cache, apify_http, token, deadline)
    if lane == MCP_WITH_AUTH and token is not None:
        url, apify_http = state.to_mcp_url(request, settings), state.make_apify_http_client()
        mcp_http, cache = state.make_mcp_http_client(), state.weather_cache
        return open_mcp_with_auth(url, mcp_http, bypass, apify_http, token, deadline, cache)
    return rest_tools(state.make_http_client(), state.weather_cache)


@router.post("/api/chat")
async def chat(request: Request) -> Response:
    """
    A question's answer, streamed as server-sent events of HTML that htmx puts into the page; or, for a request that
    breaks a rule, our own sentence as HTML, with its status and the header that marks it as ours, as for a deployment
    with no model; or, for a browser that went while sending its question, 499 and nothing more.
    """
    log = structlog.get_logger()
    started = time.perf_counter()
    settings: Settings = request.app.state.settings
    # ① The question, checked: a broken rule gets our sentence; a browser gone while sending it, nothing at all.
    try:
        chat_request, defaulted = await read_chat_request(request)
    except InputError as error:
        log.info("chat.rejected", code=error.code, status=error.status_code)
        return refusal(error)
    except ClientDisconnect:
        log.info("chat.aborted", answerChars=0, ms=to_ms(time.perf_counter() - started))
        return Response(status_code=HTTP_CLIENT_CLOSED_REQUEST)
    # A lane with auth is open only with Apify's token (step 10).
    lane = get_lane(chat_request.lane)
    if not is_open(lane, settings):
        closed = InputError("lane_needs_token", LANE_NEEDS_TOKEN)
        log.info("chat.rejected", code=closed.code, status=closed.status_code)
        return refusal(closed)
    # The question's length, never its text; and which of the browser's values took the default, if any did.
    extra: dict[str, object] = {"defaulted": defaulted} if defaulted else {}
    if chat_request.history:
        extra["historyMessages"] = len(chat_request.history)
    log.info("chat.request", questionChars=len(chat_request.question), lane=chat_request.lane, **extra)
    # ② The request's own trace, begun before its first step: the Mem0 read, the weather answer cache and the agent
    # nest in it. A streamed response ends it as its events end; any other response, or a failure, ends it here.
    # An app made for one workflow (the replay harness's intake client) may have no tracer at all.
    request_trace = RequestTrace.begin(getattr(request.app.state, "tracer", None))
    try:
        response = await answer_question(request, chat_request, lane, started, request_trace)
    except BaseException as error:
        request_trace.failed = isinstance(error, Exception)
        request_trace.end()
        raise
    if not isinstance(response, EventStream):
        request_trace.end()
    return response


async def answer_question(
    request: Request, chat_request: ChatRequest, lane: Lane, started: float, request_trace: RequestTrace
) -> Response:
    """
    A checked question's response: a preference preview, a trip form or clarification, a reused weather answer, or
    the agent's answer, in that order of priority; each streamed one's events end its request's trace.
    """
    log = structlog.get_logger()
    settings: Settings = request.app.state.settings
    memory_command = memory_intent(chat_request.question, PreferenceProfile())
    memory = await load_memory(request, include_paused=memory_command is not None, trace=request_trace.parent)
    if memory_command is not None:
        request_trace.cache_outcome("bypass", "workflow")
        request_trace.workflow = "memory"
        saved = memory.snapshot.preferences if memory.snapshot.status == "ready" else PreferenceProfile()
        command = memory_intent(chat_request.question, saved)
        assert command is not None  # noqa: S101 - the same question was recognized above
        turn_id = new_turn_id()

        async def memory_events() -> AsyncGenerator[str]:
            """An explicit memory request previews normalized fields without calling Gemini or saving a fact."""
            yield to_sse_message(render_part("chat_turn.html", {"turn_id": turn_id, "question": chat_request.question}))
            context = view_context(request, memory.identity, memory.snapshot)
            context.update(
                turn_id=turn_id,
                message=command.message,
                preferences=(
                    command.preferences
                    if command.kind == "preview"
                    and memory.snapshot.status in {"empty", "ready"}
                    and not (memory.identity and memory.identity.mode == "deleting")
                    else None
                ),
            )
            if memory.snapshot.status not in {"empty", "ready"}:
                context["error"] = "Saved preferences could not be verified. Open My preferences to review them."
            elif not context["configured"]:
                context["error"] = "Preference memory is not configured here. You can still give details for each trip."
            html = render_part("chat_memory.html", context)
            yield to_sse_message(f'<hx-partial hx-target="#turn-{turn_id}" hx-swap="outerHTML">{html}</hx-partial>')
            log.info(
                "chat.done",
                workflow="intake",
                memoryIntake=True,
                answerRef=answer_ref(turn_id),
                answerChars=len(command.message),
                toolCalls=0,
                ms=to_ms(time.perf_counter() - started),
                **request_trace.fields(),
            )

        memory_stream = request_trace.wrap(memory_events())
        response = EventStream(await anext(memory_stream), memory_stream)
        response.headers["vary"] = "Cookie"
        return response
    preferences = memory.preferences
    memory_note = ""
    if any(preferences.model_dump().values()):
        memory_note = "Saved travel preferences are available for this answer. Your current instructions take priority."
    elif memory.snapshot.status in {"unavailable", "conflict", "pending"}:
        memory_note = "Saved preferences are unavailable for this answer. Nimbus is using your current details."
    # Open a trip intake before accessing the model. Only an explicit planning request needs this workflow.
    enabled = tuple(
        name
        for name, active in (("search_flights", settings.flights_enabled), ("search_hotels", settings.hotels_enabled))
        if active
    )
    prior_questions = [message.text for message in chat_request.history if message.role == "user"]
    previous_user_text = prior_questions[-1] if prior_questions else ""
    knowledge = request.app.state.park_knowledge
    now = briefing.utc_now()
    intent = (
        analyze_with_preferences(
            chat_request.question, knowledge, previous_user_text, now, chat_request.time_zone, preferences
        )
        if settings.parks_enabled
        else None
    )
    intake_reply = None
    reply_kind = "cityTripIntake"
    if intent is None:
        intake_reply = city_trip_reply(
            chat_request.question,
            enabled,
            now,
            chat_request.time_zone,
            prior_questions,
            knowledge,
            preferences=preferences,
        )
        if intake_reply is None and settings.hotels_enabled:
            intake_reply = hotel_dates_reply(chat_request.question)
            reply_kind = "hotelDateIntake"
        if intake_reply is None:
            intake_reply = forecast_limit_reply(chat_request.question, now, chat_request.time_zone)
            reply_kind = "forecastHorizon"
    if intent or intake_reply:
        request_trace.cache_outcome("bypass", "workflow")
        turn_id = new_turn_id()

        async def intake_events() -> AsyncGenerator[str]:
            """Prime the turn before sending so even an immediate disconnect has a recorded ending."""
            try:
                yield to_sse_message(
                    render_part("chat_turn.html", {"turn_id": turn_id, "question": chat_request.question})
                )
                if intent is not None:
                    prefs = briefing.BriefPreferences.from_intent(
                        intent, chat_request.locale, lane, chat_request.time_zone
                    )
                    context = await briefing.briefing_context(request, intent, prefs, open_lane_tools, now, turn_id)
                    yield to_sse_message(render_part("chat_trip.html", context))
                    intake_type = {"tripForm": "conditions" not in context}
                    workflow = "briefing" if "conditions" in context else "intake"
                    if "conditions" in context:
                        request_trace.workflow = "briefing"
                else:
                    answer = render_answer(intake_reply or "", park_sources=())
                    yield to_sse_message(
                        render_part("chat_end.html", {"turn_id": turn_id, "answer": answer, "memory_note": memory_note})
                    )
                    intake_type = {reply_kind: True}
                    workflow = "intake"
                log.info(
                    "chat.done",
                    workflow=workflow,
                    answerRef=answer_ref(turn_id),
                    answerChars=len(intake_reply or ""),
                    toolCalls=0,
                    ms=to_ms(time.perf_counter() - started),
                    **intake_type,
                    **request_trace.fields(),
                )
            except (asyncio.CancelledError, GeneratorExit):
                log.info(
                    "chat.aborted", answerChars=0, ms=to_ms(time.perf_counter() - started), **request_trace.fields()
                )
                raise
            except Exception as error:
                request_trace.failed = True
                log.error(
                    "chat.failed",
                    answerRef=answer_ref(turn_id),
                    errorClass=type(error).__name__,
                    answerChars=0,
                    ms=to_ms(time.perf_counter() - started),
                    **request_trace.fields(),
                )
                note = f"{to_user_message(error)} (ref {to_ref(request.state.request_id)})"
                failed = {"turn_id": turn_id, "answer": "", "failed": True, "note": note, "chips": []}
                yield to_sse_message(render_part("chat_end.html", failed))

        request_trace.workflow = "intake"
        events = request_trace.wrap(intake_events())
        response = EventStream(await anext(events), events)
        response.headers["vary"] = "Cookie"
        return response
    # ② Reuse only an independently guarded weather answer after all deterministic workflows have had priority.
    history = [(message.role, message.text) for message in chat_request.history]
    cache_turn = prepare_cache(
        request,
        chat_request.question,
        chat_request.locale,
        chat_request.time_zone,
        lane.id,
        history,
        chat_request.cache_receipt,
        memory,
        now,
        trace=request_trace,
    )
    if cache_turn is not None:
        with request_trace.step("lookup") as cache_step:
            lookup = await cache_turn.service.lookup(
                chat_request.question, cache_turn.scope, cache_turn.context, cache_turn.policy, trace=cache_step
            )
            cache_step.outcome(lookup.status)
            request_trace.cache_outcome(lookup.status)
        if lookup.entry is not None and lookup.entry.expires_at > time.time():
            entry = lookup.entry
            request_trace.workflow = "cached"

            async def cached_events() -> AsyncGenerator[str]:
                """A new answer turn, with cached evidence and no simulated model or tool executions."""
                turn_id = new_turn_id()
                try:
                    yield to_sse_message(
                        render_part(
                            "chat_turn.html",
                            {
                                "turn_id": turn_id,
                                "question": chat_request.question,
                            },
                        )
                    )
                    html = render_answer(entry.answer)
                    context = {
                        "turn_id": turn_id,
                        "answer": html,
                        "chips": (),
                        "weather_cards": cached_cards(entry, time.time()),
                        "memory_note": memory_note,
                        "cache_note": "Cached answer · Gemini was not called. "
                        f"Expires in {max(0, int(entry.expires_at - time.time()))} seconds.",
                        "cache_receipt": cache_turn.receipt_for(str(html)),
                    }
                    yield to_sse_message(render_part("chat_end.html", context))
                    log.info(
                        "chat.done",
                        workflow="cached",
                        answerRef=answer_ref(turn_id),
                        answerChars=len(entry.answer),
                        toolCalls=0,
                        ms=to_ms(time.perf_counter() - started),
                        **request_trace.fields(),
                    )
                except (asyncio.CancelledError, GeneratorExit):
                    log.info(
                        "chat.aborted",
                        workflow="cached",
                        answerChars=0,
                        ms=to_ms(time.perf_counter() - started),
                        **request_trace.fields(),
                    )
                    raise

            cached_stream = request_trace.wrap(cached_events())
            response = EventStream(await anext(cached_stream), cached_stream)
            response.headers["vary"] = "Cookie"
            set_scope(response, request, cache_turn.cookie)
            return response
    # The model, made when the app started; a deployment without its key can still serve a valid cache hit.
    model = request.app.state.chat_model
    if model is None:
        ms = to_ms(time.perf_counter() - started)
        request_trace.failed = True
        log.error("chat.failed", errorClass=ConfigError.__name__, answerChars=0, ms=ms, **request_trace.fields())
        return refusal(ConfigError())
    # ③ The answer: the system prompt and the question, to the agent, with the weather tools; LangSmith traces it
    # only through the app's own tracer, whose client hides its inputs and outputs, when tracing is allowed at all.
    stats = AnswerStats()
    messages = to_messages(
        chat_request.question,
        now,
        chat_request.locale,
        chat_request.time_zone,
        history,
        parks_enabled=knowledge is not None,
        travel_tools=enabled,
        preferences=preferences,
    )
    deadline = asyncio.get_running_loop().time() + to_answer_seconds(lane)
    service: TravelService = request.app.state.travel_service
    today = now.astimezone(zoneinfo.ZoneInfo(chat_request.time_zone)).date()
    currency = preferences.currency or to_currency(chat_request.locale)
    travel = (
        service.new_turn(deadline - TRAVEL_ANSWER_RESERVE_SECONDS, today=today, currency=currency) if enabled else None
    )
    tools = open_lane_tools(request, lane, deadline)
    answer = stream_weather_answer(
        model,
        messages,
        stats,
        request.app.state.tracer,
        tools,
        lane,
        deadline,
        knowledge=knowledge,
        alerts=request.app.state.nps_alerts,
        travel=travel,
        parent=request_trace.run_tree(),
    )
    # ④ The turn's first event, made before the response starts: from then on, however the stream ends, it ends in
    # stream_turn()'s own code, which logs how. A generator closed before it has started runs none of its code.
    turn = stream_turn(
        answer,
        chat_request.question,
        request.state.request_id,
        stats,
        settings.gemini_model,
        memory_note=memory_note,
        cache_turn=cache_turn,
        request_trace=request_trace,
        restrict_links=bool(
            enabled
            and re.search(
                r"\b(?:flights?|airfare|airlines?|airports?|flying|fly|tickets?|hotels?|motels?|lodges?|lodging|resorts?|"
                r"rooms?|stays?|accommodations?|itinerar(?:y|ies)|bookings?)\b",
                chat_request.question,
                re.IGNORECASE,
            )
        ),
    )
    turn = request_trace.wrap(turn)
    first = await anext(turn)
    # ⑤ The answer, streamed.
    response = EventStream(first, turn)
    response.headers["vary"] = "Cookie"
    if cache_turn is not None:
        set_scope(response, request, cache_turn.cookie)
    return response
