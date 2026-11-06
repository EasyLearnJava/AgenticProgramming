"""HTTP acceptance cases for a real park index, synthetic upstreams, and all five planner sections."""

from datetime import date, datetime, timedelta
from typing import Any, cast
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx2
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.lanes import Lane
from nimbus.park_tools import KnowledgeService
from nimbus.parks import Destination, ParkKnowledge
from nimbus.tools import Day, ForecastOutput
from nimbus.travel import planner_page
from nimbus.travel.models import FlightSearch, HotelSearch, TravelOffer, TravelReport
from nimbus.travel.planner import GENERAL_GUIDANCE
from nimbus.travel.planner_intake import planner_intake
from nimbus.travel.service import TravelService
from tests.unit.test_nps_alerts import notice, service

PATH = "/api/parks/trip"


@pytest.fixture
def knowledge(settings: Settings) -> ParkKnowledge:
    """Use the same indexed aliases and destination scope as the public chat route."""
    return ParkKnowledge(settings.parks_index_path)


@pytest.mark.parametrize(
    ("question", "park"),
    [
        ("Plan a trip to Zion National Park", "zion"),
        ("Can you plan a visit to Yosemite?", "yosemite"),
        ("Give me a national park itinerary for Grand Canyon or Zion", ""),
        ("Plan my trip to the Grand Canyon of the Yellowstone", ""),
        ("Plan a trip to Yellowstone National Park", ""),
        ("Plan a trip to Yellowstone National Park, after my trip to Zion", ""),
        ("Plan a trip to Zion, Illinois", ""),
        ("Plan a road trip to Zion", "zion"),
        ("Plan a trip to Zion, driving", "zion"),
        ("Please plan my Grand Canyon South Rim trip", "grand-canyon"),
        ("What is the weather in Zion National Park today?", None),
        ("Plan a trip to Lisbon", None),
        ("Don't plan a trip to Zion, just show current notices", None),
    ],
)
def test_chat_opens_trip_intake_only_for_intended_park_requests(
    question: str, park: str | None, knowledge: ParkKnowledge
) -> None:
    fields = planner_intake(question, knowledge)
    assert (fields.get("park", "") if fields is not None else None) == park


def test_intake_keeps_explicit_airports_dates_and_traveler_counts(knowledge: ParkKnowledge) -> None:
    request = "Plan a trip to Zion from SEA to LAS 2027-04-03 to 2027-04-06 for two adults, 1 room"
    assert planner_intake(request, knowledge) == {
        "park": "zion",
        "origin": "SEA",
        "gateway": "LAS",
        "transport": "fly",
        "arrival": "2027-04-03",
        "departure": "2027-04-06",
        "adults": "2",
        "rooms": "1",
    }


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Plan my trip there", {"park": "zion"}),
        ("Plan a trip to Yosemite", {"park": "yosemite"}),
        ("Plan a trip to Stockholm", None),
        ("I'm planning a trip to Zion. What is tomorrow's weather?", None),
    ],
)
def test_followup_uses_park_only_for_referential_request(
    question: str, expected: dict[str, str] | None, knowledge: ParkKnowledge
) -> None:
    assert planner_intake(question, knowledge, "What should I wear in Zion?") == expected


@pytest.mark.parametrize(
    "place",
    [
        "Grand Canyon North Rim",
        "the North Rim of the Grand Canyon",
        "Yellowstone National Park, after my trip to Zion",
        "Zion or Yosemite",
    ],
)
def test_unresolved_chat_destination_requires_an_explicit_park_selection(client: TestClient, place: str) -> None:
    _enable(client)
    html = client.post("/api/chat", data={"question": f"Plan my visit to {place}."}).text
    assert 'action="/api/parks/trip"' in html
    for park in ("grand-canyon", "yosemite", "zion"):
        assert f'value="{park}" selected' not in html


@pytest.mark.parametrize(
    "question",
    [
        "I do not want an itinerary for Zion. Show me its weather.",
        "Don\N{RIGHT SINGLE QUOTATION MARK}t plan a trip to Zion; just give me the weather.",
    ],
)
def test_declining_a_plan_keeps_the_normal_chat_route(client: TestClient, question: str) -> None:
    _enable(client)
    response = client.post("/api/chat", data={"question": question})
    assert response.status_code == 200
    assert 'action="/api/parks/trip"' not in response.text
    assert 'class="answer"' in response.text


@pytest.mark.parametrize(
    ("mode", "drive"),
    [
        ("I am not driving", False),
        ("We\N{RIGHT SINGLE QUOTATION MARK}re not driving", False),
        ("I am driving", True),
        ("I am driving from ORD to LAS", False),
    ],
)
def test_chat_prefills_only_an_uncontradicted_transport_choice(client: TestClient, mode: str, drive: bool) -> None:
    _enable(client)
    html = client.post("/api/chat", data={"question": f"Plan a trip to Zion. {mode}."}).text
    assert 'value="zion" selected' in html
    assert ('value="drive" selected' in html) is drive
    assert 'value="fly" selected' not in html


