"""Hotel searches with explicitly undecided dates ask for dates before spending provider quota."""

from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.travel.hotel_intake import hotel_dates_reply


def test_explicit_undecided_hotel_dates_do_not_reach_the_model_or_provider(client: TestClient) -> None:
    """Reproduce the production prompt through the normal chat route, with no model to invent dates."""
    app = cast(FastAPI, client.app)
    app.state.settings.hotels_enabled = True
    app.state.chat_model = None
    with capture_logs() as logs:
        reply = client.post(
            "/api/chat",
            data={"question": "Find a hotel in Springdale for two adults, one room. We haven't picked dates."},
        )
    assert reply.status_code == 200
    assert "check-in and check-out dates" in reply.text
    assert "tool-chip-name" not in reply.text
    assert any(row.get("hotelDateIntake") and row.get("toolCalls") == 0 for row in logs)


@pytest.mark.parametrize(
    "question",
    [
        "Find hotels in Dallas. Our dates are TBD.",
        "Could you find a hotel in Santa Fe? We haven\u2019t decided on our travel dates.",
        "I have no dates yet. Show me hotels near the park.",
    ],
)
def test_missing_stay_dates_clarify_before_the_search(question: str) -> None:
    """Common undecided-date phrasings all ask for both ends of the stay."""
    assert hotel_dates_reply(question)


@pytest.mark.parametrize(
    "question",
    [
        "Find a hotel in Dallas November 13 to November 15.",
        "Find hotels in Dallas. We hadn't picked dates, but now use November 13 to November 15.",
        "Find hotels for the same dates.",
        "What is the weather in Springdale? We haven't picked dates.",
        "We haven't picked dates. Don't find hotels.",
        "Find flights and hotels to Dallas. We haven't picked dates.",
        "Find hotels in Dallas; we haven't picked dates. Also check tomorrow's weather.",
        "Find a hotel for this weekend; my friends haven't picked dates.",
    ],
)
def test_concrete_dates_or_other_requests_stay_with_the_existing_chat(question: str) -> None:
    """A date choice, another task or incidental hotel mention must not be replaced with hotel intake."""
    assert hotel_dates_reply(question) is None
