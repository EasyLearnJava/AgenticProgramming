"""Official notice retrieval is scoped, bounded, secret-free, cached honestly and independent of Gemini."""

import asyncio
import json
from typing import Any, cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.nps_alerts import NpsAlertsService

KEY = "test-nps-secret-not-a-real-key"


def notice(**changes: Any) -> dict[str, Any]:
    """A synthetic API notice, never represented as actual current park conditions."""
    return {
        "id": "fixture-1",
        "parkCode": "zion",
        "category": "Caution",
        "title": "Test notice",
        "description": "Synthetic trail maintenance notice.",
        "url": "https://www.nps.gov/zion/index.htm",
        "lastIndexedDate": "2026-11-03 08:00:00.0",
        **changes,
    }


def service(handler: Any, **kwargs: Any) -> NpsAlertsService:
    """An NPS client backed entirely by local recordings."""
    return NpsAlertsService(
        SecretStr(KEY), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), **kwargs
    )


def test_key_is_a_header_and_only_a_supported_park_code_leaves_the_server() -> None:
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Record the outgoing request and return a synthetic park-scoped response."""
        requests.append(request)
        return httpx2.Response(200, json={"total": "1", "start": "0", "data": [notice()]})

    with capture_logs() as logs:
        result = asyncio.run(service(handle).get("zion"))
    assert result.status == "found"
    assert result.complete
    assert result.fetched_at is not None
    assert requests[0].headers["X-Api-Key"] == KEY
    assert requests[0].url.params["parkCode"] == "zion"
    assert KEY not in str(requests[0].url)
    assert KEY not in result.model_dump_json() + json.dumps(logs)
    assert result.notices[0].last_indexed == "2026-11-03 08:00:00.0"


def test_missing_key_and_unsupported_parks_never_contact_nps() -> None:
    def forbidden() -> httpx2.AsyncClient:
        """Any network setup would fail this test."""
        pytest.fail("No HTTP client should be opened")

    assert asyncio.run(NpsAlertsService(None, forbidden).get("zion")).status == "not_configured"
    assert asyncio.run(NpsAlertsService(SecretStr(KEY), forbidden).get("yellowstone")).status == "unsupported"


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_failed_checks_are_distinct_from_no_notices_and_do_not_echo_error_bodies(status: int) -> None:
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Even a parseable empty payload must not turn a failed HTTP request into a successful check."""
        requests.append(request)
        return httpx2.Response(
            status, json={"total": "0", "data": [], "error": KEY}, headers={"location": "https://foreign.example/"}
        )

    result = asyncio.run(service(handle).get("zion"))
    assert result.status == "unavailable"
    assert not result.notices
    assert KEY not in result.model_dump_json()
    assert len(requests) == 1


def test_a_successful_empty_response_is_not_a_safety_or_open_status() -> None:
    result = asyncio.run(service(lambda _r: httpx2.Response(200, json={"total": "0", "data": []})).get("zion"))
    assert result.status == "no_alerts"
    assert result.complete
    assert "safe" not in result.status


def test_foreign_parks_and_malformed_or_oversized_results_fail_closed() -> None:
    for payload in [
        {"total": "1", "data": [notice(parkCode="yose")]},
        {"total": "1", "data": [notice(category="Invented category")]},
        {"total": "1", "data": []},
        {"total": "oops", "data": []},
    ]:
        result = asyncio.run(service(lambda _r, data=payload: httpx2.Response(200, json=data)).get("zion"))
        assert result.status == "unavailable"
    result = asyncio.run(
        service(lambda _r: httpx2.Response(200, json={"total": "0", "data": [], "padding": "x" * 1_100_000})).get(
            "zion"
        )
    )
    assert result.status == "unavailable"


def test_cache_hits_expire_and_failed_refresh_never_uses_old_notices() -> None:
    clock = [0.0]
    calls = []

    def handle(_request: httpx2.Request) -> httpx2.Response:
        """Succeed once, then simulate an outage after the cached result expires."""
        calls.append(True)
        return (
            httpx2.Response(200, json={"total": "1", "data": [notice()]}) if len(calls) == 1 else httpx2.Response(503)
        )

    client = service(handle, clock=lambda: clock[0])

    async def run() -> None:
        """Check original fetch time, detached cache values and honest failed refresh behavior."""
        first = await client.get("zion")
        cached = await client.get("zion")
        assert cached.cached
        assert cached.fetched_at == first.fetched_at
        assert len(calls) == 1
        clock[0] = 301
        failed = await client.get("zion")
        assert failed.status == "unavailable"
        assert not failed.notices
        assert len(calls) == 2

    asyncio.run(run())


def test_pagination_is_bounded_and_partial_data_is_labeled() -> None:
    calls = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Return fifty different records for each requested page."""
        start = int(request.url.params["start"])
        calls.append(start)
        return httpx2.Response(
            200,
            json={
                "total": "200",
                "start": str(start),
                "data": [notice(id=f"fixture-{start + index}") for index in range(50)],
            },
        )

    result = asyncio.run(service(handle).get("zion"))
    assert calls == [0, 50, 100]
    assert result.status == "found"
    assert not result.complete
    assert len(result.notices) == 150
    assert result.total == 200


def test_concurrent_checks_share_one_request_and_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from nimbus import nps_alerts

    calls = []

    async def handle(_request: httpx2.Request) -> httpx2.Response:
        """Hold a single in-flight request long enough to exercise coalescing."""
        calls.append(True)
        await asyncio.sleep(0.02)
        return httpx2.Response(200, json={"total": "0", "data": []})

    async def run() -> None:
        """Many visitors share one check and one source-fetch timestamp."""
        client = service(handle)
        results = await asyncio.gather(*(client.get("zion") for _ in range(8)))
        assert len(calls) == 1
        assert all(result.status == "no_alerts" for result in results)

    asyncio.run(run())
    monkeypatch.setattr(nps_alerts, "NPS_TIMEOUT_SECONDS", 0.001)
    assert asyncio.run(service(handle).get("zion")).status == "unavailable"


def test_page_works_without_gemini_and_escapes_notice_text_and_unsafe_links(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.chat_model = None
    app.state.nps_alerts = service(
        lambda _r: httpx2.Response(
            200, json={"total": "1", "data": [notice(title="<script>unsafe</script>", url="javascript:alert(1)")]}
        )
    )
    page = client.post("/api/parks/alerts", data={"park": "zion"})
    assert page.status_code == 200
    assert "&lt;script&gt;" in page.text
    assert "<script>unsafe" not in page.text
    assert "javascript:" not in page.text
    assert KEY not in page.text
    assert "Fetched" in page.text
    assert "Last indexed by NPS" in page.text
    assert "not an opening or safety guarantee" in page.text
    assert 'href="/parks/alerts" aria-current="page"' in page.text


def test_alert_input_and_missing_configuration_states(client: TestClient) -> None:
    assert "not configured" in client.get("/parks/alerts").text
    assert client.post("/api/parks/alerts", data={"park": "elsewhere"}).status_code == 400
    assert client.post("/api/parks/alerts", data={"park": "zion", "extra": "x"}).status_code == 400
    assert (
        client.post(
            "/api/parks/alerts", data={"park": "zion"}, headers={"origin": "https://foreign.example"}
        ).status_code
        == 403
    )
