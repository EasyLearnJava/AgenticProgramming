"""Review regressions: incomplete reports, honest diagnostics, separate page events and recoverable HTML errors."""

import asyncio
import json
from typing import Any, cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.answer import render_answer
from nimbus.nps_alerts import NpsAlertsService
from nimbus.observability import ACTIVITY_VIEWS, TIMELINE_FIELDS, to_activity_line, to_narrowing
from nimbus.park_tools import make_alert_tools
from tests.unit.test_nps_alerts import KEY, notice, service


@pytest.mark.parametrize("partial", [False, True])
def test_failed_and_partial_checks_expire_at_sixty_seconds(partial: bool) -> None:
    now = [0.0]
    requests: list[int] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        """The first page can succeed, but the next page always fails with a sanitized reason."""
        offset = int(request.url.params["start"])
        requests.append(offset)
        if partial and offset == 0:
            return httpx2.Response(200, json={"total": "2", "start": "0", "data": [notice()]})
        return httpx2.Response(503, text=KEY)

    client = service(handle, clock=lambda: now[0])

    async def run() -> None:
        """No stale success is invented; both short cache types expire precisely at the documented boundary."""
        first = await client.get("zion")
        assert first.status == ("found" if partial else "unavailable")
        assert len(first.notices) == (1 if partial else 0)
        assert not first.complete
        assert first.reason == "upstream_error"
        assert first.fetched_at is not None if partial else first.fetched_at is None
        calls = len(requests)
        now[0] = 59
        cached = await client.get("zion")
        assert cached.cached
        assert cached.fetched_at == first.fetched_at
        assert len(requests) == calls
        now[0] = 60
        refreshed = await client.get("zion")
        assert not refreshed.cached
        assert len(requests) == 2 * calls
        assert KEY not in refreshed.model_dump_json()

    with capture_logs() as logs:
        asyncio.run(run())
    assert logs[0]["status"] == ("partial" if partial else "failed")
    assert logs[0]["reason"] == "upstream_error"


def test_second_page_failure_preserves_visible_notices_and_incomplete_label(client: TestClient) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        """Return one notice, then refuse the remaining page."""
        if request.url.params["start"] == "0":
            return httpx2.Response(200, json={"total": "2", "data": [notice()]})
        return httpx2.Response(403, text=KEY)

    app = cast(FastAPI, client.app)
    app.state.nps_alerts = service(handle)
    with capture_logs() as logs:
        response = client.post("/api/parks/alerts", data={"park": "zion"})
    assert response.status_code == 200
    assert "Synthetic trail maintenance notice" in response.text
    assert "Incomplete check: showing 1 of 2" in response.text
    assert "No notices were returned" not in response.text
    event = next(row for row in logs if row["event"] == "nps.alerts")
    assert event["tool"] == "park_alerts"
    assert event["status"] == "partial"
    assert event["reason"] == "authentication_failed"
    assert KEY not in response.text + json.dumps(logs)


@pytest.mark.parametrize(
    "bad", [notice(category="New future category"), notice(description="x" * 15001), 42, notice(parkCode="yose")]
)
def test_invalid_record_does_not_discard_other_valid_notices(bad: Any) -> None:
    report = asyncio.run(
        service(lambda _r: httpx2.Response(200, json={"total": "2", "data": [bad, notice()]})).get("zion")
    )
    assert report.status == "found"
    assert len(report.notices) == 1
    assert report.notices[0].title == "Test notice"
    assert not report.complete
    assert report.reason == "invalid_record"


def test_get_is_not_a_check_and_the_page_is_distinct_from_the_chat_tool(client: TestClient) -> None:
    with capture_logs() as logs:
        assert client.get("/parks/alerts").status_code == 200
    assert not any(row["event"] == "nps.alerts" for row in logs)
    with capture_logs() as logs:
        assert client.post("/api/parks/alerts", data={"park": "zion"}).status_code == 200
    assert [row["tool"] for row in logs if row["event"] == "nps.alerts"] == ["park_alerts"]

    async def run() -> None:
        await make_alert_tools(NpsAlertsService(None))[0].ainvoke({"park_id": "zion"})

    with capture_logs() as logs:
        asyncio.run(run())
    assert [row["tool"] for row in logs if row["event"] == "nps.alerts"] == ["get_park_alerts"]
    narrowed = to_narrowing({"tool": "park_alerts"})
    assert narrowed is not None
    assert narrowed.words == "Park alert checks"


def test_throttled_alert_page_remains_html_with_selection_and_retry_header(client: TestClient) -> None:
    for _ in range(12):
        assert client.post("/api/parks/alerts", data={"park": "yosemite"}).status_code == 200
    response = client.post("/api/parks/alerts", data={"park": "yosemite"})
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["retry-after"] == "60"
    assert response.headers["cache-control"] == "no-store"
    assert "Too many park alert checks" in response.text
    assert 'value="yosemite" selected' in response.text
    assert "retrieval" not in response.text.lower().split("<main", 1)[1]
    assert 'href="/parks/alerts" aria-current="page"' in response.text


def test_network_errors_have_a_safe_distinct_reason() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        """A transport error carries private diagnostic text that must never be copied into public records."""
        raise httpx2.ConnectError(KEY, request=request)

    with capture_logs() as logs:
        report = asyncio.run(service(fail).get("zion"))
    assert report.reason == "network_error"
    assert logs[-1]["reason"] == "network_error"
    assert KEY not in json.dumps(logs) + report.model_dump_json()


def test_activity_shows_cache_and_reason_without_changing_guidance_tones() -> None:
    assert {"cached", "reason", "complete"} <= set(TIMELINE_FIELDS)
    assert 'event == "nps.alerts" and tostring(status) == "partial"' in ACTIVITY_VIEWS["errors"]
    row = {
        "_time": "2026-11-03T00:00:00Z",
        "event": "nps.alerts",
        "tool": "get_park_alerts",
        "status": "partial",
        "reason": "authentication_failed",
        "cached": True,
        "ms": 15,
    }
    line = to_activity_line(row)
    assert line is not None
    assert line.tone == "warn"
    assert "cached" in line.detail.lower()
    assert "authentication failed" in line.detail
    live = to_activity_line({**row, "status": "found", "reason": "", "cached": False})
    assert live is not None
    assert "live fetch" in live.detail
    guide = to_activity_line({**row, "event": "knowledge.call", "status": "unsupported"})
    assert guide is not None
    assert guide.tone == "ok"


def test_notice_canonicalization_matches_markdown_citation_destinations() -> None:
    raw = "HTTPS://WWW.NPS.GOV:443/zion/café closure.htm#more info"
    report = asyncio.run(
        service(lambda _r: httpx2.Response(200, json={"total": "1", "data": [notice(url=raw)]})).get("zion")
    )
    url = report.notices[0].url
    assert url == "https://www.nps.gov/zion/caf%C3%A9%20closure.htm#more%20info"
    assert not report.notices[0].source_is_fallback
    assert f'href="{url}"' in str(render_answer(f"[Notice]({url})", park_sources={url}))
