"""
tests/e2e/conftest.py: the browser tests' app: the real app, served by Uvicorn on a free port, in a thread, for the
whole session. pytest-playwright opens its pages from base_url. Run them with `uv run pytest tests/e2e`, adding
`--browser-channel msedge` to use the Edge already on your computer.
"""

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import httpx2
import pytest
import uvicorn
from fastapi import FastAPI
from pydantic import SecretStr

from nimbus.app import create_app
from nimbus.axiom_query import AxiomQuery, Row
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.nps_alerts import NpsAlertsService
from nimbus.nws_alerts import NwsAlertsService
from nimbus.observability import get_activity_trace_reader
from nimbus.trace_view import TraceRow, TraceView
from tests.fakes import PARIS_STEPS, AxiomRecordings, FakeCacheStore, FakeModel, OpenMeteoRecordings
from tests.travel_fakes import travel_service

STARTUP_SECONDS = 10
POLL_SECONDS = 0.05


def trace_recordings(app: FastAPI) -> AxiomRecordings:
    """A recent traced request, one awaiting upload, and one recorded before trace correlation was enabled."""
    ready = UUID("1cd9a312-dd4d-4696-ac81-9e3521b2d07a")
    pending = UUID("2edb2101-262d-41ad-ba41-d71c8c9d128e")
    traces = {"ready-11111111": ready, "pending-22222222": pending, "legacy-33333333": None}
    now = datetime.now(UTC).isoformat()

    async def fake_reader(_settings: Settings, trace_id: UUID) -> TraceView:
        if trace_id == pending:
            return TraceView(status="pending")
        assert trace_id == ready
        rows = (
            TraceRow(kind="Agent", label="Nimbus agent", depth=0, offset_ms=0, elapsed_ms=950, status="Completed"),
            TraceRow(kind="Model", label="Gemini", depth=1, offset_ms=30, elapsed_ms=880, status="Completed"),
            TraceRow(
                kind="Tool",
                label="get_forecast",
                depth=1,
                offset_ms=920,
                elapsed_ms=12,
                status="Failed",
                error="Tool call failed",
            ),
        )
        return TraceView(status="ready", rows=rows)

    app.dependency_overrides[get_activity_trace_reader] = lambda: fake_reader
    return AxiomRecordings(
        {
            "summarize started = min(_time) by requestId": [{"requestId": key, "started": now} for key in traces],
            "where requestId in (": [
                {
                    "requestId": key,
                    "_time": now,
                    "event": event,
                    "lane": "rest-no-auth",
                    "traceId": str(trace_id) if trace_id and event == "chat.done" else None,
                }
                for key, trace_id in traces.items()
                for event in ("chat.request", "chat.done")
            ],
        }
    )


def _free_port() -> int:
    """A port no other program is using, chosen by the system."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def open_meteo() -> OpenMeteoRecordings:
    """Open-Meteo, played back for the whole session: each call takes 0.3 s, unless a test slows it down."""
    return OpenMeteoRecordings(delay=0.3)


@pytest.fixture
def slow_open_meteo(open_meteo: OpenMeteoRecordings) -> Iterator[OpenMeteoRecordings]:
    """
    Open-Meteo taking 1.5 s a call, for a test that must catch a call while it runs: the browser's checks come every
    half second at worst, which could miss a call of 0.3 s on a slow machine (issue 52).
    """
    open_meteo.delay = 1.5
    yield open_meteo
    open_meteo.delay = 0.3


@pytest.fixture(scope="session")
def cache_store() -> FakeCacheStore:
    """Vercel's Runtime Cache, played in memory for the whole session."""
    return FakeCacheStore()


@pytest.fixture(autouse=True)
def empty_cache(cache_store: FakeCacheStore) -> None:
    """Nothing kept when a test starts, so no test's weather comes from another's."""
    cache_store.items.clear()


