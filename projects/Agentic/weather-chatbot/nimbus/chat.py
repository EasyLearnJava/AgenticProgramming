"""
nimbus/chat.py: POST /api/chat: the chat's one route. The page's form posts a question, with the browser's locale and
time zone; the answer comes back as server-sent events, each holding HTML that htmx puts into the page: the question
and Nimbus's answer, empty and busy; each piece of the answer as the model writes it; then the finished answer, its
Markdown made HTML. A request that breaks a rule gets our own sentence, as HTML, before any work is done. The answer is
Gemini's (nimbus/model.py, nimbus/answer.py), told its rules by nimbus/prompts.py.
"""

import asyncio
import time
import zoneinfo
from collections.abc import AsyncGenerator, Mapping
from contextlib import aclosing, suppress
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Annotated
from urllib.parse import parse_qsl

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, field_validator
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from nimbus.answer import AnswerStats, render_answer, stream_answer
from nimbus.config import Settings
from nimbus.constants import (
    CHAT_BODY_MAX_BYTES,
    CHAT_FORM_MAX_FIELDS,
    DEFAULT_LOCALE,
    DEFAULT_TIME_ZONE,
    ERROR_HEADER,
    EVENT_STREAM,
    FORM_MEDIA_TYPE,
    LOCALE_MAX_CHARS,
    LOCALE_PATTERN,
    NO_STORE,
    QUESTION_MAX_CHARS,
)
from nimbus.errors import (
    BODY_TOO_LARGE,
    EMPTY_QUESTION,
    QUESTION_TOO_LONG,
    UNREADABLE,
    ConfigError,
    InputError,
    NimbusError,
    to_user_message,
)
from nimbus.pages import templates
from nimbus.prompts import to_messages
from nimbus.utils import new_turn_id, to_ms, to_ref, to_sse_message

router = APIRouter()
# The status a request gets when the browser went before it was answered, as nginx logs it: no one reads it.
HTTP_CLIENT_CLOSED_REQUEST = 499
# Every time zone the IANA database names (tzdata's), read once: a time zone the page sends must be one of them.
TIME_ZONES = frozenset(zoneinfo.available_timezones())


class ChatRequest(BaseModel):
    """
    What the chat's form sends, checked: the question, trimmed, 1 to 2,000 characters, and no field we don't know; and
    the browser's locale and time zone. Those two come from the browser, not the visitor, and some browsers send ones
    we can't use (ICU's "Etc/Unknown"): they take the default rather than lock the visitor out (issue 40).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_CHARS)]
    locale: str = DEFAULT_LOCALE
    time_zone: str = DEFAULT_TIME_ZONE

    @field_validator("locale", mode="before")
    @classmethod
    def usable_locale(cls, value: object) -> object:
        """A language tag of at most 35 characters, letters, digits and hyphens; else the default."""
        usable = isinstance(value, str) and len(value) <= LOCALE_MAX_CHARS and LOCALE_PATTERN.fullmatch(value)
        return value if usable else DEFAULT_LOCALE

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
    problems = {(str(problem["loc"][0]) if problem["loc"] else "", problem["type"]) for problem in error.errors()}
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
    # ② Its body, at most 32 KiB, and its fields: UTF-8, each one once.
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


async def stream_turn(
    answer: AsyncGenerator[str], question: str, request_id: str, stats: AnswerStats, model_name: str
) -> AsyncGenerator[str]:
    """A turn of the chat, as server-sent events: the two messages, each piece of the answer, then the answer's end."""
    log = structlog.get_logger()
    turn_id = new_turn_id()
    started = time.perf_counter()
    pieces: list[str] = []

    def ending() -> dict[str, object]:
        """What every line about the answer's end holds: its length, its time, its tokens, and the model."""
        return {
            "answerChars": len("".join(pieces)),
            "ms": to_ms(time.perf_counter() - started),
            "tokensIn": stats.tokens_in,
            "tokensOut": stats.tokens_out,
            "model": model_name,
        }

    try:
        # ① The question, and Nimbus's answer, still empty and marked busy, added to the conversation.
        yield to_sse_message(render_part("chat_turn.html", {"question": question, "turn_id": turn_id}))
        # ② Each piece of the answer, added to it as the model writes it; the model's stream is closed however the
        # turn ends.
        async with aclosing(answer) as words:
            async for piece in words:
                pieces.append(piece)
                yield to_sse_message(render_part("chat_piece.html", {"turn_id": turn_id, "text": piece}))
        # ③ The finished answer, its Markdown made HTML, no longer busy, in place of the one being written.
        html = render_answer("".join(pieces))
        yield to_sse_message(render_part("chat_end.html", {"turn_id": turn_id, "answer": html}))
        log.info("chat.done", **ending())
    except (asyncio.CancelledError, GeneratorExit):
        # ④ Stop, or the page went away: nothing more can be sent.
        log.info("chat.aborted", **ending())
        raise
    except Exception as error:
        # ⑤ A failure: the answer so far, then our own sentence and the ref that finds the request's lines, never the
        # error's own text, which stays out of the logs too; the model's own error is logged by its class.
        cause = error.__cause__
        causes = {"causeClass": type(cause).__name__} if cause is not None else {}
        log.error("chat.failed", errorClass=type(error).__name__, **causes, **ending())
        note = f"{to_user_message(error)} (ref {to_ref(request_id)})"
        context = {"turn_id": turn_id, "answer": render_answer("".join(pieces)), "failed": True, "note": note}
        yield to_sse_message(render_part("chat_end.html", context))


def refusal(error: NimbusError) -> HTMLResponse:
    """Our own sentence for a request we can't answer, as Nimbus's message, marked as ours, with the error's status."""
    return HTMLResponse(
        render_part("chat_rejected.html", {"message": error.user_message}),
        status_code=error.status_code,
        headers={ERROR_HEADER: "1"},
    )


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
    # The question's length, never its text; and which of the browser's values took the default, if any did.
    extra = {"defaulted": defaulted} if defaulted else {}
    log.info("chat.request", questionChars=len(chat_request.question), **extra)
    # ② The model, made when the app started; a deployment without its key can't answer at all.
    model = request.app.state.chat_model
    if model is None:
        ms = to_ms(time.perf_counter() - started)
        log.error("chat.failed", errorClass=ConfigError.__name__, answerChars=0, ms=ms)
        return refusal(ConfigError())
    # ③ The answer: the system prompt and the question, to the model; LangSmith traces it only through the app's own
    # tracer, whose client hides its inputs and outputs, when tracing is allowed at all.
    stats = AnswerStats()
    messages = to_messages(chat_request.question, datetime.now(UTC), chat_request.locale, chat_request.time_zone)
    answer = stream_answer(model, messages, stats, request.app.state.tracer)
    # ④ The turn's first event, made before the response starts: from then on, however the stream ends, it ends in
    # stream_turn()'s own code, which logs how. A generator closed before it has started runs none of its code.
    turn = stream_turn(answer, chat_request.question, request.state.request_id, stats, settings.gemini_model)
    first = await anext(turn)
    # ⑤ The answer, streamed.
    return EventStream(first, turn)
