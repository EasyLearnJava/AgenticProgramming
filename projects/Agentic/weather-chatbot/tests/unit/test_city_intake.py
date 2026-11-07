"""City trip questions collect the visitor's choices before sending a query to a provider."""

import json
from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nimbus.config import Settings
from nimbus.parks import ParkKnowledge
from nimbus.travel.city_intake import city_trip_reply

NOW = datetime(2026, 11, 5, tzinfo=UTC)
TOOLS = ("search_flights", "search_hotels")


def test_dallas_uses_chat_history_and_feedback_without_model_or_provider(client: TestClient) -> None:
    """The reported input renders a real chat answer even with no model available."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    app.state.chat_model = None
    html = client.post("/api/chat", data={"question": "plan a trip to dallas"}).text
    assert "What dates will you be in Dallas?" in html
    assert all(word in html for word in ("forecast", "flights", "hotels", "departure city"))
    assert 'class="answer"' in html
    assert 'action="/api/feedback"' in html
    assert 'class="tool-chip-name"' not in html
    assert "/api/parks/briefing" not in html


@pytest.mark.parametrize(
    ("text", "expected", "absent"),
    [
        ("Plan a trip to Montréal, Canada", "Montréal, Canada", "today's weather"),
        ("I'd like to plan a trip to Dallas", "What dates will you be in Dallas?", "2026-11"),
        ("Let's plan a trip to Dallas this week end", "2026-11-06", "What dates"),
        ("Plan my trip to Dallas from AUS this weekend", "2026-11-06", "departure city"),
        ("Plan a trip to Dallas on 2026-11-14", "When will you leave", "What dates"),
        ("Plan a road trip to San Antonio", "hotels", "flights"),
        ("Plan a driving trip to San Antonio this weekend. Skip hotels.", "2026-11-06", "hotels"),
        ("Plan a driving trip to San Antonio this weekend. Skip hotels.", "forecast for those dates?", "within range"),
        ("Plan a driving trip to Dallas Nov 28 to Nov 30. Skip hotels.", "closer to departure", "for those dates?"),
        ("Plan a trip to Dallas without hotels", "flights", "hotels"),
    ],
)
def test_city_intake_uses_the_given_details(text: str, expected: str, absent: str) -> None:
    """Keep the place and known dates and respect transport and lodging choices."""
    reply = city_trip_reply(text, TOOLS, NOW, "America/Chicago")
    assert reply is not None
    assert expected in reply
    assert absent not in reply


@pytest.mark.parametrize(
    "text",
    [
        "Weather in Dallas tomorrow?",
        "We plan a trip to Dallas. Will it rain?",
        "Please plan a trip to Dallas and find hotels for two adults.",
        "Plan a trip to Dallas this weekend, find hotels for two adults.",
        "Plan a trip to Dallas. Check the weather.",
        "Plan a trip to Zion National Park",
        "Plan a trip there",
        "Don't plan a trip to Dallas",
        "Plan a trip to <script>alert(1)</script>",
    ],
)
def test_specific_tasks_and_unrecognized_destinations_use_existing_routes(text: str) -> None:
    """The generic intake never swallows a specific lookup or renders arbitrary markup."""
    assert city_trip_reply(text, TOOLS, NOW, "America/Chicago") is None


def test_city_intake_only_offers_available_searches() -> None:
    """A weather-only deployment can still collect dates without offering unavailable providers."""
    reply = city_trip_reply("Plan a trip to Dallas", (), NOW, "America/Chicago")
    assert reply is not None
    assert "forecast" in reply
    assert all(word not in reply for word in ("hotel", "flight", "departure city"))


def test_explicit_travel_followup_keeps_destination_in_the_model_messages(client: TestClient) -> None:
    """A specific follow-up proceeds to ordinary chat with the destination from the visitor's previous turn."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"hotels_enabled": True})
    history = json.dumps(
        [{"role": "user", "text": "plan a trip to dallas"}, {"role": "assistant", "text": "What dates will you visit?"}]
    )
    response = client.post(
        "/api/chat", data={"question": "Find hotels for two adults for Nov 13 to Nov 15.", "history": history}
    )
    assert response.status_code == 200
    assert "plan a trip to dallas" in [msg.content for msg in app.state.chat_model.seen[0]]


@pytest.mark.parametrize(
    ("prior", "text", "expected"),
    [
        (["Plan a trip to Dallas"], "November 13 to November 15, 2026.", "2026-11-13 to 2026-11-15"),
        (["Plan a trip to Dallas", "November 13"], "November 15", "2026-11-13 to 2026-11-15"),
        (["Plan a trip to Dallas"], "Nov 13-15, 2026.", "2026-11-13 to 2026-11-15"),
        (["Plan a trip to Dallas"], "This weekend", "2026-11-06 to 2026-11-08"),
        (["Plan a trip to Dallas"], "Forecast for November 13", None),
        (["Plan a trip to Dallas", "Weather in Tokyo?"], "November 15", None),
        (["Find hotels in Dallas"], "November 13 to November 15", None),
    ],
)
def test_only_dates_continue_the_most_recent_city_intake(prior: list[str], text: str, expected: str | None) -> None:
    """Date replies clarify that same trip without swallowing the next service selection or changing destinations."""
    reply = city_trip_reply(text, TOOLS, NOW, "America/Chicago", prior)
    if expected is None:
        assert reply is None
    else:
        assert reply is not None
        assert expected in reply
        assert "Dallas" in reply
        assert "Which would you like" in reply


def test_date_followup_preserves_origin_and_opt_outs() -> None:
    """Dates alone cannot undo an explicit hotel opt-out or discard an origin supplied in an earlier question."""
    reply = city_trip_reply("Nov 12 to Nov 15", TOOLS, NOW, "UTC", ["Plan a trip to Dallas from AUS without hotels"])
    assert reply is not None
    assert "flights" in reply
    assert "hotels" not in reply
    assert "departure city" not in reply


def test_weather_only_choice_can_use_the_requested_dates() -> None:
    """If forecast is the single offered service, supplying dates proceeds to ordinary weather chat."""
    assert city_trip_reply("Nov 12 to Nov 15", (), NOW, "UTC", ["Plan a trip to Dallas"]) is None


def test_trail_alias_does_not_become_a_city_on_a_date_followup(settings: Settings) -> None:
    """A named trail can belong to the park flow without containing the park name."""
    index = ParkKnowledge(settings.parks_index_path)
    assert city_trip_reply("Nov 12 to Nov 15", TOOLS, NOW, "UTC", ["Plan a trip to the Narrows"], index) is None
