"""
tests/unit/test_axiom.py: the app's log lines, to Axiom (step 12): the lines waiting, sent as NDJSON, with the token,
into the dataset, each at its own time; a batch Axiom refuses, or can't be reached for, or that takes too long, said on
stderr without the token, and dropped; past the lines that may wait, the rest dropped and counted.
"""

import asyncio
import json

import httpx2
import pytest
from pydantic import SecretStr

from nimbus import axiom
from nimbus.axiom import LogShipper, make_log_shipper, to_ingest_url
from nimbus.config import Settings

TOKEN = "test-axiom-token-5150"  # noqa: S105 - a stand-in, not a token
LINES = ['{"event": "chat.request", "questionChars": 31}', '{"event": "chat.done", "answerChars": 140}']


def shipper_answering(status: int = 200, sent: list[httpx2.Request] | None = None) -> LogShipper:
    """A shipper whose Axiom answers with the status, keeping each request it gets."""

    def answer(request: httpx2.Request) -> httpx2.Response:
        if sent is not None:
            sent.append(request)
        return httpx2.Response(status, json={})

    return LogShipper(
        "weather-chatbot", SecretStr(TOKEN), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(answer))
    )


def reports(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """What the shipper said on stderr, a line each."""
    err = capsys.readouterr().err
    assert TOKEN not in err
    return [json.loads(line) for line in err.splitlines()]


def test_the_ingest_address_names_the_dataset_and_each_line_s_own_time() -> None:
    assert to_ingest_url("weather-chatbot") == (
        "https://us-east-1.aws.edge.axiom.co/v1/ingest/weather-chatbot?timestamp-field=ts"
    )


def test_the_lines_waiting_go_in_one_request_as_ndjson_with_the_token(capsys: pytest.CaptureFixture[str]) -> None:
    sent: list[httpx2.Request] = []
    shipper = shipper_answering(sent=sent)
    for line in LINES:
        shipper.write(line)
    asyncio.run(shipper.send())
    [request] = sent
    assert str(request.url) == to_ingest_url("weather-chatbot")
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["content-type"] == "application/x-ndjson"
    assert request.content.decode() == LINES[0] + "\n" + LINES[1] + "\n"
    # Sent once: the next send has nothing to send, and sends nothing.
    asyncio.run(shipper.send())
    assert len(sent) == 1
    assert reports(capsys) == []


def test_a_batch_axiom_refuses_is_said_by_its_status_and_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    shipper = shipper_answering(403)
    for line in LINES:
        shipper.write(line)
    asyncio.run(shipper.send())
    assert reports(capsys) == [{"level": "warning", "event": "axiom.failed", "httpStatus": 403, "lines": 2}]


def test_a_batch_that_can_t_reach_axiom_is_said_by_its_class(capsys: pytest.CaptureFixture[str]) -> None:
    def unreachable(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host", request=request)

    shipper = LogShipper(
        "weather-chatbot", SecretStr(TOKEN), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(unreachable))
    )
    shipper.write(LINES[0])
    asyncio.run(shipper.send())
    assert reports(capsys) == [{"level": "warning", "event": "axiom.failed", "reason": "ConnectError", "lines": 1}]


def test_a_batch_has_its_time_and_no_more(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(axiom, "AXIOM_SEND_SECONDS", 0.05)

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(5)
        return httpx2.Response(200)

    shipper = LogShipper(
        "weather-chatbot", SecretStr(TOKEN), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(slow))
    )
    shipper.write(LINES[0])
    asyncio.run(shipper.send())
    assert reports(capsys) == [{"level": "warning", "event": "axiom.failed", "reason": "TimeoutError", "lines": 1}]


def test_past_the_lines_that_may_wait_the_rest_are_dropped_and_counted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(axiom, "AXIOM_MAX_WAITING_LINES", 1)
    sent: list[httpx2.Request] = []
    shipper = shipper_answering(sent=sent)
    for line in LINES:
        shipper.write(line)
    asyncio.run(shipper.send())
    assert sent[0].content.decode() == LINES[0] + "\n"
    assert reports(capsys) == [{"level": "warning", "event": "axiom.dropped", "lines": 1}]


def test_axiom_needs_both_its_token_and_its_dataset() -> None:
    assert make_log_shipper(Settings(_env_file=None, axiom_token=SecretStr(TOKEN))) is None
    assert make_log_shipper(Settings(_env_file=None, axiom_dataset="weather-chatbot")) is None
    shipper = make_log_shipper(Settings(_env_file=None, axiom_token=SecretStr(TOKEN), axiom_dataset="weather-chatbot"))
    assert shipper is not None
    assert shipper.url == to_ingest_url("weather-chatbot")
