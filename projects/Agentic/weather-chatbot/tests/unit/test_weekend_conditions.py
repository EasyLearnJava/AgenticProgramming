"""Offline conditions checks at real park reference points with recorded forecast, NPS and NWS responses."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx2
import pytest
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.nws_alerts import ACTIVE_ALERTS, MAX_BYTES, NwsAlertsService
from nimbus.parks import Destination, ParkKnowledge
from nimbus.tools import Day, ForecastOutput
from nimbus.travel.conditions import check_conditions, verified_reference
from tests.unit.test_nps_alerts import notice, service

NOW = datetime(2026, 11, 5, 17, tzinfo=UTC)
ARRIVAL = date(2026, 11, 6)
DEPARTURE = date(2026, 11, 8)


@pytest.fixture
def knowledge(settings: Settings) -> ParkKnowledge:
    return ParkKnowledge(settings.parks_index_path)


def feature(**changes: Any) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "event": "Flash Flood Warning",
            "areaDesc": "Synthetic forecast area",
            "severity": "Severe",
            "headline": "Recorded warning",
            "status": "Actual",
            "messageType": "Alert",
            "effective": "2026-11-05T15:00:00Z",
            "onset": "2026-11-06T19:00:00-07:00",
            "expires": "2026-11-07T01:00:00-07:00",
            **changes,
        },
    }


def nws_service(handler: Any, **kwargs: Any) -> NwsAlertsService:
    return NwsAlertsService(lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), **kwargs)


def test_reference_requires_matching_registry_park_and_destination(knowledge: ParkKnowledge) -> None:
    trail = verified_reference(knowledge, "zion", "zion-narrows")
    assert trail is not None
    assert trail.id == "zion-narrows"
    assert verified_reference(knowledge, "yosemite", "zion-narrows") is None
    assert verified_reference(knowledge, "zion", "outside-index") is None


def test_nws_request_and_cache_are_shared_only_by_reference_point(knowledge: ParkKnowledge) -> None:
    zion = verified_reference(knowledge, "zion")
    yosemite = verified_reference(knowledge, "yosemite")
    assert zion is not None
    assert yosemite is not None
    requests: list[httpx2.Request] = []
    clock = [0.0]

    async def handle(req: httpx2.Request) -> httpx2.Response:
        requests.append(req)
        await asyncio.sleep(0)
        return httpx2.Response(200, json={"type": "FeatureCollection", "features": [feature(), feature(status="Test")]})

    nws = nws_service(handle, clock=lambda: clock[0])

    async def check() -> None:
        first, cached = await asyncio.gather(nws.get(zion), nws.get(zion))
        assert first == cached
        assert first.complete
        assert len(first.items) == 1
        assert first.items[0].overlap(ARRIVAL, DEPARTURE, zion.time_zone) == "overlaps"
        assert first.items[0].end is None
        assert first.items[0].overlap(DEPARTURE, DEPARTURE, zion.time_zone) == "unknown"
        assert len(requests) == 1
        assert str(requests[0].url).split("?")[0] == ACTIVE_ALERTS
        assert requests[0].url.params["point"] == "37.2508,-112.9563"
        assert "Nimbus" in requests[0].headers["User-Agent"]
        assert "authorization" not in requests[0].headers
        assert first.source_url.startswith("https://forecast.weather.gov/MapClick.php?")
        await nws.get(yosemite)
        clock[0] = 61
        await nws.get(zion)
        assert len(requests) == 3

    asyncio.run(check())


@pytest.mark.parametrize("mode", ["429", "redirect", "oversize", "malformed", "missing", "paginated", "bad_time"])
def test_failed_or_partial_warnings_never_look_clear(knowledge: ParkKnowledge, mode: str) -> None:
    point = verified_reference(knowledge, "zion")
    assert point is not None
    count = 0
    clock = [0.0]

    def handle(req: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        if mode == "429":
            return httpx2.Response(429, json={"type": "FeatureCollection", "features": []})
        if mode == "redirect":
            return httpx2.Response(302, headers={"Location": "https://untrusted.example/"})
        if mode == "oversize":
            return httpx2.Response(200, content=b" " * (MAX_BYTES + 1))
        if mode == "malformed":
            return httpx2.Response(200, content=b"broken")
        data: dict[str, Any] = {"type": "FeatureCollection", "features": [feature()]}
        if mode == "missing":
            data["features"].append({"type": "Feature"})
        elif mode == "bad_time":
            data["features"].append(feature(expires="2026-01-01"))
        else:
            data["pagination"] = {"next": "https://untrusted.example/"}
        return httpx2.Response(200, json=data)

    nws = nws_service(handle, clock=lambda: clock[0])

    async def run() -> None:
        report = await nws.get(point)
        assert not report.complete
        assert len(report.items) == int(mode in {"missing", "bad_time", "paginated"})
        await nws.get(point)
        assert count == 1
        clock[0] = 31
        await nws.get(point)
        assert count == 2

    with capture_logs() as logs:
        asyncio.run(run())
    checks = [line for line in logs if line["event"] == "nws.alerts"]
    assert [line["cached"] for line in checks] == [False, True, False]
    assert all(
        line["status"] == ("partial" if mode in {"missing", "paginated", "bad_time"} else "failed") for line in checks
    )
    assert "Recorded warning" not in str(checks)
    assert "37.2508" not in str(checks)


@pytest.mark.parametrize(
    ("scenario", "expect"),
    [
        ("no_alert", "proceed"),
        ("expired", "proceed"),
        ("open_ended", "review"),
        ("next_local_day", "proceed"),
        ("severe", "pause"),
        ("severe_partial", "pause"),
        ("minor", "adapt"),
        ("trail_closed", "adapt"),
        ("whole_dated", "pause"),
        ("whole_informational", "pause"),
        ("second_interval_overlaps", "pause"),
        ("both_intervals_outside", "proceed"),
        ("unverified_second_interval", "review"),
        ("informational_update", "proceed"),
        ("whole_unknown", "review"),
        ("whole_outside", "proceed"),
        ("qualifier", "review"),
        ("outage", "review"),
        ("nps_down", "review"),
        ("horizon", "review"),
        ("storm", "adapt"),
        ("unknown_weather", "review"),
    ],
)
def test_conditions_change_with_recorded_evidence(knowledge: ParkKnowledge, scenario: str, expect: str) -> None:
    park = verified_reference(knowledge, "zion")
    assert park is not None
    start, end = (
        (ARRIVAL, DEPARTURE)
        if scenario != "horizon"
        else (ARRIVAL + timedelta(days=50), DEPARTURE + timedelta(days=50))
    )
    calls: list[str] = []

    async def forecast(destination: Destination, days: int) -> ForecastOutput:
        calls.append("forecast")
        assert destination == park
        assert days <= 16
        return ForecastOutput.model_validate(
            {
                "latitude": park.latitude,
                "longitude": park.longitude,
                "time_zone": park.time_zone,
                "local_now": NOW.isoformat(),
                "temperature_unit": "F",
                "hours": None,
                "days": [
                    Day.model_validate(
                        {
                            "date": (ARRIVAL + timedelta(days=i)).isoformat(),
                            "weekday": "Fri",
                            "condition": {
                                "storm": "Thunderstorm with hail",
                                "unknown_weather": "Unknown conditions",
                            }.get(scenario, "Clear"),
                            "temperature_min": 42,
                            "temperature_max": 65,
                            "rain_chance_percent": 20,
                            "sunrise": None,
                            "sunset": None,
                        }
                    )
                    for i in range(3)
                ],
            }
        )

    def weather_alerts(req: httpx2.Request) -> httpx2.Response:
        calls.append("nws")
        items = []
        if scenario in {"severe", "severe_partial"}:
            items.append(feature())
        elif scenario == "expired":
            items.append(feature(onset=None, ends="2026-11-06T00:00:00-07:00", expires="2026-11-06T00:00:00-07:00"))
        elif scenario == "open_ended":
            items.append(feature(onset=None, ends=None, expires="2026-11-06T00:00:00-07:00"))
        elif scenario == "next_local_day":
            items.append(feature(onset="2026-11-09T00:00:00-07:00", expires="2026-11-10T00:00:00-07:00"))
        elif scenario == "minor":
            items.append(feature(event="Wind Advisory", severity="Minor"))
        if scenario == "severe_partial":
            items.append({})
        return httpx2.Response(
            429 if scenario == "outage" else 200, json={"type": "FeatureCollection", "features": items}
        )

    def park_alerts(req: httpx2.Request) -> httpx2.Response:
        calls.append("nps")
        earlier = "Zion National Park is closed from 2026-10-01 through 2026-10-02."
        during = "Zion National Park is closed from 2026-11-05 through 2026-11-07."
        later = "Zion National Park is closed from 2026-11-10 through 2026-11-13."
        cases = {
            "trail_closed": "The Narrows trail is closed.",
            "whole_dated": during,
            "whole_informational": during,
            "second_interval_overlaps": f"{earlier} {during}",
            "both_intervals_outside": f"{earlier} {later}",
            "unverified_second_interval": f"{earlier} Zion National Park is closed until further notice.",
            "informational_update": "The park visitor guide is available.",
            "whole_unknown": "Zion National Park is closed.",
            "whole_outside": later,
            "qualifier": "Zion National Park is closed to buses.",
        }
        category = "Information" if scenario in {"whole_informational", "informational_update"} else "Park Closure"
        notices = (
            [notice(category=category, title="NPS notice", description=cases[scenario])] if scenario in cases else []
        )
        return httpx2.Response(500 if scenario == "nps_down" else 200, json={"total": len(notices), "data": notices})

    async def check() -> None:
        result = await check_conditions(
            park="zion",
            arrival=start,
            departure=end,
            activity="",
            destination=park,
            knowledge=knowledge,
            alerts=service(park_alerts),
            nws=nws_service(weather_alerts),
            forecast=forecast,
            now=NOW,
            deadline=asyncio.get_running_loop().time() + 4,
        )
        assert result.decision == expect, (result.reason, result.weather)
        assert set(calls) == ({"nws", "nps"} if scenario == "horizon" else {"nws", "nps", "forecast"})

    asyncio.run(check())
