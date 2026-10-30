"""
tests/unit/test_middleware.py: what every request goes through: its id, on its log line and its response; one log line
when it ends, without the query string; and the security headers, on every kind of response, a streamed one too.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route
from starlette.types import Message, Receive, Scope, Send
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from nimbus.constants import CONTENT_SECURITY_POLICY, PROJECT_ROOT, SECURITY_HEADERS
from nimbus.middleware import RequestContextMiddleware, SecurityHeadersMiddleware

VERCEL_ID = "cle1::v9h4q-1793390239541-fa4d33a7af21"


@pytest.mark.parametrize("path", ["/", "/docs/step-1", "/nowhere", "/api/health", "/static/app.css"])
def test_every_response_carries_the_security_headers(client: TestClient, path: str) -> None:
    headers = client.get(path).headers
    for name, value in SECURITY_HEADERS:
        assert headers[name] == value


def test_the_cdns_files_get_the_same_security_headers_from_vercel_json() -> None:
    config = json.loads((PROJECT_ROOT / "vercel.json").read_text(encoding="utf-8"))
    [rule] = [rule for rule in config["headers"] if rule["source"] == "/static/(.*)"]
    assert {(header["key"], header["value"]) for header in rule["headers"]} == set(SECURITY_HEADERS)


def test_passes_each_message_of_a_stream_on_by_itself() -> None:
    sent: list[Message] = []

    async def stream_three_chunks(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for chunk in (b"one", b"two", b"three"):
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    app = SecurityHeadersMiddleware(RequestContextMiddleware(stream_three_chunks))
    scope: Scope = {"type": "http", "method": "GET", "path": "/stream", "headers": [], "query_string": b""}
    asyncio.run(app(scope, receive, send))
    assert [message["type"] for message in sent] == ["http.response.start", *["http.response.body"] * 4]
    assert [message["body"] for message in sent[1:4]] == [b"one", b"two", b"three"]
    headers = dict(sent[0]["headers"])
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert b"x-request-id" in headers


def test_the_content_security_policy_is_enforced_and_allows_only_our_own_files() -> None:
    assert ("content-security-policy", CONTENT_SECURITY_POLICY) in SECURITY_HEADERS
    assert "default-src 'self'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert "unsafe" not in CONTENT_SECURITY_POLICY


def test_a_request_from_vercel_keeps_vercels_id(client: TestClient) -> None:
    assert client.get("/", headers={"x-vercel-id": VERCEL_ID}).headers["x-request-id"] == VERCEL_ID


def test_any_other_request_gets_a_new_id(client: TestClient) -> None:
    request_id = client.get("/", headers={"x-vercel-id": "not an id"}).headers["x-request-id"]
    assert len(request_id) == 16


def test_logs_one_line_per_request_with_its_id_and_without_its_query(client: TestClient) -> None:
    # capture_logs replaces every configured step, so the one that adds the request's id is given back.
    with capture_logs(processors=[merge_contextvars]) as lines:
        client.get("/docs?q=a+private+question", headers={"x-vercel-id": VERCEL_ID})
    [line] = [line for line in lines if line["event"] == "http.request"]
    assert line["requestId"] == VERCEL_ID
    assert line["path"] == "/docs"
    assert line["method"] == "GET"
    assert line["status"] == 200
    assert line["log_level"] == "info"
    assert isinstance(line["ms"], int)
    assert "private" not in str(line)


def _app_that_streams_then_fails() -> Starlette:
    """A small app behind both middleware: one route streams three chunks, another fails before it answers."""

    async def chunks() -> AsyncIterator[str]:
        for chunk in ("one ", "two ", "three"):
            yield chunk

    def stream(_request: Request) -> Response:
        return StreamingResponse(chunks(), media_type="text/plain")

    def fail(_request: Request) -> Response:
        raise RuntimeError("boom")

    app = Starlette(routes=[Route("/stream", stream), Route("/fail", fail)])
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


@pytest.fixture
def small_client() -> Iterator[TestClient]:
    with TestClient(_app_that_streams_then_fails(), raise_server_exceptions=False) as test_client:
        yield test_client


def test_a_streamed_response_passes_through_whole_with_its_headers(small_client: TestClient) -> None:
    answer = small_client.get("/stream")
    assert answer.text == "one two three"
    assert answer.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in answer.headers


def test_a_request_that_fails_logs_its_error_class_and_500(small_client: TestClient) -> None:
    with capture_logs() as lines:
        assert small_client.get("/fail").status_code == 500
    [line] = [line for line in lines if line["event"] == "http.request"]
    assert line["status"] == 500
    assert line["errorClass"] == "RuntimeError"
    assert line["log_level"] == "error"
