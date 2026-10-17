"""Tests for project 16. The plain tests make no model call: reading the "Answer:" line, the three ways and their
settings, the report and summary, compare() with stand-ins (its order, its limit of calls at once, a failed call),
the two prompts, the endpoints, and the page. The live tests ask one question three ways, and try the fixed prompt."""
import asyncio
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

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent


def reply(text, output_tokens=10, thinking=0):
    usage = {"input_tokens": 50, "output_tokens": output_tokens, "total_tokens": 50 + output_tokens}
    if thinking:
        usage["output_token_details"] = {"reasoning": thinking}
    return AIMessage(content=text, usage_metadata=usage)


# ---- reading the answer, no call ----

@pytest.mark.parametrize("text, value", [
    ("Answer: 5", 5),
    ("Step 1: 36 apples.\nStep 2: 36 - 12 = 24.\nStep 3: 24 + 7 = 31.\nAnswer: 31", 31),
    ("Answer: 1,250", 1250),
    ("Answer: ₹660", 660),
    ("Answer: 47 days", 47),
    ("First guess. Answer: 10\nChecking again... Answer: 5", 5),     # the last Answer line counts
    ("The ball costs 5 rupees.", None),                              # no Answer line: can't be checked
])
def test_read_answer_takes_the_number_on_the_last_answer_line(text, value):
    assert hello.read_answer(text) == value


# ---- the three ways, no call ----

def test_every_question_has_a_whole_number_answer():
    assert len(hello.QUESTIONS) == 6
    assert all(isinstance(item["answer"], int) for item in hello.QUESTIONS)


def test_direct_and_thinking_share_a_prompt_and_differ_only_in_thinking():
    direct, thinking = hello.WAYS["direct"], hello.WAYS["thinking"]
    assert direct["system"] == thinking["system"]
    assert (direct["thinking_level"], thinking["thinking_level"]) == (None, "high")


def test_step_by_step_asks_for_steps_and_every_way_asks_for_the_answer_line():
    assert "step by step" in hello.WAYS["step_by_step"]["system"]
    assert all(hello.ANSWER_LINE in way["system"] for way in hello.WAYS.values())


def test_only_the_thinking_chain_turns_thinking_up():
    assert hello.chains["thinking"].last.kwargs == {"thinking_level": "high"}
    assert hello.chains["direct"].last is hello.model
    assert hello.chains["step_by_step"].last is hello.model


def test_the_cap_leaves_room_for_steps_and_thinking():
    assert hello.model.max_output_tokens == hello.MAX_OUTPUT_TOKENS == 2000


# ---- the report and the summary, no call ----

def test_report_reads_the_answer_and_its_numbers():
    assert hello.report(reply("Answer: 5", output_tokens=300, thinking=280), expected=5, latency_ms=900) == {
        "text": "Answer: 5", "value": 5, "correct": True,
        "output_tokens": 300, "thinking_tokens": 280, "latency_ms": 900,
    }


def test_a_wrong_or_missing_answer_is_not_correct():
    assert hello.report(reply("Answer: 10"), expected=5, latency_ms=1)["correct"] is False
    assert hello.report(reply("The ball costs 5."), expected=5, latency_ms=1)["correct"] is False


def test_summary_counts_right_answers_and_averages_only_the_calls_that_answered():
    cell = lambda correct, tokens: {"correct": correct, "output_tokens": tokens, "thinking_tokens": 0, "latency_ms": 100}
    rows = [
        {"ways": {"direct": cell(False, 10), "step_by_step": cell(True, 200), "thinking": cell(True, 30)}},
        {"ways": {"direct": cell(True, 20), "step_by_step": cell(True, 100), "thinking": {"error": "..."}}},
    ]
    s = hello.summary(rows)
    assert s["direct"] == {"correct": 1, "answered": 2, "avg_output_tokens": 15, "avg_thinking_tokens": 0,
                           "avg_latency_ms": 100}
    assert s["step_by_step"]["avg_output_tokens"] == 150
    assert (s["thinking"]["correct"], s["thinking"]["answered"]) == (1, 1)


# ---- compare(), with stand-in chains ----

def stand_in_chains(monkeypatch, answer_for, delay=0.0):
    """Replace the three chains with stand-ins; answer_for(way, question) gives the text. Returns the peak number
    of calls that were running at the same time."""
    state = {"running": 0, "peak": 0}

    def make(way):
        async def run(inputs):
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
            await asyncio.sleep(delay)
            state["running"] -= 1
            return reply(answer_for(way, inputs["question"]))
        return RunnableLambda(lambda inputs: None, afunc=run)

    monkeypatch.setattr(hello, "chains", {way: make(way) for way in hello.WAYS})
    return state


