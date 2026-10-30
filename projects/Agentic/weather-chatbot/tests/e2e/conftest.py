"""
tests/e2e/conftest.py: the browser tests' app: the real app, served by Uvicorn on a free port, in a thread, for the
whole session. pytest-playwright opens its pages from base_url. Run them with `uv run pytest tests/e2e`, adding
`--browser-channel msedge` to use the Edge already on your computer.
"""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from nimbus.app import create_app
from nimbus.config import Settings

STARTUP_SECONDS = 10
POLL_SECONDS = 0.05


def _free_port() -> int:
    """A port no other program is using, chosen by the system."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def base_url() -> Iterator[str]:
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
