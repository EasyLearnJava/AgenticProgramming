"""
Shared test set-up for this folder. pytest reads a file named conftest.py by itself, before any test file, so this
code runs first:

    a real key (in .env or the environment)  ->  every test runs, the @pytest.mark.live ones too (real Gemini calls)
    no key                                   ->  live tests are skipped

Whatever the key, a plain test can't reach Google: the HTTP library Google's client uses can't send.
The fixtures give each test the shipped settings (with stand-in sizes, no log file, and a vector file of its own, not
saved yet), an engine built on stand-ins, the log lines it wrote, each with its trace ID, a trace store, and logging
put back as it was after setup_logging().
"""
import logging

import httpx
import pytest
from fakes import SIZE
from support import change, stand_in_engine

from src.config.settings import Settings, load_api_key, load_settings
from src.exceptions import ConfigError
from src.observability.logging_setup import APP_LOGGERS, TRACED_LIBRARY_LOGGERS, TraceIdFilter
from src.observability.trace_store import TraceStore
from src.pipeline.rag_engine import RAGEngine

try:
    load_api_key()                                         # a real key, in .env or the environment
    HAVE_KEY = True
except ConfigError:
    HAVE_KEY = False

# A pytest "hook": pytest itself calls a function with exactly this name, after it has collected the tests and
# before it runs them. Nothing in our code calls it.
def pytest_collection_modifyitems(items):
    """Skip every @pytest.mark.live test when there is no real key."""
    if HAVE_KEY:
        return
    skip = pytest.mark.skip(reason="live test: needs GOOGLE_API_KEY (see .env.example)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """In every plain test: a fake key, and httpx (what Google's client sends with) unable to send, so nothing can
    reach Google. FastAPI's TestClient sends with httpx2, so it still works."""
    if "live" in request.keywords:
        return
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-tests")

    def refuse(*args, **kwargs):
        raise RuntimeError("A plain test tried to send an HTTP request")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture
def settings(tmp_path) -> Settings:
    """The shipped config.yaml, with the stand-in embeddings' size, no log file, and the vector file in tmp_path (not
    saved yet), so no test reads or writes data/vectors.json."""
    return change(load_settings(), embeddings={"dimensions": SIZE, "vector_file": tmp_path / "vectors.json"},
                  logging={"file": None})


@pytest.fixture
def engine(settings) -> RAGEngine:
    """An engine on stand-ins, built: 10 articles, 28 chunks."""
    built = stand_in_engine(settings)
    built.build()
    return built


class LogLines(logging.Handler):
    """Every log line written during a test, each with its trace_id, as a handler of the app's would see it."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self.addFilter(TraceIdFilter())

    def emit(self, record):
        self.records.append(record)

    def messages(self, level: int = logging.DEBUG) -> list[str]:
        return [record.getMessage() for record in self.records if record.levelno >= level]

    def find(self, message: str) -> logging.LogRecord:
        return next(record for record in self.records if record.getMessage() == message)


@pytest.fixture
def logs():
    root = logging.getLogger()
    lines, level = LogLines(), root.level
    root.addHandler(lines)
    root.setLevel(logging.DEBUG)
    yield lines
    root.removeHandler(lines)
    root.setLevel(level)


@pytest.fixture
def restore_logging():
    """Put logging back as it was: setup_logging() (main() calls it) changes it for the whole process."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)
    for name in APP_LOGGERS + TRACED_LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)


@pytest.fixture
def trace_store():
    """A trace store, getting every log line as the app's does (without the console and the file); removed after."""
    store = TraceStore(max_traces=50)
    root = logging.getLogger()
    level = root.level
    root.addHandler(store)
    root.setLevel(logging.DEBUG)
    yield store
    root.removeHandler(store)
    root.setLevel(level)
