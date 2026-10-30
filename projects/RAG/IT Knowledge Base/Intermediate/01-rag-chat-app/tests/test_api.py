"""
Tests for src/api: the chat page and its files, with a content security policy and no inline script; the health
checks; the engine's info; a question answered, with the trace ID in a header and on every log line of the request;
each way a request can fail, answered in the one error shape with the trace ID: a bad question (422), the engine
not built (503), a busy, failing or slow provider (503, 502, 504), the whole question too slow (504), an unknown
address (404) and an error nothing else handled (500), each logged once, without the question's text; and each
request's trace: every stage and line in timeline order, the chunks, the prompt and the tokens, where a failed one
failed, the build's, what isn't kept, and the request's line written before its last bytes go out.
FastAPI's TestClient calls the app directly, so no server is started.
"""
import asyncio
import logging
import re

import pytest
from fakes import ANSWER
from fastapi.testclient import TestClient
from google.genai import errors
from support import change, stand_in_engine

from src.api.app import create_app
from src.api.middleware import TraceMiddleware
from src.config.settings import PROJECT_DIR
from src.exceptions import UpstreamError, UpstreamRateLimitError
from src.observability.tracing import trace_context

TRACE_ID = re.compile(r"[0-9a-f]{16}")


@pytest.fixture
def client(settings, engine):
    with TestClient(create_app(settings, engine)) as test_client:
        yield test_client


def fail_with(engine, monkeypatch, error: Exception):
    """Make every question fail with this error, as the engine would raise it."""
    async def fail(question):
        raise error
    monkeypatch.setattr(engine, "aquery", fail)


# --- The page ---

def test_the_page_is_served_with_a_content_security_policy(client):
    response = client.get("/")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-cache"
    assert '<script src="/static/app.js" defer></script>' in response.text
    assert "<script>" not in response.text and "<style>" not in response.text     # nothing inline: the policy blocks it


def test_the_pages_script_and_styles_are_served(client):
    assert "javascript" in client.get("/static/app.js").headers["content-type"]       # text/ or application/: by OS
    assert client.get("/static/styles.css").headers["content-type"].startswith("text/css")