def test_compare_asks_every_question_every_way_in_order(monkeypatch):
    answers = {item["question"]: item["answer"] for item in hello.QUESTIONS}
    stand_in_chains(monkeypatch, lambda way, q: "Answer: 0" if way == "direct" else f"Answer: {answers[q]}")
    rows = asyncio.run(hello.compare())
    assert [row["question"] for row in rows] == [item["question"] for item in hello.QUESTIONS]
    assert all(list(row["ways"]) == ["direct", "step_by_step", "thinking"] for row in rows)
    s = hello.summary(rows)
    assert (s["direct"]["correct"], s["step_by_step"]["correct"], s["thinking"]["correct"]) == (0, 6, 6)


def test_compare_never_runs_more_than_at_once_calls(monkeypatch):
    state = stand_in_chains(monkeypatch, lambda way, q: "Answer: 1", delay=0.02)
    asyncio.run(hello.compare())
    assert state["peak"] == hello.AT_ONCE == 4


def test_a_failed_call_becomes_an_error_in_its_own_cell(monkeypatch):
    def answer_for(way, question):
        if way == "thinking":
            raise RuntimeError("429 too many requests")
        return "Answer: 5"
    stand_in_chains(monkeypatch, answer_for)
    first = asyncio.run(hello.compare())[0]
    assert first["ways"]["thinking"]["error"] == "Gemini didn't answer (RuntimeError)."
    assert first["ways"]["direct"]["correct"] is True


# ---- the prompt before and after, no call ----

def test_the_prompt_before_has_the_four_mistakes_and_the_one_after_fixes_them():
    assert "tell me about it" in hello.BEFORE_PROMPT                       # vague goal
    assert "short but explain everything in detail" in hello.BEFORE_PROMPT  # conflicting instructions
    assert "write them a reply too" in hello.BEFORE_PROMPT                  # several tasks
    assert "at most 20 words" in hello.AFTER_PROMPT                         # a clear length
    assert 'starting with "The customer wants"' in hello.AFTER_PROMPT       # an output format
    assert "Do not write a reply" in hello.AFTER_PROMPT                     # one task
    assert len(hello.ANTI_PATTERNS) == 4


def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoints, with stand-ins ----

def test_api_setup_shows_the_questions_ways_and_prompts():
    setup = client.get("/api/setup").json()
    assert setup["questions"] == hello.QUESTIONS
    assert list(setup["ways"]) == ["direct", "step_by_step", "thinking"]
    assert setup["before_prompt"] == hello.BEFORE_PROMPT


def test_api_compare_returns_rows_and_a_summary_without_error_details(monkeypatch):
    def answer_for(way, question):
        if way == "thinking":
            raise RuntimeError("quota exceeded for project 1234")
        return "Answer: 5"
    stand_in_chains(monkeypatch, answer_for)
    data = client.post("/api/compare").json()
    assert len(data["rows"]) == 6
    assert data["rows"][0]["ways"]["thinking"] == {"error": "Gemini didn't answer (RuntimeError)."}   # no detail
    assert data["summary"]["direct"]["answered"] == 6


def test_api_fix_runs_both_prompts(monkeypatch):
    monkeypatch.setattr(hello, "before_chain", RunnableLambda(lambda inputs: "A long, rambling answer..."))
    monkeypatch.setattr(hello, "after_chain", RunnableLambda(lambda inputs: "The customer wants a refund."))
    response = client.post("/api/fix", json={"message": " charged twice "})
    assert response.status_code == 200
    assert response.json() == {"before": "A long, rambling answer...", "after": "The customer wants a refund."}


def test_api_fix_rejects_an_empty_message_and_reports_a_failed_call(monkeypatch):
    assert client.post("/api/fix", json={"message": ""}).status_code == 422

    def fail(inputs):
        raise RuntimeError("no network")
    monkeypatch.setattr(hello, "after_chain", RunnableLambda(fail))
    monkeypatch.setattr(hello, "before_chain", RunnableLambda(lambda inputs: "x"))
    response = client.post("/api/fix", json={"message": "charged twice"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="summary"' in response.text
    assert hello.api_key not in response.text


# ---- live: one question three ways, and the fixed prompt ----

@pytest.mark.live
def test_live_each_way_ends_with_an_answer_line_and_reasoning_costs_more_tokens():
    item = hello.QUESTIONS[0]                                    # the bat and the ball
    cells = {way: hello.report(chain.invoke({"question": item["question"]}), item["answer"], 0)
             for way, chain in hello.chains.items()}
    assert all(cell["value"] is not None for cell in cells.values()), cells
    assert cells["step_by_step"]["output_tokens"] > cells["direct"]["output_tokens"]   # the steps are written out
    assert cells["thinking"]["thinking_tokens"] > 0                                     # the thinking is hidden


@pytest.mark.live
def test_live_the_fixed_prompt_gives_one_short_sentence():
    answer = hello.after_chain.invoke({"message": hello.SAMPLE_MESSAGE}).strip()
    assert answer.startswith("The customer wants")
    assert len(answer.split()) <= 30
