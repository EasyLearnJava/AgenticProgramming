"""Voluntary, category-only answer feedback. Reviewers correlate reports using a public-safe digest."""

import hashlib
import re
from typing import Final

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from nimbus.constants import NO_STORE
from nimbus.forms import read_form_fields

router = APIRouter()
CATEGORIES: Final = {
    "helpful": "Helpful answer",
    "trip-dates": "Wrong trip dates or times",
    "destination": "Wrong destination or intent",
    "travel": "Flight or hotel results",
    "weather": "Weather or park guidance",
    "safety": "Safety or official notices",
    "sources": "Missing or incorrect sources",
}
TURN_ID = re.compile(r"[0-9a-f]{16}")


def answer_ref(turn_id: str) -> str:
    """Correlate the answer and report without publishing the identifier accepted by the feedback form."""
    return hashlib.sha256(bytes.fromhex(turn_id)).hexdigest()[:16]


@router.post("/api/feedback", response_class=PlainTextResponse)
async def report_feedback(request: Request) -> PlainTextResponse:
    """An untrusted visitor signal may identify a case to investigate. Only a reviewer can add a regression."""
    headers = {"cache-control": NO_STORE}
    try:
        fields = await read_form_fields(request, max_bytes=128, max_fields=2)
        turn, category = fields.get("turn", ""), fields.get("category", "")
        if set(fields) != {"turn", "category"} or not TURN_ID.fullmatch(turn) or category not in CATEGORIES:
            raise HTTPException(400)
        gate = request.app.state.feedback_gate
        async with gate.reserve(request.client.host if request.client else "unknown"):
            structlog.get_logger().info("answer.feedback", category=category, answerRef=answer_ref(turn))
    except HTTPException as error:
        headers.update(error.headers or {})
        message = "Please wait a minute and try again." if error.status_code == 429 else "Feedback could not be sent."
        return PlainTextResponse(message, status_code=error.status_code, headers=headers)
    return PlainTextResponse("Feedback received.", headers=headers)
