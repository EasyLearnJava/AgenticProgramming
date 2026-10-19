"""Tests for project 11. The plain tests make no model call: the cost sum, reading a reply's numbers, the chain for
one call, ask() with a stand-in model, the settings, the missing-key message, the endpoint's 422s and 502, and the
page. The two live tests call the real Gemini and check the shape of the numbers, not their values (they change
every time)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import hello
import main
from hello import (MAX_OUTPUT_TOKENS, MODEL, PRICE_PER_MILLION_INPUT, PRICE_PER_MILLION_OUTPUT, api_key, ask,
                   chain_for, dollars, estimate_cost, model, prompt, usage_report)

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent


def reply(text="Welcome, Asha!", input_tokens=21, output_tokens=27, thinking=None, finish="STOP"):
    """An AIMessage shaped like Gemini's, built by hand: the text (as a list of content blocks, the way this model
    sends it), the token counts and the finish reason."""
    usage = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens}
    if thinking is not None:
        usage["output_token_details"] = {"reasoning": thinking}
    return AIMessage(content=[{"type": "text", "text": text}], usage_metadata=usage,
                     response_metadata={"finish_reason": finish})


# ---- cost and the report, no call ----

def test_prices_are_per_million_tokens():
    assert (PRICE_PER_MILLION_INPUT, PRICE_PER_MILLION_OUTPUT) == (0.30, 2.50)      # the prices in the README
    # pytest.approx: float sums aren't exact (estimate_cost(21, 27) is 7.379999999999999e-05, not 0.0000738), so
    # costs are compared with a tiny tolerance instead of ==.
    assert estimate_cost(1_000_000, 0) == pytest.approx(0.30)
    assert estimate_cost(0, 1_000_000) == pytest.approx(2.50)


def test_a_typical_call_costs_a_tiny_fraction_of_a_cent():
    # 21 in x $0.30/M + 27 out x $2.50/M = $0.0000063 + $0.0000675
    assert estimate_cost(21, 27) == pytest.approx(0.0000738)


def test_output_tokens_cost_more_than_input_tokens():
    assert estimate_cost(0, 100) > estimate_cost(100, 0)


def test_dollars_shows_7_decimal_places_like_the_page():
    assert dollars(estimate_cost(21, 27)) == "$0.0000738"
    assert dollars(estimate_cost(21, 10)) == "$0.0000313"


def test_the_report_reads_the_numbers_out_of_the_reply():
    assert usage_report(reply(), counted_tokens=20, latency_ms=640) == {
        "answer": "Welcome, Asha!",
        "finish_reason": "STOP",
        "counted_tokens": 20,
        "input_tokens": 21,
        "output_tokens": 27,
        "thinking_tokens": 0,
        "latency_ms": 640,
        "cost_usd": pytest.approx(0.0000738),
    }


def test_thinking_tokens_are_part_of_the_output_and_its_cost():
    report = usage_report(reply(output_tokens=40, thinking=13), counted_tokens=21, latency_ms=1)
    assert report["thinking_tokens"] == 13
    assert report["cost_usd"] == pytest.approx(estimate_cost(21, 40))


def test_a_cut_off_answer_says_max_tokens():
    assert usage_report(reply(finish="MAX_TOKENS"), counted_tokens=21, latency_ms=1)["finish_reason"] == "MAX_TOKENS"


# ---- the model, the chain and ask(), no call ----

def test_model_settings():
    assert model.model == MODEL == "gemini-3.5-flash-lite"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 200


def test_chain_for_caps_this_call_and_leaves_the_model_alone():
    chain = chain_for(10)
    assert chain.first is prompt                              # the prompt, then the model: no parser
    assert chain.last.bound is model                          # bind() wraps the same model: nothing is copied
    assert chain.last.kwargs == {"max_output_tokens": 10}     # sent with every call made through this chain
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS       # the model's own cap hasn't changed


class StandInModel:
    """Takes the model's place in hello.py: counts and answers without calling Gemini, and notes each request in the
    order it happens."""

    def __init__(self):
        self.requests = []

    def get_num_tokens(self, text):
        self.requests.append("count")
        return 21

    def bind(self, max_output_tokens):
        def answer(prompt_value):                             # runs when the chain is invoked: the call itself
            self.requests.append(f"call with a cap of {max_output_tokens}")
            return reply(output_tokens=max_output_tokens, finish="MAX_TOKENS")
        return RunnableLambda(answer)


def test_ask_counts_the_prompt_then_calls_the_model_with_this_calls_cap(monkeypatch):
    stand_in = StandInModel()
    monkeypatch.setattr(hello, "model", stand_in)             # ask() and chain_for() now use the stand-in
    report = ask("Asha", max_output_tokens=10)
    assert stand_in.requests == ["count", "call with a cap of 10"]    # the count first, then the call with this cap
    assert report["counted_tokens"] == 21                     # from get_num_tokens()
    assert report["output_tokens"] == 10
    assert report["finish_reason"] == "MAX_TOKENS"
    assert report["latency_ms"] >= 0


def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoint, with ask() swapped out so no call is made ----

def test_api_hello_passes_the_name_and_limit_and_returns_the_report(monkeypatch):
    seen = {}

    def stand_in(name, max_output_tokens):
        seen.update(name=name, max_output_tokens=max_output_tokens)
        return usage_report(reply(), counted_tokens=21, latency_ms=5)

    monkeypatch.setattr(main, "ask", stand_in)
    response = client.post("/api/hello", json={"name": " Asha ", "max_output_tokens": 50})
    assert response.status_code == 200
    assert seen == {"name": "Asha", "max_output_tokens": 50}
    assert response.json()["output_tokens"] == 27


def test_max_output_tokens_defaults_to_200(monkeypatch):
    seen = {}

    def stand_in(name, max_output_tokens):
        seen["max_output_tokens"] = max_output_tokens
        return usage_report(reply(), counted_tokens=21, latency_ms=5)

    monkeypatch.setattr(main, "ask", stand_in)
    response = client.post("/api/hello", json={"name": "Asha"})        # no max_output_tokens in the body
    assert response.status_code == 200
    assert seen == {"max_output_tokens": 200}


@pytest.mark.parametrize("body, field, error_type", [
    ({"name": ""}, "name", "string_too_short"),
    ({"name": "Asha", "max_output_tokens": 5}, "max_output_tokens", "greater_than_equal"),
    ({"name": "Asha", "max_output_tokens": 500}, "max_output_tokens", "less_than_equal"),
])
def test_bad_input_gets_a_422_and_no_model_call(monkeypatch, body, field, error_type):
    def must_not_run(name, max_output_tokens):
        raise AssertionError("the model was called for a bad request")
    monkeypatch.setattr(main, "ask", must_not_run)
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", field]
    assert problem["type"] == error_type


def test_a_failed_model_call_gets_a_502_without_the_details(monkeypatch):
    def fail(name, max_output_tokens):
        raise RuntimeError("quota exceeded for project 1234")
    monkeypatch.setattr(main, "ask", fail)
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="calls"' in response.text
    assert api_key not in response.text


# ---- live: real calls to Gemini ----

@pytest.mark.live
def test_live_a_call_reports_its_tokens_time_and_cost():
    report = ask("Asha")
    assert "Asha" in report["answer"]
    assert report["finish_reason"] == "STOP"
    assert report["counted_tokens"] > 0
    assert report["input_tokens"] > 0
    assert 0 < report["output_tokens"] <= MAX_OUTPUT_TOKENS
    assert report["latency_ms"] > 0
    assert report["cost_usd"] == pytest.approx(estimate_cost(report["input_tokens"], report["output_tokens"]))


@pytest.mark.live
def test_live_a_low_limit_cuts_the_answer_off():
    report = ask("Asha", max_output_tokens=10)
    assert report["finish_reason"] == "MAX_TOKENS"
    assert report["output_tokens"] <= 10