@pytest.fixture(scope="session")
def chat_model() -> FakeModel:
    """
    Gemini needs a key and costs quota: a stand-in answers for the whole session. It asks for the place, then its
    forecast, then writes its words; a test reads what it was sent.
    """
    return FakeModel(delay=0.06, tool_steps=PARIS_STEPS)


@pytest.fixture(scope="session")
def workflow_events() -> list[Row]:
    """Actual endpoint events recorded for the observability browser regressions."""
    return []


@pytest.fixture(scope="session")
def base_url(
    request: pytest.FixtureRequest,
    open_meteo: OpenMeteoRecordings,
    chat_model: FakeModel,
    cache_store: FakeCacheStore,
    workflow_events: list[Row],
) -> Iterator[str]:
    """The app's address, once Uvicorn is serving it; Uvicorn stops when the session ends."""
    port = _free_port()
    # Every setting given here, so the shell's environment can't change the app. Only the source-to-display
    # regressions enable info-level events; ordinary tests keep the output quiet.
    settings = Settings(
        _env_file=None,
        is_vercel=False,
        vercel_env=None,
        vercel_git_commit_sha=None,
        vercel_deployment_id=None,
        log_level="info" if getattr(request, "param", None) == "observability" else "warning",
        apify_token=None,
        axiom_token=None,
        axiom_dataset="weather-chatbot",
        axiom_query_token=SecretStr("xaat-query-test") if getattr(request, "param", None) == "trace" else None,
        sentry_dsn=None,
        nps_api_key=None,
        flights_enabled=getattr(request, "param", None) in {"travel", "flights-only", "observability"},
        hotels_enabled=getattr(request, "param", None) in {"travel", "observability"},
    )
    app = create_app(settings)
    app.state.nws_alerts = NwsAlertsService(
        lambda: httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda _: httpx2.Response(200, json={"type": "FeatureCollection", "features": []})
            )
        )
    )
    # Stand-ins answer: the model, and Open-Meteo, whose weather changes by the hour; and the cache.
    app.state.chat_model = chat_model
    if settings.flights_enabled:
        app.state.travel_service = travel_service()
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(cache_store)

    # Synthetic notices exercise the server-side integration without any real credential or NPS call.
    def notices(request: httpx2.Request) -> httpx2.Response:
        """Three predictable outcomes, with the requested park code only and an explicitly synthetic notice."""
        code = request.url.params["parkCode"]
        if code == "grca":
            return httpx2.Response(503)
        rows = [
            {
                "id": "synthetic",
                "parkCode": code,
                "category": "Caution",
                "title": "Synthetic maintenance",
                "description": "Test fixture: maintenance in a named area. This is not a real current notice.",
                "url": "https://www.nps.gov/zion/index.htm",
                "lastIndexedDate": "2026-11-03 08:00:00.0",
            }
        ]
        return httpx2.Response(
            200, json={"total": "1" if code == "zion" else "0", "data": rows if code == "zion" else []}
        )

    app.state.nps_alerts = NpsAlertsService(
        SecretStr("synthetic-nps-key"), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(notices))
    )
    # And Axiom's query door, played back with its recorded rows, for the Observability pages (step 14).
    axiom = trace_recordings(app) if getattr(request, "param", None) == "trace" else AxiomRecordings()
    if getattr(request, "param", None) == "observability":
        from tests.e2e.test_observability_workflows import workflow_recordings

        axiom = workflow_recordings(app, workflow_events)
    token = SecretStr("xaat-query-test")
    app.state.axiom_query = AxiomQuery(token, lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(axiom)))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    # On a selector loop: on Windows, the default loop, the proactor, can lose its listening socket when a browser
    # resets a connection before it's accepted, and every later test then fails to connect (issue 75).
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop), daemon=True
    )
    thread.start()
    deadline = time.monotonic() + STARTUP_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The app didn't start within 10 s.")
        time.sleep(POLL_SECONDS)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()