def _enable(client: TestClient) -> FastAPI:
    """Enable travel on the isolated app for this test."""
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True})
    return app


def _fields(days_out: int = 2) -> dict[str, str]:
    """A synthetic family trip starting in park local time; immune to the date the suite runs."""
    arrival = datetime.now(ZoneInfo("America/Denver")).date() + timedelta(days=days_out)
    return {
        "park": "zion",
        "transport": "fly",
        "adults": "2",
        "rooms": "1",
        "origin": "SEA",
        "gateway": "LAS",
        "arrival": arrival.isoformat(),
        "departure": (arrival + timedelta(days=2)).isoformat(),
        "children_ages": "1, 8, 15",
        "currency": "USD",
        "activity": "weather and hiking safety",
    }


@pytest.mark.parametrize(
    ("change", "components"),
    [
        ({}, {"kiwi", "trivago", "nps", "weather", "guidance"}),
        ({"transport": "drive"}, {"trivago", "nps", "weather", "guidance"}),
        ({"far": "yes"}, {"kiwi", "trivago", "nps", "guidance"}),
        ({"outage": "hotel"}, {"kiwi", "trivago", "nps", "weather", "guidance"}),
        ({"boundary": "yes"}, {"kiwi", "trivago", "nps", "weather", "guidance"}),
        ({"hotels_only": "yes"}, {"trivago", "nps", "weather", "guidance"}),
        ({"flights_only": "no_room_field"}, {"kiwi", "nps", "weather", "guidance"}),
        ({"flights_only": "stale_form"}, {"kiwi", "nps", "weather", "guidance"}),
        ({"activity": "hiking"}, {"kiwi", "trivago", "nps", "weather", "guidance", "general_guidance"}),
        ({"empty_index": "yes"}, {"kiwi", "trivago", "nps", "weather", "guidance", "general_guidance"}),
        ({"index_down": "yes"}, {"kiwi", "trivago", "nps", "weather", "guidance"}),
    ],
)
def test_park_trip_acceptance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, change: dict[str, str], components: set[str]
) -> None:
    """Check actually executed providers and visible results, including independently failing and skipped sections."""
    app = _enable(client)
    calls: list[str] = []
    fields = _fields(50 if "far" in change else 15 if "boundary" in change else 2)
    fields.update({k: v for k, v in change.items() if k in {"transport", "activity"}})
    if "hotels_only" in change:
        app.state.settings = app.state.settings.model_copy(update={"flights_enabled": False})
        for key in ("origin", "gateway", "transport"):
            fields.pop(key)
        assert 'name="origin"' not in client.get("/parks/trip").text

    if "flights_only" in change:
        app.state.settings = app.state.settings.model_copy(update={"hotels_enabled": False})
        fields.pop("rooms")
        if change["flights_only"] == "stale_form":
            fields["rooms"] = "obsolete"
        assert 'name="rooms"' not in client.get("/parks/trip").text
        intake = client.post("/api/chat", data={"question": "Plan a trip to Zion National Park"})
        assert "Build my trip plan" in intake.text
        assert 'name="rooms"' not in intake.text

    async def flight(q: FlightSearch) -> TravelReport:
        calls.append("kiwi")
        assert (q.origin, q.destination, q.adults, q.infants, q.children) == ("SEA", "LAS", 3, 1, 1)
        return TravelReport(provider="kiwi", status="found", offers=(TravelOffer(title="Synthetic test flight"),))

    async def hotel(q: HotelSearch) -> TravelReport:
        calls.append("trivago")
        assert (q.latitude, q.adults, q.children_ages) == (37.25082, 2, (1, 8, 15))
        if "outage" in change:
            raise OSError("synthetic private provider error")
        return TravelReport(provider="trivago", status="found", offers=(TravelOffer(title="Synthetic test hotel"),))

    def nps(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["parkCode"] == "zion"
        calls.append("nps")
        return httpx2.Response(200, json={"total": "1", "start": "0", "data": [notice()]})

    async def weather(
        request: Request, destination: Destination, days: int, lane: Lane, deadline: float
    ) -> ForecastOutput:
        calls.append("weather")
        assert (destination.id, days, lane.id) == ("zion", 16 if "boundary" in change else 5, "rest-no-auth")
        day = Day(
            date=fields["arrival"],
            weekday="Thursday",
            condition="Clear record",
            temperature_min=42,
            temperature_max=62,
            rain_chance_percent=2,
            sunrise=None,
            sunset=None,
        )
        first_day = date.fromisoformat(fields["arrival"])
        all_days = [
            day.model_copy(update={"date": (first_day + timedelta(days=i)).isoformat()})
            for i in range(-1, 1 if "boundary" in change else 3)
        ]
        all_days[0] = all_days[0].model_copy(update={"condition": "BEFORE-STAY"})
        return ForecastOutput(
            latitude=destination.latitude,
            longitude=destination.longitude,
            time_zone=destination.time_zone,
            local_now=fields["arrival"],
            temperature_unit="°F",
            days=all_days,
            hours=None,
        )

    real_search = cast(KnowledgeService, app.state.park_knowledge).search

    async def record_search(park: str, query: str, visit_date: date | None = None) -> dict[str, Any]:
        calls.append("general_guidance" if query == GENERAL_GUIDANCE else "guidance")
        assert (park, visit_date) == ("zion", date.fromisoformat(fields["arrival"]))
        assert query in {fields["activity"], GENERAL_GUIDANCE}
        if "empty_index" in change:
            return {"status": "not_found", "passages": []}
        if "index_down" in change:
            return {"status": "unavailable"}
        return await real_search(park, query, visit_date)

    app.state.travel_service = TravelService(
        flights=None if "hotels_only" in change else flight,
        hotels=None if "flights_only" in change else hotel,
    )
    app.state.nps_alerts = service(nps)
    monkeypatch.setattr(planner_page, "_forecast", weather)
    monkeypatch.setattr(app.state.park_knowledge, "search", record_search)
    with capture_logs() as events:
        response = client.post(PATH, data=fields)
    [aggregate] = [event for event in events if event["event"] == "travel.plan"]
    assert aggregate["missingSections"] == int(
        bool({"far", "outage", "boundary", "index_down", "empty_index"} & change.keys())
    )
    assert aggregate["failedSections"] == int(bool({"outage", "index_down"} & change.keys()))
    assert aggregate["status"] == ("partial" if aggregate["missingSections"] else "ok")
    assert response.status_code == 200
    html = response.text
    assert "2 nights" in html
    assert "Test notice" in html
    assert "Current official notices" in html
    assert 'class="knowledge-panel"><h2>Park preparation guidance</h2>' in html
    cited = not bool({"index_down", "empty_index"} & change.keys())
    assert ("/planyourvisit/" in html) == cited
    assert ("National Park Service</a>" in html) == cited
    assert ("Showing general park preparation" in html) == (change.get("activity") == "hiking")
    assert ("No preparation passages matched" in html) == ("empty_index" in change)
    assert sorted(calls) == sorted(components)
    assert ("Synthetic test flight" in html) == ("kiwi" in components)
    assert ("Synthetic test hotel" in html) == ("trivago" in components and "outage" not in change)
    if "flights_only" in change:
        assert 'name="rooms"' not in html
        assert "Hotel search is disabled for this plan." in html
        assert all(line.get("tool") != "search_hotels" for line in events)
    assert "synthetic private provider error" not in html
    assert "BEFORE-STAY" not in html
    assert ("Flight search is disabled for this plan." in html) == ("hotels_only" in change)
    assert ("16-day forecast window" in html) == ("far" in change)
    if "boundary" in change:
        assert "Forecast covers part of your stay" in html
        assert "Clear record" in html
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("foreign", 403),
        ("duplicate", 400),
        ("large", 413),
        ("json", 415),
        ("past", 400),
        ("reversed", 400),
        ("unknown", 400),
        ("party", 400),
        ("airports", 400),
        ("lane", 400),
        ("too_many_seated", 400),
        ("bad_skip", 400),
        ("timestamp", 400),
    ],
)
def test_invalid_plans_stop_before_provider_access(client: TestClient, kind: str, status: int) -> None:
    app = _enable(client)
    app.state.travel_service = None  # Would crash if upstream setup happened.
    fields = _fields()
    fields.update(
        {
            "past": {"arrival": "2000-01-01"},
            "reversed": {"departure": fields["arrival"]},
            "unknown": {"park": "other"},
            "party": {"adults": "1", "rooms": "2"},
            "airports": {"gateway": "SEA"},
            "lane": {"lane": "mcp-with-auth"},
            "too_many_seated": {"adults": "8"},
            "bad_skip": {"transport": "skip"},
            "timestamp": {"arrival": "1924992000", "departure": "1925164800"},
        }.get(kind, {})
    )
    headers = {"content-type": "application/x-www-form-urlencoded"}
    if kind == "foreign":
        headers["origin"] = "https://external.example"
    if kind == "json":
        headers["content-type"] = "application/json"
    body = urlencode(fields) + ("&park=zion" if kind == "duplicate" else "")
    response = client.post(PATH, content="x" * 5000 if kind == "large" else body, headers=headers)
    assert response.status_code == status
    assert 'role="alert"' in response.text
    assert "application/json" not in response.headers["content-type"]


def test_planner_get_disabled_queries_and_throttling(client: TestClient) -> None:
    """No GET spends quota; a gate rejection stays on the form and carries Retry-After."""
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager

    from fastapi import HTTPException

    assert client.get("/parks/trip").status_code == 404
    app = _enable(client)
    app.state.travel_service = None
    assert client.get("/parks/trip?park=zion").status_code == 200
    assert client.get("/parks/trip?park=zion&park=yosemite").status_code == 400
    assert client.get("/parks/trip?question=anything").status_code == 400

    class Gate:
        @asynccontextmanager
        async def reserve(self, caller: str) -> AsyncIterator[None]:
            raise HTTPException(429, headers={"retry-after": "60"})
            yield

    app.state.planner_gate = Gate()
    limited = client.post(PATH, data=_fields())
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert "Trip planning is busy" in limited.text
