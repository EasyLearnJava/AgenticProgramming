"""
Tests for main.py: the API's routes, with the engine built at start-up. The plain tests swap the engine for one with
stand-ins for Gemini (tests/fakes.py); FastAPI's TestClient calls the app directly, so no server is started.
The live test builds the real engine and asks the real Gemini.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from fastapi.testclient import TestClient

import main
from pipeline import RAGEngine

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


@pytest.fixture
def client(monkeypatch):
    stand_in_model = FakeListChatModel(responses=["Open UDP ports 500 and 4500."])
    engine = RAGEngine(embeddings=KeywordEmbeddings(), model=stand_in_model, embedding_size=SIZE)
    monkeypatch.setattr(main, "engine", engine)      # the routes and the start-up use this engine now
    with TestClient(main.app) as test_client:        # `with` runs the start-up: engine.build()
        yield test_client


def test_health(client):
    response = client.get("/api/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_the_engine_is_built_at_start_up(client):
    stats = client.get("/api/stats").json()
    assert (stats["documents"], stats["chunks"], stats["top_k"]) == (10, 28, 5)


def test_a_question_gets_the_answer_and_its_sources(client):
    response = client.post("/api/query", json={"question": "  My VPN won't connect  "})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Open UDP ports 500 and 4500."
    assert data["sources"][0]["title"] == "VPN Connection Timeout"
    assert set(data["sources"][0]) == {"title", "system", "category", "snippet"}


@pytest.mark.parametrize("body, message", [
    ({"question": ""}, "String should have at least 1 character"),
    ({"question": "   "}, "String should have at least 1 character"),       # only spaces: empty once trimmed
    ({"question": "x" * 501}, "String should have at most 500 characters"),
    ({}, "Field required"),
], ids=["empty", "blank", "501 characters", "no question"])
def test_a_bad_question_gets_a_422_and_no_call(client, body, message):
    calls_before = list(main.engine.embeddings.calls)
    response = client.post("/api/query", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == message
    assert main.engine.embeddings.calls == calls_before        # the question was never embedded


def test_a_failed_gemini_call_gets_a_502_without_the_details(client, monkeypatch, caplog):
    async def fail(question):
        raise RuntimeError("quota exceeded for project 1234")
    monkeypatch.setattr(main.engine, "aquery", fail)
    response = client.post("/api/query", json={"question": "My VPN won't connect"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Couldn't answer the question (RuntimeError)."}
    assert "quota exceeded for project 1234" in caplog.text     # the full reason is in the server's log
    assert "Traceback (most recent call last)" in caplog.text   # with where it happened


def test_without_a_key_the_server_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "-m", "uvicorn", "main:app", "--port", "8598"], cwd=FOLDER, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode != 0
    assert "Can't build the models: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.live
def test_live_a_question_through_the_api():
    with TestClient(main.app) as live_client:
        response = live_client.post("/api/query", json={"question": "How do I fix VPN connection timeouts?"})
    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "VPN Connection Timeout"
