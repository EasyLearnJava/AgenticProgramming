"""
tests/e2e/conftest.py: the browser tests' app: the real app, served by Uvicorn on a free port, in a thread, for the
whole session. pytest-playwright opens its pages from base_url. Run them with `uv run pytest tests/e2e`, adding
`--browser-channel msedge` to use the Edge already on your computer.
"""

import socket
import threading
import time
from collections.abc import Iterator

import httpx2
import pytest
import uvicorn

from nimbus.app import create_app
from nimbus.config import Settings
from tests.fakes import PARIS_STEPS, FakeModel, OpenMeteoRecordings

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
def chat_model() -> FakeModel:
    """
    Gemini needs a key and costs quota: a stand-in answers for the whole session. It asks for the place, then its
    forecast, then writes its words; a test reads what it was sent.
    """
    return FakeModel(delay=0.06, tool_steps=PARIS_STEPS)


@pytest.fixture(scope="session")
def base_url(open_meteo: OpenMeteoRecordings, chat_model: FakeModel) -> Iterator[str]:
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
    )
    app = create_app(settings)
    # Stand-ins answer: the model, and Open-Meteo, whose weather changes by the hour.
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + STARTUP_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("The app didn't start within 10 s.")
        time.sleep(POLL_SECONDS)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join()
