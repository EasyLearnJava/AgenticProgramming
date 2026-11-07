"""
Tests for api.py, with FastAPI's test client and the stand-ins: a missing or bad key, too many requests, a too-long
question, a too-big body, a store that's down, a slow model, the day's quota and an unexpected error, each with its
status and the one error shape; the request ID; a streamed answer, and a failure before and while it streams;
feedback; a follow-up in a session; the health checks; CORS; one access line per request with nothing of the question
or the key in the logs; and the rate limit holding while many threads ask at once.
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fakes import KeywordEmbeddings, daily_quota
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk
from langchain_core.runnables import RunnableGenerator, RunnableLambda
from qdrant_client import QdrantClient
from support import keyword_retriever, keyword_store

from answering import PROMPT_FILE, Answerer, extractive_stand_in, load_prompt, streaming_stand_in
from api import MAX_QUESTION_CHARS, create_app
from feedback import FeedbackStore
from observability import JsonFormatter, RequestIdFilter
from rag_engine import ConversationMemory, RAGEngine, condense_by_rule
from security import ApiKeys, RateLimiter, key_hash
from settings import ApiSettings
from vector_store import KBVectorStore

PROMPT = load_prompt(PROMPT_FILE)
KEY, OTHER_KEY = "kb_test-key-of-the-tester", "kb_test-key-of-another-caller"     # test values, made up
AUTH, OTHER_AUTH = {"Authorization": f"Bearer {KEY}"}, {"Authorization": f"Bearer {OTHER_KEY}"}
VPN = {"question": "My VPN keeps timing out"}


def stand_in_answerer(**options) -> Answerer:
    options.setdefault("streamer", RunnableGenerator(streaming_stand_in))
    return Answerer(options.pop("llm", RunnableLambda(extractive_stand_in)), prompt=PROMPT, **options)


def make_engine(**options) -> RAGEngine:
    options.setdefault("retriever", keyword_retriever())
    options.setdefault("answerer", stand_in_answerer())
    options.setdefault("store", keyword_store())
    options.setdefault("memory", ConversationMemory())
    return RAGEngine(model_name="fake/stand-in", kb_version="v1", condenser=condense_by_rule, **options)


def client_for(engine: RAGEngine, tmp_path, *, per_minute: int = 1000, **settings) -> TestClient:
    app = create_app(engine, keys=ApiKeys({"tester": key_hash(KEY), "other": key_hash(OTHER_KEY)}),
                     limiter=RateLimiter(per_minute), feedback=FeedbackStore(tmp_path / "feedback.sqlite3"),
                     settings=ApiSettings(**settings))
    return TestClient(app)


@pytest.fixture
def client(tmp_path) -> TestClient:
    return client_for(make_engine(), tmp_path)


def error_of(response, status: int, code: str) -> dict:
    """The response's error, checked: its status, its code, and the request ID of the header."""
    assert response.status_code == status, response.text
    error = response.json()["error"]
    assert error["code"] == code and error["request_id"] == response.headers["X-Request-ID"]
    return error


def events_of(response) -> list[tuple[str, dict]]:
    """The server-sent events of a streamed response: (name, data)."""
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


# -------------------------------------------------
# An Answer, and Who May Ask
# -------------------------------------------------

