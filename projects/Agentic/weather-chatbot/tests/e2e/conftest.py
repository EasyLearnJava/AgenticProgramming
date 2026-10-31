"""
tests/e2e/conftest.py: the browser tests' app: the real app, served by Uvicorn on a free port, in a thread, for the
whole session. pytest-playwright opens its pages from base_url. Run them with `uv run pytest tests/e2e`, adding
`--browser-channel msedge` to use the Edge already on your computer.
"""

import asyncio
import json
import socket
import threading
import time
from collections.abc import Iterator

import httpx2
import pytest
import uvicorn
from playwright.sync_api import BrowserContext

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from tests.fakes import PARIS_STEPS, FakeCacheStore, FakeModel, OpenMeteoRecordings

STARTUP_SECONDS = 10
POLL_SECONDS = 0.05


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
def base_url(open_meteo: OpenMeteoRecordings, chat_model: FakeModel, cache_store: FakeCacheStore) -> Iterator[str]:
    """The app's address, once Uvicorn is serving it; Uvicorn stops when the session ends."""
    port = _free_port()
    # Every setting given here, so the shell's environment can't change the app; it logs only warnings, so its line
    # per request doesn't fill the test output.
    settings = Settings(
        _env_file=None,
        is_vercel=False,
        vercel_env=None,
        vercel_git_commit_sha=None,
        vercel_deployment_id=None,
        log_level="warning",
        apify_token=None,
        axiom_token=None,
        axiom_dataset=None,
        sentry_dsn=None,
    )
    app = create_app(settings)
    # Stand-ins answer: the model, and Open-Meteo, whose weather changes by the hour; and the cache.
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(cache_store)
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


# What the page hears when it asks for each lane's health (step 12): every lane that's open working.
WORKING = {
    "status": "ok",
    "lanes": {"rest-no-auth": "ok", "rest-with-auth": "off", "mcp-no-auth": "ok", "mcp-with-auth": "off"},
}


@pytest.fixture(autouse=True)
def health_answered_in_the_browser(context: BrowserContext) -> None:
    """
    The page's ask for each lane's health, answered in the browser: the app's own answer runs four checks, and a test
    that's done first would close the page on a request still being answered, which the server, in this same process,
    then leaves half-read (issue 75). The tests of the dots ask the app itself, or answer it their own way.
    """
    body = json.dumps(WORKING)
    context.route("**/api/health", lambda route: route.fulfill(status=200, content_type="application/json", body=body))
