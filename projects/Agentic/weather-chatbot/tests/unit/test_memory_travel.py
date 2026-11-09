"""Saved travel defaults never outrank the current trip and use real units and departure-local dates."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tools import StructuredTool
from pydantic import SecretStr

from nimbus.config import Settings
from nimbus.lanes import REST_NO_AUTH
from nimbus.memory.models import PreferenceProfile
from nimbus.parks import Destination, ParkKnowledge
from nimbus.tools import GET_FORECAST, ForecastOutput
from nimbus.travel import briefing, conditions, planner, planner_page
from nimbus.travel.briefing import BriefPreferences
from nimbus.travel.city_intake import city_trip_reply
from nimbus.travel.models import TravelReport
from nimbus.travel.park_forecast import park_forecast
from nimbus.travel.preferences import analyze_with_preferences, prefill_preferences
from nimbus.travel.service import TravelService
from tests.unit.test_memory_client import MemoryRecorder, service
from tests.unit.test_memory_routes import ScopedRecorder, save


@pytest.fixture
def knowledge(settings: Settings) -> ParkKnowledge:
    """Resolve the same supported public destinations as the running app."""
    return ParkKnowledge(settings.parks_index_path)


@pytest.fixture
def saved_memory(client: TestClient) -> MemoryRecorder:
    """Save a real consented browser profile against the offline owned-memory adapter."""
    app = cast(FastAPI, client.app)
    app.state.settings.memory_enabled = True
    app.state.settings.memory_cookie_secret = SecretStr("synthetic-travel-cookie-signing-secret")
    recorder = ScopedRecorder()
    app.state.mem0 = service(recorder)
    save(client, origin="DFW", unit_system="metric", currency="EUR", activity="easy hikes")
    return recorder


def test_saved_airport_is_applied_before_a_weekend_boundary(knowledge: ParkKnowledge) -> None:
    """At Saturday UTC, DFW is still Friday and must receive Friday's departure date."""
    now = datetime(2026, 11, 7, 4, 30, tzinfo=UTC)
    result = analyze_with_preferences(
        "Plan a trip to Zion this weekend", knowledge, "", now, "UTC", PreferenceProfile(origin="DFW")
    )
    assert result is not None
    assert result.kind == "briefing"
    assert result.fields["arrival"] == "2026-11-06"
    assert result.origin_zone == "America/Chicago"
    assert result.fields["origin"] == "DFW"
    assert "origin" in result.memory_used


def test_explicit_origin_and_windows_override_saved_defaults(knowledge: ParkKnowledge) -> None:
    """An explicit request controls this trip without rewriting the stored profile."""
    profile = PreferenceProfile(origin="DFW", depart_window="morning")
    result = analyze_with_preferences(
        "Plan a trip to Zion next weekend from BOS, Friday night",
        knowledge,
        "",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        profile,
    )
    assert result is not None
    assert result.fields["origin"] == "BOS"
    assert result.depart_window == "evening"
    assert "origin" not in result.memory_used
    assert "depart_window" not in result.memory_used
    assert profile.origin == "DFW"


@pytest.mark.parametrize(
    "question",
    [
        "Plan a driving trip to Zion next weekend",
        "Plan a trip to Zion next weekend. No flights or hotels.",
    ],
)
def test_saved_airport_does_not_turn_a_driver_or_opt_out_into_a_flight(knowledge: ParkKnowledge, question: str) -> None:
    """A saved airport is not a standing instruction to search flights."""
    result = analyze_with_preferences(
        question,
        knowledge,
        "",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW", depart_window="morning"),
    )
    assert result is not None
    assert "origin" not in result.fields
    assert result.depart_window == ""
    assert "origin" not in result.memory_used


def test_saved_window_replaces_only_the_automatic_evening_default(knowledge: ParkKnowledge) -> None:
    """User-approved mornings beat the default weekend evening without becoming permission to search."""
    result = analyze_with_preferences(
        "Plan a trip to Zion next weekend",
        knowledge,
        "",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW", depart_window="morning"),
    )
    assert result is not None
    assert result.depart_window == "morning"
    assert "depart_window" in result.memory_used


