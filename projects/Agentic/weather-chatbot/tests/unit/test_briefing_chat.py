"""Conditions-first chat checks with a fixed Thursday in Dallas, recorded public alerts and no travel traffic."""

import json
import re
from datetime import UTC, date, datetime
from html import unescape
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.travel import briefing
from nimbus.travel.models import TravelReport
from nimbus.travel.service import TravelService
from tests.unit.test_nps_alerts import service
from tests.unit.test_weekend_conditions import NOW, feature, nws_service

CASES = json.loads((Path(__file__).resolve().parents[2] / "evals" / "weekend.json").read_text(encoding="utf-8"))


@pytest.fixture
def app(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    instance = cast(FastAPI, client.app)
    monkeypatch.setattr(briefing, "utc_now", lambda: NOW)
    instance.state.nps_alerts = service(lambda _: httpx2.Response(200, json={"total": 0, "data": []}))
    return instance


@pytest.mark.parametrize("case", CASES, ids=[case["question"] for case in CASES])
def test_weekend_prompt_from_chat(
    client: TestClient,
    app: FastAPI,
    case: dict[str, str],
) -> None:
    flights, hotels = AsyncMock(), AsyncMock()
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    app.state.travel_service = TravelService(flights=flights, hotels=hotels)
    response = client.post("/api/chat", data={"question": case["question"], "time_zone": "America/Chicago"})
    assert response.status_code == 200
    html = " ".join(response.text.replace("data: ", "").split())
    if case["expected"] == "chat":
        assert 'class="bubble trip-card"' not in html
    else:
        assert case["expected"] in html
        assert 'class="bubble trip-card"' in html
    flights.assert_not_awaited()
    hotels.assert_not_awaited()


def test_driver_can_skip_hotels_without_any_quote_form(client: TestClient, app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    html = client.post("/api/chat", data={"question": "Plan a driving trip to Zion this weekend. Skip hotels."}).text
    assert "Trip conditions · Zion" in html
    assert 'action="/api/parks/trip"' not in html
    assert "Leave home in the evening" not in html
    assert "Arrive back home" not in html


def test_late_friday_departure_uses_the_origin_date(
    client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 7, 7, 30, tzinfo=UTC))
    html = client.post("/api/chat", data={"question": "Plan a trip to Zion this weekend from LAX"}).text
    assert "Weather for your dates" in html
    assert "Fri, Nov 06, 2026" in html
    assert "Sat, Nov 07" in html
    assert "Choose a future stay" not in html
    assert "/static/planner.css" in client.get("/").text
    changed = client.post(
        "/api/parks/briefing",
        data={"park": "zion", "arrival": "2026-11-06", "departure": "2026-11-08", "origin": "lax"},
    )
    assert "Weather for your dates" in changed.text


@pytest.mark.parametrize(("origin", "zone"), [("LAX", "UTC"), ("Los Angeles", "America/Los_Angeles")])
def test_confirmed_quotes_use_the_outbound_and_park_local_dates(
    client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch, origin: str, zone: str
) -> None:
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 7, 7, 30, tzinfo=UTC))
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    flights = AsyncMock(return_value=TravelReport(provider="kiwi", status="no_results"))
    hotels = AsyncMock(return_value=TravelReport(provider="trivago", status="no_results"))
    app.state.travel_service = TravelService(flights=flights, hotels=hotels)
    response = client.post(
        "/api/parks/trip",
        data={
            "park": "zion",
            "arrival": "2026-11-06",
            "departure": "2026-11-08",
            "origin": origin,
            "time_zone": zone,
            "gateway": "LAS",
            "transport": "fly",
            "adults": "1",
            "rooms": "1",
            "return_window": "by_15:00",
        },
    )
    assert response.status_code == 200
    assert flights.await_args is not None
    assert hotels.await_args is not None
    outbound = flights.await_args.args[0]
    stay = hotels.await_args.args[0]
    assert (outbound.departure_date, outbound.return_window) == (date(2026, 11, 6), "by_15:00")
    assert (stay.check_in, stay.check_out) == (date(2026, 11, 7), date(2026, 11, 8))