def test_a_question_is_answered_with_its_sources_and_its_request_id(client):
    response = client.post("/v1/query", json=VPN, headers=AUTH)
    body = response.json()
    assert response.status_code == 200 and body["status"] == "answered" and "UDP" in body["answer"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["sources"][0]["title"] == "VPN Connection Timeout" and body["cached"] is None
    assert (response.headers["X-Content-Type-Options"], response.headers["Cache-Control"]) == ("nosniff", "no-store")


@pytest.mark.parametrize("headers, message", [
    ({}, "An API key is needed"),
    ({"Authorization": "Bearer kb_not-a-key-anyone-has"}, "The API key isn't valid"),
    ({"Authorization": f"Basic {KEY}"}, "An API key is needed"),
], ids=["no key", "a bad key", "another scheme"])
def test_a_missing_or_bad_key_is_refused(client, headers, message):
    response = client.post("/v1/query", json=VPN, headers=headers)
    error = error_of(response, 401, "UNAUTHORIZED")
    assert error["message"].startswith(message) and response.headers["WWW-Authenticate"] == "Bearer"


def test_a_valid_request_id_sent_is_kept_and_any_other_replaced(client):
    kept = client.post("/v1/query", json=VPN, headers={**AUTH, "X-Request-ID": "support-ticket-4711"})
    replaced = client.post("/v1/query", json=VPN, headers={**AUTH, "X-Request-ID": "no spaces <allowed>"})
    assert kept.headers["X-Request-ID"] == kept.json()["request_id"] == "support-ticket-4711"
    assert len(replaced.headers["X-Request-ID"]) == 32


def test_too_many_requests_get_429_and_how_long_to_wait(tmp_path):
    client = client_for(make_engine(), tmp_path, per_minute=2)
    assert [client.post("/v1/query", json=VPN, headers=AUTH).status_code for _ in range(2)] == [200, 200]
    response = client.post("/v1/query", json=VPN, headers=AUTH)
    error = error_of(response, 429, "RATE_LIMITED")
    assert error["retryable"] and 1 <= int(response.headers["Retry-After"]) <= 30
    assert client.post("/v1/query", json=VPN, headers=OTHER_AUTH).status_code == 200      # each caller its own limit


@pytest.mark.parametrize("body, field", [
    ({"question": "x" * (MAX_QUESTION_CHARS + 1)}, "question"),
    ({"question": "   "}, "question"),
    ({"question": "VPN?", "extra": 1}, "extra"),
    ({"question": "VPN?", "session_id": "has spaces"}, "session_id"),
    ({}, "question"),
], ids=["too long", "only spaces", "an unknown field", "a bad session ID", "no question"])
def test_a_request_that_isnt_valid_is_refused_with_each_field(client, body, field):
    error = error_of(client.post("/v1/query", json=body, headers=AUTH), 422, "INVALID_REQUEST")
    assert [detail["field"] for detail in error["details"]] == [field]


def test_a_body_over_the_limit_is_refused_by_its_size_or_as_it_arrives(tmp_path):
    client = client_for(make_engine(), tmp_path, max_body_bytes=1000)
    big = json.dumps({"question": "x" * 2000})
    error_of(client.post("/v1/query", content=big, headers={**AUTH, "Content-Type": "application/json"}), 413,
             "REQUEST_TOO_LARGE")
    pieces = (piece.encode() for piece in [big[:600], big[600:]])        # no Content-Length: counted as it comes
    error_of(client.post("/v1/query", content=pieces, headers={**AUTH, "Content-Type": "application/json"}), 413,
             "REQUEST_TOO_LARGE")


# -------------------------------------------------
# When a Part Fails
# -------------------------------------------------

class BrokenEmbeddings(KeywordEmbeddings):
    def embed_query(self, text):
        raise ConnectionError("the embedding service is down")


def test_a_store_that_is_down_fails_then_stops_being_called(tmp_path):
    client = client_for(make_engine(retriever=keyword_retriever(embeddings=BrokenEmbeddings())), tmp_path)
    for _ in range(3):
        error = error_of(client.post("/v1/query", json=VPN, headers=AUTH), 502, "UPSTREAM_ERROR")
        assert error["retryable"] and "down" not in error["message"]          # the part's own text isn't sent
    response = client.post("/v1/query", json=VPN, headers=AUTH)
    assert "failed 3 times in a row" in error_of(response, 503, "UNAVAILABLE")["message"]
    assert 1 <= int(response.headers["Retry-After"]) <= 30
    ready = client.get("/health/ready")
    assert ready.status_code == 503 and ready.json()["checks"]["vector_store_breaker"] == "open"


def test_a_slow_model_is_cut_off_at_the_deadline(tmp_path):
    slow = RunnableLambda(lambda messages: time.sleep(1.0) or extractive_stand_in(messages))
    # One event loop for the client's life, as a server has: a client made per request waits, as it closes its loop,
    # for the thread the engine left behind
    with client_for(make_engine(answerer=stand_in_answerer(llm=slow), question_timeout_seconds=0.2),
                    tmp_path) as client:
        started = time.perf_counter()
        error_of(client.post("/v1/query", json=VPN, headers=AUTH), 504, "DEADLINE_EXCEEDED")
        assert time.perf_counter() - started < 0.9


def test_the_days_quota_used_up_says_when_it_comes_back(tmp_path):
    def quota(messages):
        raise daily_quota()
    client = client_for(make_engine(answerer=stand_in_answerer(llm=RunnableLambda(quota))), tmp_path)
    error = error_of(client.post("/v1/query", json=VPN, headers=AUTH), 503, "UPSTREAM_DAILY_QUOTA")
    assert error["message"].endswith("Try again after midnight Pacific time.")


def test_an_unexpected_error_is_a_500_without_its_text(tmp_path, caplog):
    def bug(messages):
        raise RuntimeError("an internal detail")
    client = client_for(make_engine(answerer=stand_in_answerer(llm=RunnableLambda(bug))), tmp_path)
    response = client.post("/v1/query", json=VPN, headers=AUTH)
    error = error_of(response, 500, "INTERNAL_ERROR")
    assert "internal detail" not in response.text and "quote the request ID" in error["message"]
    assert any(record.message == "Unhandled error" and record.exc_info for record in caplog.records)


# -------------------------------------------------
# Streaming
# -------------------------------------------------

def test_the_answer_streams_as_its_written_then_the_checked_answer(client):
    with client.stream("POST", "/v1/query/stream", json=VPN, headers=AUTH) as response:
        response.read()
    events = events_of(response)
    assert response.headers["content-type"].startswith("text/event-stream")
    deltas = [data["text"] for name, data in events if name == "delta"]
    (last, answer), = [event for event in events if event[0] != "delta"]
    assert len(deltas) > 2 and last == "answer" and events[-1][0] == "answer"
    assert "".join(deltas) == answer["answer"] and answer["status"] == "answered" and answer["sources"]
    assert answer["request_id"] == response.headers["X-Request-ID"]


def test_a_failure_before_the_stream_starts_gets_its_own_status(tmp_path):
    client = client_for(make_engine(retriever=keyword_retriever(embeddings=BrokenEmbeddings())), tmp_path)
    error_of(client.post("/v1/query/stream", json=VPN, headers=AUTH), 502, "UPSTREAM_ERROR")


def test_a_failure_while_it_streams_is_the_last_event(tmp_path):
    def breaks_off(inputs):
        for _ in inputs:
            yield AIMessageChunk(content='{"answer": "Open UDP ports 500 and 4500 on the firewall, then restart the '
                                         'VPN client, and if it still times out')
            raise ConnectionError("the model went away")
    client = client_for(make_engine(answerer=stand_in_answerer(streamer=RunnableGenerator(breaks_off))), tmp_path)
    with client.stream("POST", "/v1/query/stream", json=VPN, headers=AUTH) as response:
        response.read()
    events = events_of(response)
    assert response.status_code == 200 and [name for name, _ in events] == ["delta", "error"]
    assert events[0][1]["text"].startswith("Open UDP ports") and events[1][1]["error"]["code"] == "UPSTREAM_ERROR"


# -------------------------------------------------
# Feedback, Sessions, Health, CORS, Routes
# -------------------------------------------------

def test_an_answer_can_be_rated_only_by_the_caller_it_was_given_to(client, tmp_path):
    request_id = client.post("/v1/query", json=VPN, headers=AUTH).json()["request_id"]
    rated = client.post("/v1/feedback", json={"request_id": request_id, "rating": "down", "comment": "Not for Mac"},
                        headers=AUTH)
    assert rated.status_code == 200 and rated.json() == {"request_id": request_id, "rating": "down"}
    error_of(client.post("/v1/feedback", json={"request_id": request_id, "rating": "up"}, headers=OTHER_AUTH), 404,
             "NOT_FOUND")
    error_of(client.post("/v1/feedback", json={"request_id": "unknown", "rating": "up"}, headers=AUTH), 404,
             "NOT_FOUND")
    error_of(client.post("/v1/feedback", json={"request_id": request_id, "rating": "meh"}, headers=AUTH), 422,
             "INVALID_REQUEST")
    (row,) = FeedbackStore(tmp_path / "feedback.sqlite3").rated("down")
    assert (row["request_id"], row["comment"], row["caller"]) == (request_id, "Not for Mac", "tester")


def test_a_follow_up_is_read_with_its_own_callers_conversation(client):
    client.post("/v1/query", json={**VPN, "session_id": "s1"}, headers=AUTH)
    follow_up = client.post("/v1/query", json={"question": "and on Mac?", "session_id": "s1"}, headers=AUTH).json()
    stranger = client.post("/v1/query", json={"question": "and on Mac?", "session_id": "s1"},
                           headers=OTHER_AUTH).json()
    assert follow_up["asked"] == "My VPN keeps timing out, and on Mac?" and stranger["asked"] == "and on Mac?"


def test_the_health_checks_need_no_key(client):
    assert client.get("/health/live").json() == {"status": "alive"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200 and ready.json() == {"status": "ready", "checks": {
        "store": "ok", "vector_store_breaker": "closed", "chat_model_breaker": "closed"}}


def test_with_no_knowledge_base_loaded_it_isnt_ready(tmp_path):
    empty = KBVectorStore(QdrantClient(":memory:"), dimensions=KeywordEmbeddings().dimensions)
    client = client_for(make_engine(store=empty), tmp_path)
    ready = client.get("/health/ready")
    assert ready.status_code == 503 and "run python pipeline.py first" in ready.json()["checks"]["store"]
    assert "isn't ready" in error_of(client.post("/v1/query", json=VPN, headers=AUTH), 503, "NOT_READY")["message"]


def test_browsers_may_call_it_only_from_the_pages_named(client):
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
    allowed = client.options("/v1/query", headers={"Origin": "http://localhost:8000", **preflight})
    refused = client.options("/v1/query", headers={"Origin": "https://evil.example", **preflight})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8000"
    assert "access-control-allow-origin" not in refused.headers


def test_an_unknown_route_or_method_gets_the_one_error_shape(client):
    error_of(client.get("/v1/nothing-here"), 404, "NOT_FOUND")
    error_of(client.post("/api/query", json=VPN, headers=AUTH), 404, "NOT_FOUND")       # only /v1 routes
    error_of(client.get("/v1/query", headers=AUTH), 405, "METHOD_NOT_ALLOWED")


def test_the_stats_need_a_key_and_say_what_it_runs_with(client):
    error_of(client.get("/v1/stats"), 401, "UNAUTHORIZED")
    stats = client.get("/v1/stats", headers=AUTH).json()
    assert stats["engine"]["chat_model"] == "fake/stand-in" and stats["engine"]["points"] == 39
    assert stats["feedback"] == {"answers_kept": 0, "rated_up": 0, "rated_down": 0}


# -------------------------------------------------
# The Logs, and the Load
# -------------------------------------------------

def test_one_access_line_per_request_and_nothing_of_the_question_or_the_key(client, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.handler.addFilter(RequestIdFilter())
    question = "Secret project Bluebird: my VPN keeps timing out"
    answered = client.post("/v1/query", json={"question": question}, headers=AUTH)
    client.post("/v1/feedback", json={"request_id": answered.json()["request_id"], "rating": "down",
                                      "comment": "Bluebird again"}, headers=AUTH)
    client.post("/v1/query", json={"question": question}, headers={"Authorization": "Bearer kb_wrong-key"})
    lines = [JsonFormatter().format(record) for record in caplog.records]
    access = [json.loads(line) for line in lines if json.loads(line)["message"].startswith(("GET ", "POST "))]
    assert [(line["path"], line["status"]) for line in access] == [("/v1/query", 200), ("/v1/feedback", 200),
                                                                   ("/v1/query", 401)]
    assert access[0]["request_id"] == answered.headers["X-Request-ID"] and access[0]["caller"] == "tester"
    own = [line for line in lines if json.loads(line)["logger"] == "api"]
    assert access[2]["error_code"] == "UNAUTHORIZED" and len(own) == len(access)       # a refusal: one line, not two
    assert access[0]["answer_status"] == "answered" and set(access[0]["stages_ms"]) == {
        "condense", "cache", "retrieve", "answer"}
    assert all(isinstance(line["ms"], float) for line in access)
    everything = "\n".join(lines)
    assert "Bluebird" not in everything and KEY not in everything and "kb_wrong-key" not in everything


def test_the_rate_limit_holds_while_many_ask_at_once(tmp_path):
    with client_for(make_engine(), tmp_path, per_minute=20) as client:
        with ThreadPoolExecutor(max_workers=10) as pool:
            asked = [pool.submit(client.post, "/v1/query", json=VPN, headers=AUTH) for _ in range(60)]
            started = time.perf_counter()
            live = client.get("/health/live")
            live_seconds = time.perf_counter() - started
        statuses = sorted(future.result().status_code for future in asked)
    assert statuses == [200] * 20 + [429] * 40
    assert live.status_code == 200 and live_seconds < 1.0
