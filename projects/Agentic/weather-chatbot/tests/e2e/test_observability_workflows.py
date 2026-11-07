"""Compare real endpoint events with the Activity timeline rendered in a browser."""

import json
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import cast

import httpx2
import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect
from pydantic import SecretStr
from structlog.testing import capture_logs
from structlog.typing import Processor

from nimbus.axiom_query import Row
from nimbus.nps_alerts import NpsAlertsService
from nimbus.nws_alerts import NwsAlertsService
from nimbus.travel.models import HotelSearch, TravelReport
from nimbus.travel.service import TravelService
from tests.fakes import AxiomRecordings, open_meteo_answer

pytestmark = pytest.mark.parametrize("base_url", ["observability"], indirect=True)


def workflow_recordings(app: FastAPI, rows: list[Row]) -> AxiomRecordings:
    """Run real routes with synthetic upstreams, then expose only their logged events to Activity."""
    arrival = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    departure = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
    forecast = open_meteo_answer("forecast-dallas-imperial")
    forecast["daily"]["time"] = [arrival, departure]
    for field, clock in (("sunrise", "08:00"), ("sunset", "18:00")):
        forecast["daily"][field] = [f"{day}T{clock}" for day in (arrival, departure)]
    app.state.make_http_client = lambda: httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=forecast))
    )

    def notices(request: httpx2.Request) -> httpx2.Response:
        """A current park-wide closure is useful information, while a later page can fail."""
        if request.url.params["start"] != "0":
            return httpx2.Response(503)
        record = {
            "id": "synthetic",
            "parkCode": "zion",
            "category": "Park Closure",
            "title": "Synthetic closure",
            "description": f"Zion National Park is closed from {arrival} through {departure}.",
            "url": "https://www.nps.gov/zion/index.htm",
        }
        return httpx2.Response(200, json={"total": "1", "data": [record]})

    async def unavailable_hotel(_query: HotelSearch) -> TravelReport:
        """Exercise the service's actual timeout classification without waiting on a provider."""
        raise TimeoutError

    app.state.nps_alerts = NpsAlertsService(
        SecretStr("synthetic-nps-key"), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(notices))
    )
    app.state.travel_service = TravelService(hotels=unavailable_hotel)
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="_time"),
    ]
    question = f"Plan a trip to Zion from DFW from {arrival} to {departure}"
    with capture_logs(processors=processors) as emitted, closing(TestClient(app)) as client:
        for ref, text in (
            ("11111111", "Plan a trip to Dallas"),
            ("22222222", "Plan a trip to Zion"),
            ("33333333", question),
            ("44444444", question),
        ):
            response = client.post(
                "/api/chat",
                data={"question": text, "locale": "en-US", "time_zone": "America/Chicago"},
                headers={"x-vercel-id": f"workflow-{ref}"},
            )
            assert response.status_code == 200

        def partial_notices(request: httpx2.Request) -> httpx2.Response:
            """Preserve page one's valid notice while recording the next page's failure."""
            response = notices(request)
            if response.status_code == 200:
                return httpx2.Response(200, json={**response.json(), "total": "2"})
            return response

        app.state.nps_alerts = NpsAlertsService(
            SecretStr("synthetic-nps-key"), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(partial_notices))
        )
        app.state.nws_alerts = NwsAlertsService(
            lambda: httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda _: httpx2.Response(200, json={"type": "FeatureCollection", "features": [{}]})
                )
            )
        )
        response = client.post(
            "/api/chat",
            data={"question": question, "locale": "en-US", "time_zone": "America/Chicago"},
            headers={"x-vercel-id": "workflow-55555555"},
        )
        assert response.status_code == 200
        response = client.post(
            "/api/knowledge/retrieval",
            data={"destination": "zion-narrows", "q": "What should I know about flash floods?", "visit_date": arrival},
            headers={"x-vercel-id": "workflow-66666666"},
        )
        assert response.status_code == 200
        response = client.post(
            "/api/parks/trip",
            data={
                "park": "zion",
                "arrival": arrival,
                "departure": departure,
                "transport": "drive",
                "adults": "1",
                "rooms": "1",
            },
            headers={"x-vercel-id": "workflow-77777777"},
        )
        assert response.status_code == 200
    rows[:] = [dict(event) for event in emitted]
    assert all(text not in json.dumps(rows) for text in (question, "Plan a trip to Dallas", "synthetic-nps-key"))
    starts = [
        {"requestId": row["requestId"], "started": row["_time"]} for row in rows if row["event"] == "http.request"
    ]
    chat_ids = {row["requestId"] for row in rows if row["event"] == "chat.request"}
    tool_starts = {
        f'== "{tool}"': [
            start
            for start in starts
            if start["requestId"] in {row["requestId"] for row in rows if row.get("tool") == tool}
        ]
        for tool in ("retrieval_playground", "search_hotels")
    }
    groups: dict[tuple[str, str, str], list[Row]] = {}
    for row in rows:
        if row["event"] in {"knowledge.call", "nps.alerts", "nws.alerts", "travel.call"}:
            groups.setdefault((str(row["event"]), str(row["tool"]), str(row["status"])), []).append(row)
    services = [
        {
            "event": event,
            "tool": tool,
            "status": status,
            "calls": len(calls),
            "totalMs": sum(cast(float, row["ms"]) for row in calls),
            "slowestMs": max(cast(float, row["ms"]) for row in calls),
        }
        for (event, tool, status), calls in groups.items()
    ]
    workflows: dict[str, list[float]] = {}
    weather_tools: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        if row["event"] == "chat.done":
            workflows.setdefault(str(row["workflow"]), []).append(cast(float, row["ms"]))
        if row["event"] == "tool.call":
            weather_tools.setdefault((str(row["tool"]), str(row["lane"])), []).append(row)
    endings = Counter(
        (str(row["event"]), str(row.get("lane", ""))) for row in rows if str(row["event"]).startswith("chat.")
    )
    upstreams = Counter(
        (str(row["event"]), str(row["status"]))
        for row in rows
        if row["event"] in {"upstream.cache", "upstream.http"}
        and row.get("upstream") == "open-meteo"
        and not row.get("check")
    )
    return AxiomRecordings(
        {
            **tool_starts,
            "summarize started = min(_time) by requestId": [row for row in starts if row["requestId"] in chat_ids],
            "where requestId in (": rows,
            'where event in ("knowledge.call"': services,
            "summarize responses": [
                {"responseWorkflow": name, "responses": len(times), "p50": median(times), "p95": max(times)}
                for name, times in workflows.items()
            ],
            'where event == "tool.call"': [
                {
                    "tool": tool,
                    "lane": lane,
                    "calls": len(calls),
                    "failed": sum(row["status"] == "failed" for row in calls),
                    "totalMs": sum(cast(float, row["ms"]) for row in calls),
                    "slowestMs": max(cast(float, row["ms"]) for row in calls),
                }
                for (tool, lane), calls in weather_tools.items()
            ],
            "by event, lane": [
                {"event": event, "lane": lane, "lines": count} for (event, lane), count in endings.items()
            ],
            "upstream.cache": [
                {"event": event, "status": status, "lines": count} for (event, status), count in upstreams.items()
            ],
        }
    )