def test_explicit_any_departure_time_clears_a_saved_window(knowledge: ParkKnowledge) -> None:
    """A deliberately unrestricted departure must not be filled from stored preferences."""
    result = analyze_with_preferences(
        "Plan a trip to Zion next weekend, departing at any time",
        knowledge,
        "",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW", depart_window="morning"),
    )
    assert result is not None
    assert result.depart_window == ""
    assert "depart_window" not in result.memory_used


def test_current_activity_units_and_currency_win_independently(knowledge: ParkKnowledge) -> None:
    """Explicit current values remain independent of both the profile and browser locale."""
    result = analyze_with_preferences(
        "Plan a trip to Zion next weekend for camping; use Celsius; prices in USD",
        knowledge,
        "",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(unit_system="imperial", currency="EUR", activity="easy hikes"),
    )
    assert result is not None
    prefs = BriefPreferences.from_intent(result, "en-US", REST_NO_AUTH, "UTC")
    assert prefs.unit_system == "metric"
    assert prefs.currency == "USD"
    assert prefs.activity == "camping"
    assert prefs.locale == "en-US"
    assert "activity" not in result.memory_used


def test_referential_followup_keeps_explicit_previous_origin(knowledge: ParkKnowledge) -> None:
    """Only the active referent's origin wins over memory; unrelated earlier trips are not reused."""
    result = analyze_with_preferences(
        "Plan my trip there next weekend",
        knowledge,
        "Plan a trip to Zion from BOS",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW"),
    )
    assert result is not None
    assert result.fields["origin"] == "BOS"
    assert "origin" not in result.memory_used


def test_unrelated_previous_origin_does_not_contaminate_a_new_trip(knowledge: ParkKnowledge) -> None:
    """A freshly named trip uses the current request and saved defaults, not an unrelated origin."""
    result = analyze_with_preferences(
        "Plan a trip to Yosemite next weekend",
        knowledge,
        "Plan a trip to Zion from BOS",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW"),
    )
    assert result is not None
    assert result.fields["origin"] == "DFW"


def test_referential_followup_keeps_prior_window_and_units_with_a_new_origin(knowledge: ParkKnowledge) -> None:
    """Changing one trip field leaves other explicit trip choices ahead of saved defaults."""
    result = analyze_with_preferences(
        "Plan my trip there next weekend from BOS",
        knowledge,
        "Plan a trip to Zion from DFW, Friday night; use Celsius",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW", depart_window="morning", unit_system="imperial"),
    )
    assert result is not None
    assert result.fields["origin"] == "BOS"
    assert result.fields["unit_system"] == "metric"
    assert result.depart_window == "evening"
    assert not result.memory_used


def test_referential_followup_keeps_driving_and_hotel_opt_out(knowledge: ParkKnowledge) -> None:
    """A continuation cannot use memory to undo the active trip's mode and search opt-outs."""
    result = analyze_with_preferences(
        "Plan my trip there next weekend",
        knowledge,
        "Plan a driving trip to Zion. No hotels.",
        datetime(2026, 11, 5, tzinfo=UTC),
        "UTC",
        PreferenceProfile(origin="DFW", depart_window="morning"),
    )
    assert result is not None
    assert result.fields["transport"] == "drive"
    assert "origin" not in result.fields
    assert result.skip_hotels
    assert result.depart_window == ""


def test_weather_question_stays_on_weather_path_and_prefill_never_overwrites_values(knowledge: ParkKnowledge) -> None:
    """Memory is defaults, not routing authority or permission to override an edited form."""
    profile = PreferenceProfile(origin="DFW", unit_system="metric", currency="USD")
    assert analyze_with_preferences("Dallas weather", knowledge, "", datetime.now(UTC), "UTC", profile) is None
    fields = prefill_preferences({"origin": "BOS", "unit_system": "", "currency": "EUR"}, profile)
    assert fields["origin"] == "BOS"
    assert fields["unit_system"] == ""
    assert fields["currency"] == "EUR"


