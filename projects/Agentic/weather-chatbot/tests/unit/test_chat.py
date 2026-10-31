"""
tests/unit/test_chat.py: POST /api/chat: a question gets its answer as server-sent events of HTML, a piece at a time,
then the finished message; a request that breaks a rule gets our own sentence instead; Stop ends the answer, logged as
aborted, however the server tells the app the browser has gone; a failure shows our sentence and its ref, never its own
text; and the question is never logged.
"""

import asyncio
import re
from collections.abc import AsyncIterator, Iterator, MutableMapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from starlette.types import Message, Receive, Scope, Send
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from nimbus import answer, chat
from nimbus.answer import FIXED_ANSWER
from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.constants import CHAT_BODY_MAX_BYTES, ERROR_HEADER, QUESTION_MAX_CHARS
from nimbus.errors import BODY_TOO_LARGE, EMPTY_QUESTION, QUESTION_TOO_LONG, UNEXPECTED, UNREADABLE

VERCEL_ID = "cle1::v9h4q-1793390239541-fa4d33a7af21"
TURN_ID = re.compile(r'id="answer-([0-9a-f]{16})"')
FORM = {"content-type": "application/x-www-form-urlencoded"}


@pytest.fixture(autouse=True)
def no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixed answer without its pause between words, so the tests run fast."""
    monkeypatch.setattr(answer, "WORD_DELAY_SECONDS", 0)


def ask(client: TestClient, question: str) -> str:
    """The whole response to a question, every event in it, as text."""
    response = client.post("/api/chat", data={"question": question})
    assert response.status_code == 200
    return response.text


def events(text: str) -> list[str]:
    """Each server-sent event's data, its lines joined as a browser joins them."""
    datas = []
    for block in text.split("\n\n"):
        lines = [line.removeprefix("data: ") for line in block.split("\n") if line.startswith("data: ")]
        if lines:
            datas.append("\n".join(lines))
    return datas


def turn_id_of(first_event: str) -> str:
    """The turn's id, from the answer's element in the first event."""
    match = TURN_ID.search(first_event)
    assert match is not None
    return match[1]