def test_intake_and_conditions_retain_their_real_outcomes(page: Page, workflow_events: list[Row]) -> None:
    endings = {row["requestId"]: row for row in workflow_events if row["event"] == "chat.done"}
    assert endings["workflow-11111111"]["cityTripIntake"] is True
    assert endings["workflow-22222222"]["tripForm"] is True
    assert endings["workflow-33333333"]["tripForm"] is False
    decisions = [row["status"] for row in workflow_events if row["event"] == "travel.briefing"]
    assert decisions[:2] == ["pause", "pause"]
    complete = next(
        row for row in workflow_events if row["event"] == "travel.briefing" and row["requestId"] == "workflow-33333333"
    )
    assert complete["missingSections"] == complete["failedSections"] == 0
    preparation = next(
        row
        for row in workflow_events
        if row["event"] == "knowledge.call"
        and row.get("tool") == "search_park_guidance"
        and row["requestId"] == "workflow-33333333"
    )
    assert preparation["status"] == "found"
    page.goto("/activity")
    for ref in ("11111111", "22222222", "33333333"):
        row = page.locator("details.obs-details").filter(has_text=f"Ref {ref}")
        row.locator("summary").click()
        assert "tokens in" not in row.inner_text()
        assert "0 tool calls" not in row.inner_text()
    paused = page.locator("details.obs-details").filter(has_text="Ref 33333333")
    expect(paused).to_contain_text("Park trip conditions")
    expect(paused).to_contain_text("Pause travel")
    expect(paused).to_contain_text("search_park_guidance")
    expect(paused.locator("summary")).to_have_attribute("data-tone", "idle")
    assert "went wrong" not in paused.locator("summary").inner_text()


