"""Tests for project 12. The plain tests make no model call: the chain's parts, the missing-key message, and the
endpoint streaming from a stand-in (its pieces in order, a failure before the first piece, a failure part-way, a bad
name) and the page. The live test streams one real answer from Gemini and checks it came in more than one piece."""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.output_parsers import StrOutputParser

import main
from hello import MAX_OUTPUT_TOKENS, MODEL, api_key, chain, model, prompt

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent


class StandIn:
    """Takes the chain's place in main.py: streams the given pieces, and can fail at one of them."""

    def __init__(self, pieces, fail_at=None):
        self.pieces = pieces
        self.fail_at = fail_at
        self.called = False

    async def astream(self, inputs):
        self.called = True
        for i, piece in enumerate(self.pieces):
            if i == self.fail_at:
                raise RuntimeError("the connection to Gemini dropped")
            await asyncio.sleep(0)                       # give way, as a real stream does between pieces
            yield piece


def post_and_read(name):
    """POST a name and read the reply as it streams: the status, the content type and the pieces of text."""
    with client.stream("POST", "/api/hello", json={"name": name}) as response:
        return response.status_code, response.headers["content-type"], list(response.iter_text())


# ---- the chain's parts, no call ----

def test_chain_is_prompt_then_model_then_parser():
    assert chain.first is prompt
    assert chain.middle == [model]
    assert isinstance(chain.last, StrOutputParser)


def test_prompt_asks_for_three_paragraphs():
    text = prompt.format(name="Asha")
    assert "for Asha," in text
    assert "three short paragraphs" in text


def test_model_settings():
    assert model.model == MODEL == "gemini-3.5-flash-lite"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 400


def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoint, streaming from a stand-in ----

def test_api_hello_streams_the_pieces_in_order_as_plain_text(monkeypatch):
    monkeypatch.setattr(main, "chain", StandIn(["Welcome", ", Asha", "!"]))
    status, content_type, pieces = post_and_read("Asha")
    assert status == 200
    assert content_type.startswith("text/plain")
    assert "".join(pieces) == "Welcome, Asha!"


def test_streaming_headers_ask_proxies_not_to_buffer(monkeypatch):
    monkeypatch.setattr(main, "chain", StandIn(["Hi"]))
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_a_failure_before_the_first_piece_is_a_502(monkeypatch):
    monkeypatch.setattr(main, "chain", StandIn(["Welcome", ", Asha"], fail_at=0))
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}


def test_a_failure_part_way_keeps_the_text_so_far_and_says_it_stopped(monkeypatch):
    monkeypatch.setattr(main, "chain", StandIn(["Welcome", ", Asha", "!"], fail_at=2))
    status, _, pieces = post_and_read("Asha")
    assert status == 200                                 # already sent with the first piece
    assert "".join(pieces) == "Welcome, Asha" + main.STOPPED


def test_a_bad_name_gets_a_422_and_no_model_call(monkeypatch):
    stand_in = StandIn(["never sent"])
    monkeypatch.setattr(main, "chain", stand_in)
    assert client.post("/api/hello", json={"name": ""}).status_code == 422
    assert stand_in.called is False


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_reads_the_stream_piece_by_piece(path):
    response = client.get(path)
    assert response.status_code == 200
    assert "res.body.getReader()" in response.text
    assert api_key not in response.text


# ---- live: one real streamed answer ----

@pytest.mark.live
def test_live_gemini_streams_the_answer_in_several_pieces():
    start = time.perf_counter()
    first_at = None
    pieces = []
    for piece in chain.stream({"name": "Asha"}):
        if first_at is None:
            first_at = time.perf_counter() - start
        pieces.append(piece)
    total = time.perf_counter() - start

    answer = "".join(pieces)
    assert "Asha" in answer
    assert len(pieces) > 1                               # it came in pieces, not all at once
    assert first_at < total                              # the first piece came before the end
