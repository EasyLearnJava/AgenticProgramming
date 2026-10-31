"""
tests/unit/test_privacy.py: what never leaves the app, or never lands in its logs (step 11). A question and a
conversation, each with a word of its own, go through three lanes: REST · no auth, MCP · no auth through our own server,
and REST · with auth through Apify. No log line holds either word, nor the place asked; no request to Open-Meteo, to
our MCP server or to Apify holds either word; Apify gets the point, rounded, and no token in a chip or a log line.
"""

import json
from collections.abc import MutableMapping
from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

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