def test_choosing_a_weekend_preserves_a_return_day_without_a_deadline(client: TestClient, app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True})
    response = client.post(
        "/api/parks/briefing",
        data={
            "park": "zion",
            "weekend": "2026-11-07/2026-11-09",
            "prefs": json.dumps({"origin": "DFW", "transport": "fly", "depart_window": "evening"}),
        },
    )
    assert "Mon, Nov 09, 2026" in response.text
    carried = re.search(r'name="prefs" value="([^"]+)"', response.text)
    assert carried is not None
    assert json.loads(unescape(carried[1])).get("return_window", "") == ""
    assert "in the evening on Monday" not in response.text


def test_performance_includes_checked_briefings_and_excludes_intake(client: TestClient, app: FastAPI) -> None:
    with capture_logs() as lines:
        client.post("/api/chat", data={"question": "Plan a trip to Zion"})
        response = client.post("/api/chat", data={"question": "Plan a trip to Zion this weekend"})
    assert "Weather for your dates" in response.text
    assert [line["tripForm"] for line in lines if line["event"] == "chat.done"] == [True, False]


def test_failed_briefing_finishes_stream_with_ref_and_logs_no_private_details(
    client: TestClient,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(briefing, "briefing_context", AsyncMock(side_effect=RuntimeError("secret upstream failure")))
    with capture_logs() as lines:
        response = client.post("/api/chat", data={"question": "Plan a trip to Zion this weekend"})
    assert "message-error" in response.text
    assert "(ref " in response.text
    assert "secret upstream failure" not in response.text
    assert "secret upstream failure" not in str(lines)
    assert [line["errorClass"] for line in lines if line["event"] == "chat.failed"] == ["RuntimeError"]
    assert all(line["event"] != "chat.done" for line in lines)


def test_dates_entered_in_undated_planner_cannot_bypass_weather_warning(client: TestClient, app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    app.state.nws_alerts = nws_service(
        lambda _: httpx2.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [feature()],
            },
        )
    )
    flights, hotels = AsyncMock(), AsyncMock()
    app.state.travel_service = TravelService(flights=flights, hotels=hotels)
    initial = client.post("/api/chat", data={"question": "Plan a trip to Zion"}).text
    assert 'action="/api/parks/trip"' not in initial
    assert 'class="trip-form brief-action"' in initial
    response = client.post(
        "/api/parks/briefing",
        data={
            "park": "zion",
            "arrival": "2026-11-06",
            "departure": "2026-11-08",
            "origin": "DFW",
            "gateway": "LAS",
            "transport": "fly",
            "adults": "2",
            "rooms": "1",
            "children_ages": "8",
        },
    )
    assert response.headers["x-nimbus-briefing"] == "fragment"
    assert response.headers["cache-control"] == "no-store"
    assert 'data-brief-decision="pause"' in response.text
    assert "Flash Flood Warning" in response.text
    assert "Change dates" in response.text
    assert 'action="/api/parks/trip"' not in response.text
    flights.assert_not_awaited()
    hotels.assert_not_awaited()


def test_saturday_choice_with_two_parks_works_without_travel(
    client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 7, 18, tzinfo=UTC))
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": False, "hotels_enabled": False})
    initial = client.post("/api/chat", data={"question": "Plan a trip to Zion or Yosemite this weekend from DFW."}).text
    assert 'name="weekend" required' in initial
    assert "2026-11-07/2026-11-08" in initial
    response = client.post("/api/parks/briefing", data={"park": "yosemite", "weekend": "2026-11-07/2026-11-08"})
    assert "Trip conditions · Yosemite" in response.text
    assert "National Weather Service" in response.text
    assert 'action="/api/parks/trip"' not in response.text


@pytest.mark.parametrize(
    "extras",
    [
        {"unexpected": "a"},
        {"prefs": '{"time_zone":"not-a-zone"}'},
        {"prefs": '{"origin":{"unexpected":"x"}}'},
        {"weekend": "2026-11-06/2026-11-08", "arrival": "2026-12-23"},
    ],
)
def test_followup_rejects_conflicting_or_untrusted_fields(client: TestClient, extras: dict[str, Any]) -> None:
    data = {"park": "zion", "arrival": "2026-11-06", "departure": "2026-11-08", **extras}
    assert client.post("/api/parks/briefing", data=data).status_code == 400
