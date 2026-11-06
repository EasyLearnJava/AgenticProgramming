"""
tests/unit/test_privacy.py: what never leaves the app, or never lands in its logs (step 11). A question and a
conversation, each with a word of its own, go through three lanes: REST · no auth, MCP · no auth through our own server,
and REST · with auth through Apify. No log line holds either word, nor the place asked; no request to Open-Meteo, to
our MCP server or to Apify holds either word; Apify gets the point, rounded, and no token in a chip or a log line.
And LangSmith, when tracing is on, gets neither word, even of a run that failed (issue 68).
"""

import asyncio
import json
from collections.abc import Coroutine, Mapping, MutableMapping
from typing import Any
from uuid import UUID

import httpx2
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith import Client
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus import model
from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from tests.fakes import PARIS_STEPS, ApifyRecordings, FakeCacheStore, FakeModel, OpenMeteoRecordings

QUESTION_WORD = "zebra-question-7319"
HISTORY_WORD = "okapi-history-5521"
TOKEN = "test-apify-token-8842"  # noqa: S105 - a stand-in, not a token
LOCAL_MCP = "http://127.0.0.1:8000/api/mcp"


def make_app(
    settings: Settings,
    chat_model: FakeModel,
    open_meteo: OpenMeteoRecordings,
    apify: ApifyRecordings,
    to_mcp: list[str],
) -> FastAPI:
    """
    The app with Apify's token, every way out played back, the MCP lane calling the app's own server: each request
    to it kept in to_mcp, its address and body.
    """

    async def keep(request: httpx2.Request) -> None:
        to_mcp.append(str(request.url) + (await request.aread()).decode())

    app = create_app(settings.model_copy(update={"apify_token": SecretStr(TOKEN)}))
    chat_model.tool_steps = PARIS_STEPS
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    app.state.make_apify_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(apify))
    app.state.to_mcp_url = lambda _request, _settings: LOCAL_MCP
    app.state.make_mcp_http_client = lambda: httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), event_hooks={"request": [keep]}
    )
    return app


def ask(app: FastAPI, lane: str) -> tuple[str, list[MutableMapping[str, Any]]]:
    """A question with its own word, after a conversation with another, on the lane: the answer, and the log lines."""
    history = json.dumps([{"role": "user", "text": f"Hi {HISTORY_WORD}"}, {"role": "assistant", "text": "Hello."}])
    form = {"question": f"Will it rain in Paris tomorrow? {QUESTION_WORD}", "history": history, "lane": lane}
    with TestClient(app, base_url="http://127.0.0.1:8000") as client, capture_logs() as lines:
        answer = client.post("/api/chat", data=form)
    assert answer.status_code == 200
    return answer.text, lines


@pytest.mark.parametrize("lane", ["rest-no-auth", "mcp-no-auth", "rest-with-auth"])
def test_no_log_line_holds_the_question_the_conversation_or_the_place(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, lane: str
) -> None:
    _, lines = ask(make_app(settings, chat_model, open_meteo, ApifyRecordings(), []), lane)
    written = json.dumps([dict(line) for line in lines], default=str)
    assert "tool.call" in written
    for word in (QUESTION_WORD, HISTORY_WORD, "Paris", TOKEN):
        assert word not in written


@pytest.mark.parametrize("lane", ["rest-no-auth", "mcp-no-auth", "rest-with-auth"])
def test_no_request_out_holds_the_question_or_the_conversation(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, lane: str
) -> None:
    apify = ApifyRecordings()
    to_mcp: list[str] = []
    ask(make_app(settings, chat_model, open_meteo, apify, to_mcp), lane)
    sent = [str(request.url) + request.content.decode() for request in open_meteo.requests + apify.requests]
    assert sent
    assert bool(to_mcp) == (lane == "mcp-no-auth")
    for request in sent + to_mcp:
        assert QUESTION_WORD not in request
        assert HISTORY_WORD not in request