def test_dated_quote_form_keeps_preferences_editable_and_submits_the_changed_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    saved_memory: MemoryRecorder,
) -> None:
    """The visible quote controls override saved defaults for this trip without changing the stored profile."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"hotels_enabled": True})
    hotels = AsyncMock(return_value=TravelReport(provider="trivago", status="no_results"))
    app.state.travel_service = TravelService(hotels=hotels)
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 5, 18, tzinfo=UTC))
    calls: list[tuple[str, str]] = []

    async def forecast(_point: Any, _days: int, locale: str, _tools: Any, *, unit_system: str = "") -> ForecastOutput:
        """Record the independent choices at the weather boundary without opening a provider."""
        calls.append((locale, unit_system))
        return ForecastOutput(
            latitude=37.25,
            longitude=-112.96,
            time_zone="America/Denver",
            local_now="2026-11-05T11:00",
            temperature_unit="°C",
            days=[],
            hours=None,
        )

    monkeypatch.setattr(briefing, "park_forecast", forecast)
    monkeypatch.setattr(planner_page, "park_forecast", forecast)
    preparation = AsyncMock(wraps=conditions.preparation)
    monkeypatch.setattr(planner, "preparation", preparation)
    profile = PreferenceProfile.model_validate_json(saved_memory.rows[0]["memory"])
    response = client.post(
        "/api/parks/briefing",
        data={
            "park": "zion",
            "arrival": "2026-11-06",
            "departure": "2026-11-08",
            "prefs": json.dumps({"locale": "en-US", **profile.model_dump()}),
        },
    )
    assert response.status_code == 200
    assert calls == [("en-US", "metric")]
    quote = re.search(r'<form action="/api/parks/trip".*?</form>', response.text, re.S)
    assert quote is not None
    for field in ("activity", "unit_system", "currency"):
        assert quote[0].count(f'name="{field}"') == 1
        assert f'type="hidden" name="{field}"' not in quote[0]
    assert 'name="activity" maxlength="160" value="easy hikes"' in quote[0]
    assert 'value="metric" selected' in quote[0]
    assert 'value="EUR" selected' in quote[0]
    hotels.assert_not_awaited()
    response = client.post(
        "/api/parks/trip",
        data={
            "park": "zion",
            "arrival": "2026-11-06",
            "departure": "2026-11-08",
            "transport": "skip",
            "adults": "1",
            "rooms": "1",
            "locale": "en-US",
            "unit_system": "imperial",
            "currency": "USD",
            "activity": "camping",
        },
    )
    assert response.status_code == 200
    assert calls == [("en-US", "metric"), ("en-US", "imperial")]
    assert hotels.await_args is not None
    assert hotels.await_args.args[0].currency == "USD"
    assert preparation.await_args is not None
    assert preparation.await_args.args[3] == "camping"
    assert PreferenceProfile.model_validate_json(saved_memory.rows[0]["memory"]) == profile


def test_saved_city_airport_sets_calendar_and_does_not_request_providers(
    client: TestClient, saved_memory: MemoryRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual chat city path uses the approved airport before interpreting the weekend near UTC midnight."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    app.state.chat_model = None
    flights, hotels = AsyncMock(), AsyncMock()
    app.state.travel_service = TravelService(flights=flights, hotels=hotels)
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 7, 4, 30, tzinfo=UTC))
    response = client.post(
        "/api/chat",
        data={"question": "Plan a trip to Dallas this weekend", "time_zone": "UTC"},
        headers={"origin": "http://testserver"},
    )
    assert response.status_code == 200
    assert "Your travel dates are 2026-11-06 to 2026-11-08" in response.text
    assert "Using your saved departure airport: DFW" in response.text
    assert "Tell me a different departure city or airport" in response.text
    assert "For flights, include" not in response.text
    flights.assert_not_awaited()
    hotels.assert_not_awaited()


@pytest.mark.parametrize(
    ("question", "prior"),
    [
        ("Plan a trip to Dallas this weekend from BOS", []),
        ("Plan a trip to Dallas this weekend from Boston", []),
        ("This weekend", ["Plan a trip to Dallas from BOS"]),
    ],
)
def test_city_explicit_or_active_trip_origin_beats_saved_airport(question: str, prior: list[str]) -> None:
    """A current or active prior route blocks saved DFW, including origins without a known airport zone."""
    reply = city_trip_reply(
        question,
        ("search_flights", "search_hotels"),
        datetime(2026, 11, 7, 5, 30, tzinfo=UTC),
        "UTC",
        prior,
        preferences=PreferenceProfile(origin="DFW"),
    )
    assert reply is not None
    assert "2026-11-07 to 2026-11-08" in reply
    assert "saved departure airport" not in reply
    assert "For flights, include" not in reply


@pytest.mark.parametrize(
    ("question", "tools"),
    [
        ("Plan a driving trip to Dallas this weekend", ("search_flights", "search_hotels")),
        ("Plan a trip to Dallas this weekend. No flights.", ("search_flights", "search_hotels")),
        ("Plan a trip to Dallas this weekend", ("search_hotels",)),
    ],
)
def test_city_saved_origin_does_not_change_driving_opt_out_or_disabled_flights(
    question: str, tools: tuple[str, ...]
) -> None:
    """An unwanted or unavailable flight service does not activate the saved airport or its calendar."""
    reply = city_trip_reply(
        question,
        tools,
        datetime(2026, 11, 7, 4, 30, tzinfo=UTC),
        "UTC",
        preferences=PreferenceProfile(origin="DFW"),
    )
    assert reply is not None
    assert "2026-11-07 to 2026-11-08" in reply
    assert "saved departure airport" not in reply
    assert "flights" not in reply


def test_an_explicit_any_time_survives_the_weekend_choice(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Choosing a date after an unrestricted departure does not silently restore the evening default."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True})
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 5, 18, tzinfo=UTC))
    response = client.post(
        "/api/parks/briefing",
        data={
            "park": "zion",
            "weekend": "2026-11-06/2026-11-08",
            "prefs": json.dumps({"origin": "DFW", "transport": "fly", "depart_window_explicit": True}),
        },
    )
    assert response.status_code == 200
    assert "Leave DFW in the evening" not in response.text
    assert 'name="depart_window">' in response.text


def test_invalid_measurement_system_is_rejected_before_provider_calls(client: TestClient) -> None:
    """Only the app's supported unit systems cross the validated trip boundary."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"hotels_enabled": True})
    hotels = AsyncMock()
    app.state.travel_service = TravelService(hotels=hotels)
    response = client.post(
        "/api/parks/trip",
        data={
            "park": "zion",
            "arrival": "2026-11-06",
            "departure": "2026-11-08",
            "transport": "skip",
            "adults": "1",
            "rooms": "1",
            "unit_system": "arbitrary",
        },
    )
    assert response.status_code == 400
    hotels.assert_not_awaited()


@pytest.mark.parametrize(("locale", "units"), [("en-US", "metric"), ("en-GB", "imperial")])
def test_explicit_units_reach_the_real_weather_tool_boundary(locale: str, units: str) -> None:
    """Contrary browser defaults cannot overwrite the visitor's submitted weather units."""
    asked: list[dict[str, Any]] = []

    class Tool:
        name = GET_FORECAST.name

        async def ainvoke(self, params: dict[str, Any]) -> str:
            asked.append(params)
            raise RuntimeError("recorded")

    @asynccontextmanager
    async def tools() -> AsyncIterator[list[StructuredTool]]:
        yield [cast(StructuredTool, Tool())]

    zion = cast(Destination, SimpleNamespace(latitude=37.2, longitude=-112.99))
    preferences = PreferenceProfile.model_validate({"unit_system": units})
    with pytest.raises(RuntimeError, match="recorded"):
        asyncio.run(park_forecast(zion, 3, locale, tools(), unit_system=preferences.unit_system))
    assert asked[0]["units"] == units