def test_the_page_calls_the_api_and_shows_its_text_as_text():
    script = (PROJECT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert 'fetch("/api/v1/query"' in script and 'fetch("/api/v1/info")' in script
    assert 'res.headers.get("X-Trace-ID")' in script and "error.trace_id" in script
    assert ".innerHTML" not in script


# --- Health and info ---

def test_live_and_ready(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    assert client.get("/health/ready").json() == {"status": "ready", "chunks": 28}


def test_info_has_the_engines_stats_and_what_the_page_needs(client, settings):
    info = client.get("/api/v1/info").json()
    assert (info["documents"], info["chunks"], info["top_k"], info["max_question_length"]) == (10, 28, 5, 500)
    assert info["sample_questions"] == settings.app.sample_questions
    assert info["request_timeout_seconds"] == settings.api.request_timeout_seconds == 60     # the page waits longer


def test_every_response_has_a_trace_id_and_the_security_headers(client):
    response = client.get("/health/live")
    assert TRACE_ID.fullmatch(response.headers["x-trace-id"])
    assert (response.headers["x-content-type-options"], response.headers["x-frame-options"]) == ("nosniff", "DENY")
    assert client.get("/health/live").headers["x-trace-id"] != response.headers["x-trace-id"]


# --- A question ---

def test_a_question_gets_the_answer_and_its_sources(client):
    response = client.post("/api/v1/query", json={"question": "  My VPN won't connect  "})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == ANSWER
    assert data["sources"][0]["title"] == "VPN Connection Timeout"
    assert set(data["sources"][0]) == {"title", "system", "category", "snippet", "score"}


def test_every_log_line_of_a_request_carries_its_trace_id(client, logs):
    response = client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    trace_id = response.headers["x-trace-id"]
    request_lines = [record for record in logs.records if record.trace_id == trace_id]
    messages = [record.getMessage() for record in request_lines]
    assert messages[0] == "Request started" and messages[-1] == "Request finished"
    for stage in ("embeddings.embed_query ok", "vectordb.search ok", "retrieval.retrieve ok", "llm.generate ok",
                  "pipeline.query ok"):
        assert stage in messages
    finished = request_lines[-1]
    assert (finished.method, finished.path, finished.status_code, finished.levelname) == (
        "POST", "/api/v1/query", 200, "INFO")


def test_the_questions_text_is_not_logged_above_debug(client, logs):
    client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    assert not [record for record in logs.records
                if record.levelno > logging.DEBUG and "VPN won't" in str(vars(record))]


# --- Failures ---

@pytest.mark.parametrize("body, message", [
    ({"question": ""}, "question: String should have at least 1 character"),
    ({"question": "   "}, "question: String should have at least 1 character"),       # only spaces: empty once trimmed
    ({"question": "x" * 501}, "question: String should have at most 500 characters"),
    ({}, "question: Field required"),
    ({"question": "vpn", "user": "me"}, "user: Extra inputs are not permitted"),
], ids=["empty", "blank", "501 characters", "no question", "unknown field"])
def test_a_bad_question_gets_a_422_and_costs_nothing(client, engine, body, message):
    calls_before = list(engine.embedder.model.calls)
    response = client.post("/api/v1/query", json=body)
    error = response.json()["error"]
    assert response.status_code == 422
    assert (error["code"], error["retryable"]) == ("INVALID_REQUEST", False)
    assert error["message"] == f"The request isn't valid: {message}"
    assert error["trace_id"] == response.headers["x-trace-id"]
    assert engine.embedder.model.calls == calls_before         # the question was never embedded


def test_a_body_that_isnt_json_gets_a_422(client):
    response = client.post("/api/v1/query", content=b"not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422 and response.json()["error"]["details"][0]["field"] == "body"


def test_a_body_that_isnt_utf8_gets_a_400_in_the_same_shape(client):
    response = client.post("/api/v1/query", content='{"question": "café"}'.encode("latin-1"),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json()["error"] | {"trace_id": "-"} == {"code": "BAD_REQUEST", "retryable": False,
                                                            "message": "There was an error parsing the body",
                                                            "trace_id": "-"}


def test_an_engine_not_built_is_not_ready(settings):
    with TestClient(create_app(settings, stand_in_engine(settings))) as unbuilt:
        ready, query = unbuilt.get("/health/ready"), unbuilt.post("/api/v1/query", json={"question": "vpn"})
    assert (ready.status_code, ready.json()["error"]["code"]) == (503, "NOT_READY")
    assert (query.status_code, query.json()["error"]["code"]) == (503, "NOT_READY")


def test_a_busy_provider_gets_a_503_and_a_warning_without_a_traceback(client, engine, monkeypatch, logs):
    fail_with(engine, monkeypatch, UpstreamRateLimitError("llm", "GoogleRateLimitError: 429 RESOURCE_EXHAUSTED"))
    response = client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    assert response.status_code == 503
    assert response.json() == {"error": {
        "code": "UPSTREAM_RATE_LIMITED", "message": "The AI service is busy (rate limited). Try again in a minute.",
        "trace_id": response.headers["x-trace-id"], "retryable": True}}
    record = logs.find("Request failed: UPSTREAM_RATE_LIMITED")
    assert (record.levelname, record.exc_info) == ("WARNING", None)
    assert record.error == "llm: GoogleRateLimitError: 429 RESOURCE_EXHAUSTED"     # the detail: in the log only


def test_a_failing_provider_gets_a_502_and_an_error_with_its_traceback(client, engine, monkeypatch, logs):
    fail_with(engine, monkeypatch, UpstreamError("llm", "GoogleInvalidRequestError: 400 API key not valid"))
    response = client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    assert (response.status_code, response.json()["error"]["code"]) == (502, "UPSTREAM_ERROR")
    assert "API key" not in response.text                                          # the detail stays in the log
    record = logs.find("Request failed: UPSTREAM_ERROR")
    assert record.levelname == "ERROR" and record.exc_info is not None


def test_a_question_that_takes_too_long_gets_a_504_and_its_stage_is_cancelled(settings, engine, logs):
    class SlowModel:                       # a chat model that never answers in time
        model = "slow-model"

        async def ainvoke(self, messages):
            await asyncio.sleep(5)

    engine.llm.model = SlowModel()
    fast = change(settings, api={"request_timeout_seconds": 0.2})
    with TestClient(create_app(fast, engine)) as test_client:
        response = test_client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    assert (response.status_code, response.json()["error"]["code"]) == (504, "REQUEST_TIMEOUT")
    assert logs.find("llm.generate cancelled").trace_id == response.headers["x-trace-id"]
    assert logs.find("Request failed: REQUEST_TIMEOUT").error == "No answer within api.request_timeout_seconds (0.2 s)"


def test_an_unknown_address_gets_a_404_in_the_same_shape(client):
    response = client.get("/api/v1/nothing-here")
    assert response.status_code == 404
    assert response.json()["error"] | {"trace_id": "-"} == {"code": "NOT_FOUND", "message": "Not Found",
                                                            "trace_id": "-", "retryable": False}


def test_an_unexpected_error_gets_a_500_without_its_text_and_is_logged_with_its_traceback(client, engine,
                                                                                          monkeypatch, logs):
    fail_with(engine, monkeypatch, KeyError("a bug's details"))
    response = client.post("/api/v1/query", json={"question": "My VPN won't connect"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR" and "bug" not in response.text
    assert TRACE_ID.fullmatch(response.headers["x-trace-id"])
    record = logs.find("Unhandled error")
    assert record.exc_info is not None and record.trace_id == response.headers["x-trace-id"]
    assert logs.find("Request finished").status_code == 500


# --- Traces: what happened behind the scenes ---

@pytest.fixture
def traced(settings, trace_store):
    """An app that keeps traces, on an engine built under a trace of its own, as main.py builds it."""
    engine = stand_in_engine(settings)
    with trace_context() as build_trace_id:
        trace_store.pin(build_trace_id)
        engine.build()
    with TestClient(create_app(settings, engine, trace_store)) as test_client:
        yield test_client


def trace_of(client, response) -> dict:
    """The trace of the request that got this response."""
    return client.get(f"/api/v1/traces/{response.headers['x-trace-id']}").json()


def test_a_questions_trace_holds_every_stage_and_line_in_timeline_order(traced):
    response = traced.post("/api/v1/query", json={"question": "My VPN won't connect"})
    trace = trace_of(traced, response)
    events = trace["events"]
    assert (trace["trace_id"], trace["dropped"]) == (response.headers["x-trace-id"], 0)
    assert [(event["span"], event["depth"]) for event in events if event["span"]] == [
        ("pipeline.query", 0), ("retrieval.retrieve", 1), ("embeddings.embed_query", 2), ("vectordb.search", 2),
        ("prompts.build", 1), ("llm.generate", 1)]
    messages = [event["message"] for event in events]
    assert messages[0] == "Request started" and messages[-1] == "Request finished"
    assert [message for message in messages if message in ("Question", "Prompt", "Answer")] == [
        "Question", "Prompt", "Answer"]
    assert [event["at_ms"] for event in events] == sorted(event["at_ms"] for event in events)
    assert events[-1]["fields"] | {"duration_ms": 0} == {"method": "POST", "path": "/api/v1/query",
                                                         "status_code": 200, "duration_ms": 0}


def test_a_trace_shows_the_chunks_found_the_prompt_and_the_models_tokens(traced):
    events = trace_of(traced, traced.post("/api/v1/query", json={"question": "My VPN won't connect"}))["events"]
    found = [event for event in events if event["message"] == "Chunk found"]
    assert [event["fields"]["rank"] for event in found] == [1, 2, 3, 4, 5]
    assert set(found[0]["fields"]) == {"rank", "chunk", "title", "score", "chunk_id"}
    assert found[0]["fields"]["title"] == "VPN Connection Timeout" and found[0]["depth"] == 2
    prompt = next(event for event in events if event["message"] == "Prompt")["fields"]
    assert [message["role"] for message in prompt["messages"]] == ["system", "human"]
    assert prompt["messages"][1]["content"] == "My VPN won't connect"
    assert "[1] VPN Connection Timeout" in prompt["messages"][0]["content"]
    generate = next(event for event in events if event["span"] == "llm.generate")
    assert {key: generate["fields"][key] for key in ("input_tokens", "output_tokens", "finish_reason")} == {
        "input_tokens": 950, "output_tokens": 12, "finish_reason": "STOP"}
    build = next(event for event in events if event["span"] == "prompts.build")       # filling in the prompt
    assert (build["fields"]["chunks"], build["fields"]["prompt_version"]) == (5, "answer-v1")
    assert build["fields"]["prompt_chars"] == sum(len(message["content"]) for message in prompt["messages"])


def test_a_failed_questions_trace_shows_where_it_failed_and_why(traced, monkeypatch):
    class BusyModel:                       # a chat model whose provider answers 429
        model = "busy-model"

        async def ainvoke(self, messages):
            raise errors.ClientError(429, {"error": {"code": 429, "message": "Quota.", "status": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(traced.app.state.engine.llm, "model", BusyModel())
    response = traced.post("/api/v1/query", json={"question": "My VPN won't connect"})
    events = trace_of(traced, response)["events"]
    assert response.status_code == 503
    failed = {event["span"]: event for event in events if event["span"] and event["status"] == "failed"}
    assert set(failed) == {"llm.generate", "pipeline.query"}
    assert failed["llm.generate"]["fields"]["error_type"] == "UpstreamRateLimitError"
    request_failed = next(event for event in events if event["message"] == "Request failed: UPSTREAM_RATE_LIMITED")
    assert request_failed["fields"]["error"].startswith("llm: ClientError: 429 RESOURCE_EXHAUSTED")
    assert events[-1]["fields"]["status_code"] == 503


def test_the_build_has_its_own_trace_which_info_names(traced):
    info = traced.get("/api/v1/info").json()
    assert info["traces"] is True
    events = traced.get(f"/api/v1/traces/{info['build_trace_id']}").json()["events"]
    assert [(event["span"], event["depth"]) for event in events if event["span"]] == [
        ("pipeline.build", 0), ("ingestion.load", 1), ("chunking.split", 1), ("embeddings.load_vectors", 1),
        ("embeddings.embed_documents", 1), ("vectordb.recreate", 1), ("vectordb.upsert", 1)]
    looked = next(event for event in events if event["span"] == "embeddings.load_vectors")
    assert looked["fields"]["used"] is False                  # nothing saved yet, so the build embedded the chunks


@pytest.mark.parametrize("path", ["/health/live", "/static/app.js", "/"])
def test_the_pages_files_and_the_health_checks_arent_kept(traced, path):
    response = traced.get(path)
    assert traced.get(f"/api/v1/traces/{response.headers['x-trace-id']}").status_code == 404


def test_reading_a_trace_isnt_kept_and_an_unknown_one_is_a_404(traced):
    response = traced.get("/api/v1/traces/0123456789abcdef")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TRACE_NOT_FOUND"
    assert traced.get(f"/api/v1/traces/{response.headers['x-trace-id']}").status_code == 404
    assert traced.get("/api/v1/traces/not.an.id").status_code == 422             # only letters, digits, - and _


def test_without_a_trace_store_info_says_so_and_no_trace_is_served(client):
    assert client.get("/api/v1/info").json()["traces"] is False
    trace_id = client.post("/api/v1/query", json={"question": "vpn"}).headers["x-trace-id"]
    assert client.get(f"/api/v1/traces/{trace_id}").json()["error"]["code"] == "TRACE_NOT_FOUND"


def test_the_request_line_is_written_before_the_last_bytes_go_out(logs):
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part", "more_body": True})
        await send({"type": "http.response.body", "body": b"end"})

    seen = []

    async def send(message):               # notes, for each message, whether the request's line was written yet
        seen.append((message["type"], "Request finished" in logs.messages()))

    asyncio.run(TraceMiddleware(app)({"type": "http", "method": "GET", "path": "/api/v1/info"}, None, send))
    assert seen == [("http.response.start", False), ("http.response.body", False), ("http.response.body", True)]
    assert logs.messages().count("Request finished") == 1


def test_the_page_reads_each_answers_trace_into_its_boxes():
    script = (PROJECT_DIR / "static" / "app.js").read_text(encoding="utf-8")
    assert "fetch(`/api/v1/traces/${encodeURIComponent(traceId)}`)" in script
    assert "info.build_trace_id" in script
    for title in ("The answer", "What went wrong", "Pipeline", "Time per step", "Calls", "Logs",
                  "What the model was given"):
        assert f'"{title}"' in script                  # each box's title
    styles = (PROJECT_DIR / "static" / "styles.css").read_text(encoding="utf-8")
    assert ".boxes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));" in styles   # two per row
    assert "@media (max-width: 960px)" in styles                                                     # one, narrow
