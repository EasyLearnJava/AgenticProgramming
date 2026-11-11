"""A small chat bridge for one explicit sandbox command; no changes to the regular travel agent."""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import structlog
from fastapi import Request
from fastapi.responses import Response

from nimbus.booking_demo.routes import bind_browser, seed
from nimbus.feedback import answer_ref
from nimbus.request_trace import RequestTrace
from nimbus.utils import new_turn_id, to_ms, to_sse_message

if TYPE_CHECKING:
    from nimbus.chat import ChatRequest


async def reply(request: Request, chat_request: "ChatRequest", trace: RequestTrace) -> Response:
    """Return a demo card; its isolated browser client drives provider steps and preserves the receipts."""
    # Import only at request time, avoiding a cycle with the existing chat module.
    from nimbus.chat import EventStream, render_part

    state, token = seed(request)
    turn_id = new_turn_id()
    started = time.perf_counter()
    trace.workflow = "intake"
    trace.cache_outcome("bypass", "workflow")

    async def events() -> AsyncGenerator[str]:
        yield to_sse_message(render_part("chat_turn.html", {"turn_id": turn_id, "question": chat_request.question}))
        yield to_sse_message(
            render_part(
                "chat_booking_demo.html",
                {
                    "turn_id": turn_id,
                    "seed": token,
                    "checkin": state.checkin,
                    "checkout": state.checkout,
                },
            )
        )
        structlog.get_logger().info(
            "chat.done",
            workflow="intake",
            bookingDemo=True,
            answerRef=answer_ref(turn_id),
            answerChars=0,
            toolCalls=0,
            ms=to_ms(time.perf_counter() - started),
            **trace.fields(),
        )

    stream = trace.wrap(events())
    response = EventStream(await anext(stream), stream)
    bind_browser(response, request, state.owner)
    return response