def test_check_sources_and_partial_failures_match_the_emitted_events(page: Page, workflow_events: list[Row]) -> None:
    cached = [row for row in workflow_events if row.get("requestId") == "workflow-44444444"]
    for event in ("nps.alerts", "nws.alerts"):
        assert next(row for row in cached if row["event"] == event)["cached"] is True
    partial = [row for row in workflow_events if row.get("requestId") == "workflow-55555555"]
    assert next(row for row in partial if row["event"] == "nps.alerts")["status"] == "partial"
    assert next(row for row in partial if row["event"] == "nws.alerts")["status"] == "partial"
    page.goto("/activity")
    row = page.locator("details.obs-details").filter(has_text="Ref 44444444")
    row.locator("summary").click()
    expect(row.get_by_text("cached result", exact=False)).to_have_count(2)
    row = page.locator("details.obs-details").filter(has_text="Ref 55555555")
    row.locator("summary").click()
    expect(row).to_contain_text("partial")
    expect(row).to_contain_text("upstream server error")
    expect(row).to_contain_text("NWS weather alerts")
    expect(row.locator("summary")).to_have_attribute("data-tone", "warn")


def test_retrieval_and_failed_hotel_are_visible_without_exposing_input(page: Page, workflow_events: list[Row]) -> None:
    retrieval = next(row for row in workflow_events if row.get("tool") == "retrieval_playground")
    hotel = next(row for row in workflow_events if row.get("tool") == "search_hotels")
    assert retrieval["status"] == "found"
    assert hotel["status"] == "timeout"
    for ref, expected in (("66666666", "retrieval_playground"), ("77777777", "search_hotels")):
        page.goto(f"/activity?tool={expected}")
        row = page.locator("details.obs-details").filter(has_text=f"Ref {ref}")
        row.locator("summary").click()
        expect(row).to_contain_text(expected)
    failed = page.locator("details.obs-details").filter(has_text="Ref 77777777")
    expect(failed).to_contain_text("trivago timeout")
    expect(failed.locator("summary")).to_have_attribute("data-tone", "warn")
    assert "flash floods?" not in page.locator("main").inner_text()


def test_performance_counts_the_same_recorded_service_outcomes(page: Page, workflow_events: list[Row]) -> None:
    assert not any(row.get("workflow") == "agent" for row in workflow_events)
    page.goto("/performance")
    expect(page.get_by_text("No completed model answers in this period.")).to_be_visible()
    responses = page.locator('section[aria-labelledby="responses"]')
    expect(responses).to_contain_text("Clarifications and guidance")
    expect(responses).to_contain_text("2 responses")
    expect(responses).to_contain_text("Park conditions briefings")
    expect(responses).to_contain_text("3 responses")
    checks = page.locator('section[aria-labelledby="services"]')
    expect(checks).to_contain_text("search_hotels")
    expect(checks).to_contain_text("1 timeout")
    nps = checks.locator("li").filter(has_text="NPS notices · park_trip_briefing")
    counts = Counter(
        str(row["status"])
        for row in workflow_events
        if row["event"] == "nps.alerts" and row["tool"] == "park_trip_briefing"
    )
    for status, count in counts.items():
        expect(nps).to_contain_text(f"{count} {status}")
    expect(checks).to_contain_text("retrieval_playground")
    guidance = checks.locator("li").filter(has_text="search_park_guidance")
    guidance_calls = sum(row.get("tool") == "search_park_guidance" for row in workflow_events)
    expect(guidance).to_contain_text(f"{guidance_calls} calls")
    weather = page.locator('section[aria-labelledby="tools"]')
    weather_calls = sum(row["event"] == "tool.call" for row in workflow_events)
    expect(weather).to_contain_text(f"{weather_calls} calls")
    expect(weather).to_contain_text("get_forecast")