def test_apify_gets_the_point_rounded_and_the_token_only_in_its_header(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings
) -> None:
    apify = ApifyRecordings()
    text, _ = ask(make_app(settings, chat_model, open_meteo, apify, []), "rest-with-auth")
    [run] = apify.requests
    assert json.loads(run.content)["locations"] == [{"name": "48.85, 2.35", "latitude": 48.85, "longitude": 2.35}]
    assert run.headers["authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in str(run.url)
    assert TOKEN not in text


class KeepingClient(Client):
    """LangSmith's client as the app makes it, but with every run sent at once, and kept here instead: none leaves."""

    def __init__(self, **kwargs: Any) -> None:
        """The app's own client, sending each run as it ends, to an address that isn't LangSmith's."""
        super().__init__(**kwargs, api_url="http://langsmith.test", auto_batch_tracing=False)
        self.kept_runs: list[dict[str, Any]] = []

    def request_with_retries(
        self, /, method: str, pathname: str, *, request_kwargs: Mapping[str, Any] | None = None, **kwargs: Any
    ) -> requests.Response:
        """Keeps each run the client would send, made or ended, and answers as LangSmith would, with nothing."""
        data = (request_kwargs or {}).get("data")
        if data is not None:
            self.kept_runs.append(json.loads(data))
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        return response


@pytest.fixture
def traced_app(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """A chat running the real graph and tracing SDK with a recorder in place of LangSmith."""
    monkeypatch.setattr(model, "Client", KeepingClient)
    tracing = {
        "langsmith_tracing": True,
        "langsmith_api_key": SecretStr("lsv2-stand-in"),
        "langsmith_hide_inputs": True,
        "langsmith_hide_outputs": True,
    }
    return make_app(settings.model_copy(update=tracing), chat_model, open_meteo, ApifyRecordings(), [])


def test_langsmith_gets_neither_word_even_of_a_run_that_failed(traced_app: FastAPI, chat_model: FakeModel) -> None:
    # A tool input our check refuses fails its run, and the run's error, pydantic's words, quotes the input.
    chat_model.tool_steps = [[{"name": "geocode_location", "args": {"query": f"Paris {QUESTION_WORD} " + "x" * 120}}]]
    ask(traced_app, "rest-no-auth")
    wait_for_all_tracers()
    runs = traced_app.state.tracer.client.kept_runs
    assert {run["error"] for run in runs if run.get("error")} == {"hidden"}
    for run in runs:
        # A run's serialized model is the stand-in's own repr, which holds the tool calls it was given to make; the
        # real model's holds its settings.
        run.pop("serialized", None)
        sent = json.dumps(run)
        assert QUESTION_WORD not in sent
        assert HISTORY_WORD not in sent


def test_activity_id_matches_the_sdk_root_and_its_children_for_success_and_failure(
    traced_app: FastAPI, chat_model: FakeModel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each question gets its own root even if the caller supplies the same request ID twice."""
    external_id = "b242283d-50ae-48d4-9ee6-29617632c206"
    trace_ids = set()
    waiting: list[Coroutine[Any, Any, None]] = []
    monkeypatch.setattr(model, "wait_until", waiting.append)
    with TestClient(traced_app) as client:
        for outcome in ("done", "failed"):
            if outcome == "failed":
                chat_model.fail_after_first_word = RuntimeError("private detail")
            with capture_logs() as lines:
                response = client.post("/api/chat", data={"question": "Paris?"}, headers={"x-vercel-id": external_id})
            [ending] = [line for line in lines if line["event"] == f"chat.{outcome}"]
            trace_id = ending["traceId"]
            assert UUID(trace_id).version == 4
            assert trace_id != external_id
            assert trace_id not in response.text
            trace_ids.add(trace_id)
            wait_for_all_tracers()
            runs = [run for run in traced_app.state.tracer.client.kept_runs if run.get("trace_id") == trace_id]
            assert any(run.get("name") == "nimbus" and run["id"] == trace_id for run in runs)
            kinds = {run["run_type"] for run in runs if run.get("parent_run_id") and "run_type" in run}
            assert "llm" in kinds
            if outcome == "done":
                assert "tool" in kinds
    assert len(trace_ids) == 2
    assert waiting == []


def test_vercel_defers_a_bounded_sdk_flush_only_for_a_traced_question(
    traced_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Vercel can finish sending a trace after the answer; a flush failure exposes none of its text."""
    settings = traced_app.state.settings.model_copy(update={"flights_enabled": True, "is_vercel": True})
    traced_app.state.settings = settings
    traced_app.state.tracer = model.make_tracer(settings)
    waiting: list[Coroutine[Any, Any, None]] = []
    timeouts: list[float | None] = []

    def broken_flush(_client: Client, timeout: float | None = None) -> None:
        timeouts.append(timeout)
        raise RuntimeError("private provider detail")

    monkeypatch.setattr(model, "wait_until", waiting.append)
    monkeypatch.setattr(KeepingClient, "flush", broken_flush)
    with TestClient(traced_app) as client, capture_logs() as lines:
        intake = client.post("/api/chat", data={"question": "Plan a trip to Zion National Park"})
        assert 'action="/api/parks/trip"' in intake.text
        assert waiting == []
        assert all("traceId" not in line for line in lines)
        answer = client.post("/api/chat", data={"question": "Paris?"})
        assert answer.status_code == 200
        [task] = waiting
        assert timeouts == []
        asyncio.run(task)
        assert timeouts == [2]
    assert any(line["event"] == "chat.done" and "traceId" in line for line in lines)
    assert "private provider detail" not in str(lines)
