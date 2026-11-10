"""Automatic quotes follow completed conditions and preserve missing details, dates and opt-outs."""

import json
import re
from datetime import UTC, date, datetime
from html import unescape
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.travel import briefing
from nimbus.travel.conditions import Conditions, Decision, Section
from nimbus.travel.models import TravelOffer, TravelReport
from nimbus.travel.service import TravelService
from tests.fakes import FakeModel

NOW = datetime(2026, 11, 10, 23, 26, tzinfo=UTC)
QUESTION = "Plan a trip to Zion this week end from DFW to LAS for two adults, 1 room"


@pytest.fixture
def trip_setup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[FastAPI, AsyncMock, AsyncMock, AsyncMock, list[str]]:
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    monkeypatch.setattr(briefing, "utc_now", lambda: NOW)
    order: list[str] = []
    # Condition decisions themselves are covered with real weather/NPS/NWS recordings in test_weekend_conditions.
    conditions = Conditions(
        Section(message="Recorded weather"), Section(), Section(), Section(), "proceed", "Recorded conditions", NOW
    )

    async def checked(**kwargs: Any) -> Conditions:
        order.append("conditions")
        return conditions

    check = AsyncMock(side_effect=checked)
    monkeypatch.setattr(briefing, "check_conditions", check)

    async def flight(query: Any) -> TravelReport:
        order.append("flights")
        return TravelReport(provider="kiwi", status="found", offers=(TravelOffer(title="Recorded flight"),))

    async def hotel(query: Any) -> TravelReport:
        order.append("hotels")
        return TravelReport(provider="trivago", status="found", offers=(TravelOffer(title="Recorded hotel"),))

    flights, hotels = AsyncMock(side_effect=flight), AsyncMock(side_effect=hotel)
    app.state.travel_service = TravelService(flights=flights, hotels=hotels)

    async def no_repeat(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("The quote stage repeated a completed conditions check")

    for name in ("visit_weather", "preparation", "park_notices"):
        monkeypatch.setattr(f"nimbus.travel.planner.{name}", no_repeat)
    return app, check, flights, hotels, order


def test_complete_weekend_searches_after_conditions_and_renders_both_providers(
    client: TestClient, trip_setup: tuple[Any, ...], chat_model: FakeModel
) -> None:
    _, check, flights, hotels, order = trip_setup
    with capture_logs() as logs:
        response = client.post("/api/chat", data={"question": QUESTION, "time_zone": "America/Chicago"})
    assert response.status_code == 200
    assert "Recorded flight" in response.text
    assert "Recorded hotel" in response.text
    assert "Change travel options" in response.text
    assert "Complete your travel details" not in response.text
    assert order[0] == "conditions"
    assert set(order[1:]) == {"flights", "hotels"}
    check.assert_awaited_once()
    flights.assert_awaited_once()
    hotels.assert_awaited_once()
    air, stay = flights.await_args.args[0], hotels.await_args.args[0]
    assert (air.departure_date, air.return_date) == (date(2026, 11, 13), date(2026, 11, 15))
    assert (stay.check_in, stay.check_out) == (air.departure_date, air.return_date)
    assert (air.origin, air.destination, air.adults, air.depart_window, air.return_window) == (
        "DFW",
        "LAS",
        2,
        "evening",
        "evening",
    )
    assert (stay.adults, stay.rooms) == (2, 1)
    assert not chat_model.seen
    assert not chat_model.guard_seen
    assert any(row["event"] == "travel.plan" for row in logs)
    assert QUESTION not in str(logs)


def test_missing_gateway_asks_only_for_that_field_and_completion_searches(
    client: TestClient, trip_setup: tuple[Any, ...]
) -> None:
    _, check, flights, hotels, _ = trip_setup
    response = client.post("/api/chat", data={"question": "Plan a trip to Zion this weekend from DFW"})
    compact = re.search(r'<form[^>]+class="trip-form brief-action"[^>]*>(.*?)</form>', response.text, re.S)
    assert compact is not None
    assert 'name="gateway"' in compact[1]
    for field in ("origin", "adults", "rooms", "currency", "return_window"):
        assert f'name="{field}"' not in compact[1]
    flights.assert_not_awaited()
    hotels.assert_not_awaited()
    carried = re.search(r'name="prefs" value="([^"]+)"', response.text)
    assert carried is not None
    result = client.post(
        "/api/parks/briefing",
        data={
            "prefs": unescape(carried[1]),
            "park": "zion",
            "arrival": "2026-11-13",
            "departure": "2026-11-15",
            "gateway": "LAS",
        },
        headers={"hx-request": "true"},
    )
    assert result.headers["x-nimbus-briefing"] == "fragment"
    assert "Recorded flight" in result.text
    assert "Recorded hotel" in result.text
    assert "Complete your travel details" not in result.text
    assert check.await_count == 2  # The follow-up rechecks current conditions before searching.
    assert flights.await_args.args[0].origin == "DFW"


@pytest.mark.parametrize("decision", ["pause", "review"])
def test_hazard_or_unverified_conditions_do_not_start_automatic_searches(
    client: TestClient, trip_setup: tuple[Any, ...], decision: Decision
) -> None:
    _, check, flights, hotels, _ = trip_setup
    check.side_effect = None
    check.return_value = Conditions(
        Section(), Section(), Section(), Section(), decision, "Review recorded conditions", NOW
    )
    response = client.post("/api/chat", data={"question": QUESTION})
    assert f'data-brief-decision="{decision}"' in response.text
    flights.assert_not_awaited()
    hotels.assert_not_awaited()


@pytest.mark.parametrize(
    ("question", "flight_count", "hotel_count"),
    [
        ("Plan a driving trip to Zion this weekend", 0, 1),
        (QUESTION + ". Skip hotels.", 1, 0),
        (QUESTION + ". Skip flights.", 0, 1),
        ("Plan a driving trip to Zion this weekend. Skip hotels.", 0, 0),
    ],
)
def test_automatic_quotes_preserve_service_opt_outs(
    client: TestClient, trip_setup: tuple[Any, ...], question: str, flight_count: int, hotel_count: int
) -> None:
    _, _, flights, hotels, _ = trip_setup
    response = client.post("/api/chat", data={"question": question})
    assert response.status_code == 200
    assert flights.await_count == flight_count
    assert hotels.await_count == hotel_count


def test_provider_failure_keeps_conditions_and_other_offers(client: TestClient, trip_setup: tuple[Any, ...]) -> None:
    _, _, flights, hotels, _ = trip_setup
    hotels.side_effect = OSError("PRIVATE_PROVIDER_FAILURE")
    with capture_logs() as logs:
        response = client.post("/api/chat", data={"question": QUESTION})
    assert "Recorded conditions" in response.text
    assert "Recorded flight" in response.text
    assert "PRIVATE_PROVIDER_FAILURE" not in response.text + str(logs)
    assert any(row["event"] == "travel.call" and row.get("status") == "unavailable" for row in logs)
    flights.assert_awaited_once()
    hotels.assert_awaited_once()


def test_invalid_party_is_rejected_before_either_quote(client: TestClient, trip_setup: tuple[Any, ...]) -> None:
    _, _, flights, hotels, _ = trip_setup
    response = client.post(
        "/api/parks/briefing",
        data={
            "park": "zion",
            "arrival": "2026-11-13",
            "departure": "2026-11-15",
            "prefs": json.dumps({"origin": "DFW", "gateway": "LAS", "adults": 1, "rooms": 2}),
        },
    )
    assert "Please check the airports, rooms and traveler counts" in response.text
    flights.assert_not_awaited()
    hotels.assert_not_awaited()