def test_streams_the_answer_as_server_sent_events_never_cached(client: TestClient) -> None:
    response = client.post("/api/chat", data={"question": "Will it rain in Paris?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in response.headers


def test_the_first_event_shows_the_question_and_nimbus_s_answer_empty_and_busy(client: TestClient) -> None:
    first = events(ask(client, "Will it rain in Paris?"))[0]
    assert '<li class="message message-user">' in first
    assert "<p>Will it rain in Paris?</p>" in first
    turn_id = turn_id_of(first)
    assert f'<li class="message message-bot" id="turn-{turn_id}" aria-busy="true">' in first
    assert f'<p class="answer" id="answer-{turn_id}"></p>' in first


def test_each_piece_goes_into_that_answer_and_together_they_are_the_answer(client: TestClient) -> None:
    datas = events(ask(client, "Will it rain in Paris?"))
    turn_id = turn_id_of(datas[0])
    piece = re.compile(rf'<hx-partial hx-target="#answer-{turn_id}" hx-swap="beforeend">(.*)</hx-partial>', re.S)
    texts = []
    for data in datas[1:-1]:
        match = piece.fullmatch(data.strip())
        assert match is not None, data
        texts.append(match[1])
    assert len(texts) == len(FIXED_ANSWER.split())
    assert "".join(texts) == escape(FIXED_ANSWER)


def test_the_last_event_swaps_in_the_finished_answer_no_longer_busy(client: TestClient) -> None:
    datas = events(ask(client, "Will it rain in Paris?"))
    turn_id = turn_id_of(datas[0])
    last = datas[-1]
    assert last.startswith(f'<hx-partial hx-target="#turn-{turn_id}" hx-swap="outerHTML">')
    assert f'<li class="message message-bot" id="turn-{turn_id}">' in last
    assert f'<p class="answer" id="answer-{turn_id}">{escape(FIXED_ANSWER)}</p>' in last
    assert "aria-busy" not in last


def test_each_turn_gets_its_own_id(client: TestClient) -> None:
    first, second = (turn_id_of(events(ask(client, "Paris?"))[0]) for _ in range(2))
    assert first != second


def test_the_question_is_shown_as_text_never_as_html(client: TestClient) -> None:
    text = ask(client, "<script>alert(1)</script>")
    assert "<script>" not in text
    assert "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>" in text


def test_the_question_is_trimmed(client: TestClient) -> None:
    assert "<p>Paris?</p>" in events(ask(client, "   Paris?  \n"))[0]


def test_a_question_of_the_longest_length_is_answered(client: TestClient) -> None:
    assert ask(client, "a" * QUESTION_MAX_CHARS)


@pytest.mark.parametrize(
    ("body", "headers", "status", "sentence", "code"),
    [
        (b"question=", FORM, 400, EMPTY_QUESTION, "question_empty"),
        (b"question=+++%0A", FORM, 400, EMPTY_QUESTION, "question_empty"),
        (b"", FORM, 400, EMPTY_QUESTION, "question_empty"),
        (b"question=" + b"a" * (QUESTION_MAX_CHARS + 1), FORM, 400, QUESTION_TOO_LONG, "question_too_long"),
        (b"question=a&question=b", FORM, 400, UNREADABLE, "form_unreadable"),
        (b"question=a&lane=x", FORM, 400, UNREADABLE, "form_unreadable"),
        (b"lane=x", FORM, 400, UNREADABLE, "form_unreadable"),
        (b"question=%FF", FORM, 400, UNREADABLE, "form_unreadable"),
        (b'{"question": "a"}', {"content-type": "application/json"}, 415, UNREADABLE, "not_a_form"),
        (b"question=a", {}, 415, UNREADABLE, "not_a_form"),
        (b"question=" + b"a" * CHAT_BODY_MAX_BYTES, FORM, 413, BODY_TOO_LARGE, "body_too_large"),
    ],
    ids=[
        "empty",
        "only-spaces",
        "no-question",
        "too-long",
        "two-questions",
        "a-field-we-dont-know",
        "only-a-field-we-dont-know",
        "not-utf-8",
        "json",
        "no-content-type",
        "body-too-large",
    ],
)
def test_a_request_that_breaks_a_rule_gets_our_sentence_and_no_stream(
    client: TestClient, body: bytes, headers: dict[str, str], status: int, sentence: str, code: str
) -> None:
    with capture_logs() as lines:
        response = client.post("/api/chat", content=body, headers=headers)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers[ERROR_HEADER] == "1"
    assert '<li class="message message-bot message-error">' in response.text
    assert escape(sentence) in response.text
    [line] = [line for line in lines if line["event"] == "chat.rejected"]
    assert line == {"event": "chat.rejected", "code": code, "status": status, "log_level": "info"}


def test_a_question_is_at_most_2000_characters_and_a_body_at_most_32_kib(client: TestClient) -> None:
    # The limits themselves, in numbers: the tests above use the constants, which would follow any change.
    assert client.post("/api/chat", data={"question": "a" * 2000}).status_code == 200
    assert client.post("/api/chat", data={"question": "a" * 2001}).status_code == 400
    assert client.post("/api/chat", content=b"question=" + b"a" * (32 * 1024 - 8), headers=FORM).status_code == 413


def test_the_too_long_sentence_says_how_long_a_question_may_be() -> None:
    assert f"{QUESTION_MAX_CHARS:,}" in QUESTION_TOO_LONG


def test_logs_the_question_s_length_and_the_answer_s_never_their_text(client: TestClient) -> None:
    question = "a private question about my street"
    with capture_logs(processors=[merge_contextvars]) as lines:
        client.post("/api/chat", data={"question": question}, headers={"x-vercel-id": VERCEL_ID})
    [request_line] = [line for line in lines if line["event"] == "chat.request"]
    assert request_line["questionChars"] == len(question)
    assert request_line["requestId"] == VERCEL_ID
    [done] = [line for line in lines if line["event"] == "chat.done"]
    assert done["answerChars"] == len(FIXED_ANSWER)
    assert done["requestId"] == VERCEL_ID
    assert isinstance(done["ms"], int)
    assert "private" not in str(lines)
    assert FIXED_ANSWER.split()[3] not in str(lines)


def test_a_failure_shows_our_sentence_and_its_ref_never_its_own_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fails_halfway() -> AsyncIterator[str]:
        yield "Half an"
        raise RuntimeError("a secret detail")

    monkeypatch.setattr(chat, "stream_fixed_answer", fails_halfway)
    with capture_logs() as lines:
        response = client.post("/api/chat", data={"question": "Paris?"}, headers={"x-vercel-id": VERCEL_ID})
    datas = events(response.text)
    turn_id = turn_id_of(datas[0])
    last = datas[-1]
    assert last.startswith(f'<hx-partial hx-target="#turn-{turn_id}" hx-swap="outerHTML">')
    assert f'<li class="message message-bot message-error" id="turn-{turn_id}">' in last
    assert "Half an" in last
    assert f"{escape(UNEXPECTED)} (ref 33a7af21)" in last
    assert "secret" not in response.text
    [failed] = [line for line in lines if line["event"] == "chat.failed"]
    assert failed["errorClass"] == "RuntimeError"
    assert failed["log_level"] == "error"
    assert "secret" not in str(lines)
    assert not [line for line in lines if line["event"] == "chat.done"]


def _scope(body_length: int, spec_version: str = "2.3") -> Scope:
    """A form posted to /api/chat, as a server hands it to the app, under the given version of ASGI's spec."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec_version},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/chat",
        "raw_path": b"/api/chat",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"content-length", str(body_length).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
    }


def _bodies(sent: list[Message]) -> list[Message]:
    """The body messages sent so far."""
    return [message for message in sent if message["type"] == "http.response.body"]


def _run(scope: Scope, receive: Receive, send: Send) -> list[MutableMapping[str, Any]]:
    """Calls the app as a server would, and gives back the lines it logged."""
    app = create_app(Settings(_env_file=None))  # before capture_logs(): building the app sets logging up afresh
    with capture_logs() as lines:
        asyncio.run(app(scope, receive, send))
    return lines


def _assert_aborted_within_its_request(lines: list[MutableMapping[str, Any]], status: int = 200) -> None:
    """The answer ended as aborted, logged before the request's own line, which is no error."""
    names = [line["event"] for line in lines]
    assert names.index("chat.aborted") < names.index("http.request")
    assert "chat.done" not in names
    assert "chat.failed" not in names
    [request_line] = [line for line in lines if line["event"] == "http.request"]
    assert request_line["status"] == status
    assert request_line["log_level"] == "info"


def test_a_body_too_large_is_refused_from_its_length_alone() -> None:
    sent: list[Message] = []

    async def receive() -> Message:
        raise AssertionError("the body was read")

    async def send(message: Message) -> None:
        sent.append(message)

    _run(_scope(CHAT_BODY_MAX_BYTES + 1), receive, send)
    assert sent[0]["status"] == 413


def test_a_body_too_large_with_no_declared_length_is_refused_as_it_s_read(client: TestClient) -> None:
    chunks = iter([b"question=", b"a" * CHAT_BODY_MAX_BYTES])
    assert client.post("/api/chat", content=chunks, headers=FORM).status_code == 413


def test_a_declared_length_that_isn_t_ascii_digits_is_ignored_not_a_crash() -> None:
    # ASGI 2.4, so Starlette doesn't ask for more messages while it streams: this server would answer each at once.
    body = b"question=Paris%3F"
    sent: list[Message] = []
    scope = _scope(len(body), "2.4")
    scope["headers"] = [(b"content-type", b"application/x-www-form-urlencoded"), (b"content-length", b"\xb2")]

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    _run(scope, receive, send)
    assert sent[0]["status"] == 200


def test_stop_ends_the_answer_and_is_logged_as_aborted_not_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    # ASGI 2.3, as Uvicorn speaks it: Starlette listens for the server's http.disconnect, and cancels the stream.
    monkeypatch.setattr(answer, "WORD_DELAY_SECONDS", 0.01)
    body = b"question=Paris%3F"
    sent: list[Message] = []
    enough_sent = asyncio.Event()
    received = 0

    async def receive() -> Message:
        nonlocal received
        received += 1
        if received == 1:
            return {"type": "http.request", "body": body, "more_body": False}
        await enough_sent.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)
        if len(_bodies(sent)) >= 4:
            enough_sent.set()

    _assert_aborted_within_its_request(_run(_scope(len(body)), receive, send))
    assert len([message for message in _bodies(sent) if message["body"]]) < len(FIXED_ANSWER.split()) + 2


def test_stop_is_logged_the_same_when_the_server_reports_it_as_a_failed_send() -> None:
    # ASGI 2.4: a send to a closed connection raises OSError, and Starlette, relying on that, stops listening for
    # http.disconnect: the failed send becomes ClientDisconnect.
    body = b"question=Paris%3F"
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        if len(_bodies(sent)) >= 4:
            raise OSError("the browser has gone")
        sent.append(message)

    _assert_aborted_within_its_request(_run(_scope(len(body), "2.4"), receive, send))


def test_a_browser_gone_before_the_response_starts_is_logged_the_same_under_asgi_2_4() -> None:
    body = b"question=Paris%3F"

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        raise OSError("the browser has gone")

    _assert_aborted_within_its_request(_run(_scope(len(body), "2.4"), receive, send))


def test_a_browser_gone_before_the_response_starts_is_logged_the_same_under_asgi_2_3() -> None:
    # The disconnect comes at once, so Starlette may cancel the stream before it has sent anything at all.
    body = b"question=Paris%3F"
    received = 0

    async def receive() -> Message:
        nonlocal received
        received += 1
        if received == 1:
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(_message: Message) -> None:
        await asyncio.sleep(0.05)

    _assert_aborted_within_its_request(_run(_scope(len(body)), receive, send))


def test_a_browser_gone_while_sending_its_question_gets_499_and_no_error() -> None:
    sent: list[Message] = []
    messages: Iterator[Message] = iter(
        [
            {"type": "http.request", "body": b"question=Par", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    async def receive() -> Message:
        return next(messages)

    async def send(message: Message) -> None:
        sent.append(message)

    _assert_aborted_within_its_request(_run(_scope(17), receive, send), status=499)
    assert sent[0]["status"] == 499


def test_only_post_is_answered(client: TestClient) -> None:
    assert client.get("/api/chat").status_code == 405
