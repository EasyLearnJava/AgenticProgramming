"""Tests for project 14. The plain tests make no model call: the format check, that the examples follow their own
format, how the two prompts are built, the model settings, the script and the endpoints with a stand-in for Gemini,
and the page. The live test asks two questions with examples and checks both answers follow the format."""
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI

import main
from hello import (EXAMPLES, LABELS, MAX_OUTPUT_TOKENS, MODEL, QUESTIONS, SYSTEM_PROMPT, api_key, chain,
                   follows_format, model, with_examples, without_examples)

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent

GOOD = "In one line: A list holds items in order.\nExample: [1, 2, 3]\nWatch out: The first item is at index 0."


# ---- the format check, no call ----

@pytest.mark.parametrize("answer", [
    GOOD,
    "\n" + GOOD + "\n",                                            # blank lines around it don't matter
    GOOD.replace("\n", "\n\n"),                                    # nor blank lines between
])
def test_the_format_is_three_labelled_lines(answer):
    assert follows_format(answer)


@pytest.mark.parametrize("answer", [
    "A list holds items in order, like [1, 2, 3].",                                    # free text
    "Example: [1, 2, 3]\nIn one line: A list holds items.\nWatch out: index 0.",       # wrong order
    "In one line: A list holds items.\nExample: [1, 2, 3]",                            # a label missing
    GOOD + "\nAlso: lists can grow.",                                                  # an extra line
    "**In one line:** A list holds items.\n**Example:** [1, 2, 3]\n**Watch out:** 0", # bold labels: not the format
])
def test_anything_else_is_not_the_format(answer):
    assert not follows_format(answer)


def test_every_example_follows_the_format_it_teaches():
    for example in EXAMPLES:
        assert follows_format(example["answer"]), example["question"]


def test_the_system_prompt_does_not_describe_the_format():
    # Otherwise the instructions, not the examples, would be teaching it.
    for label in LABELS:
        assert label.rstrip(":").lower() not in SYSTEM_PROMPT.lower()


def test_no_question_is_one_of_the_examples():
    assert not set(QUESTIONS) & {example["question"] for example in EXAMPLES}
    assert len(QUESTIONS) == 10


# ---- the two prompts and the model, no call ----

def test_without_examples_is_the_system_message_then_the_question():
    messages = without_examples.format_messages(question="What is a list?")
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]


def test_with_examples_puts_each_example_between_the_system_message_and_the_question():
    messages = with_examples.format_messages(question="What is a list?")
    assert [type(m) for m in messages] == [SystemMessage] + [HumanMessage, AIMessage] * len(EXAMPLES) + [HumanMessage]
    assert messages[0].content == SYSTEM_PROMPT
    assert messages[1].content == EXAMPLES[0]["question"]
    assert messages[2].content == EXAMPLES[0]["answer"]
    assert messages[-1].content == "What is a list?"


def test_chain_asks_both_ways():
    assert list(chain.steps__) == ["without", "with"]


def test_model_settings():
    assert model.model == MODEL == "gemini-3.5-flash-lite"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 200


# ---- the script, no call ----

def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


def test_the_script_reports_a_question_gemini_did_not_answer_and_goes_on(monkeypatch, capsys):
    # capsys is a pytest fixture, like monkeypatch: it collects what print() writes, so the test can read it back.
    # A stand-in for Gemini: every model.invoke() runs this instead of calling Google. It refuses one question, and
    # answers in the format only when the prompt holds the examples (the AI messages).
    def stand_in(self, prompt, config=None, **kwargs):
        messages = prompt.to_messages()
        if messages[-1].content == "What is a bug?":
            raise RuntimeError("429 too many requests")
        has_examples = any(isinstance(message, AIMessage) for message in messages)
        return AIMessage(content=GOOD if has_examples else "A list holds items.")

    # The endpoint tests below swap main.chain, but runpy runs hello.py again, and that builds a new model. So the
    # stand-in replaces invoke on the ChatGoogleGenerativeAI class itself, which covers every model, the new one too.
    # That's also why it takes self first: as a method of the class, it's handed the model it was called on.
    monkeypatch.setattr(ChatGoogleGenerativeAI, "invoke", stand_in)
    # runpy runs hello.py the way `python hello.py` does: with __name__ set to "__main__", so its last block runs.
    runpy.run_path(str(FOLDER / "hello.py"), run_name="__main__")
    printed = capsys.readouterr().out
    assert "=== What is a bug?\nGemini didn't answer: RuntimeError: 429 too many requests\n" in printed
    assert printed.endswith("Gemini answered 9 of 10 questions.\n"
                            "without examples: 0 of 9 answers follow the format\n"
                            "with examples: 9 of 9 answers follow the format\n")


# ---- the endpoints, with the chain swapped out so no call is made ----

def test_api_setup_shows_the_system_prompt_examples_and_questions():
    assert client.get("/api/setup").json() == {"system_prompt": SYSTEM_PROMPT, "examples": EXAMPLES,
                                               "questions": QUESTIONS}


def test_api_compare_checks_the_format_of_each_answer(monkeypatch):
    monkeypatch.setattr(main, "chain", RunnableLambda(lambda inputs: {"without": "A list holds items.", "with": GOOD}))
    response = client.post("/api/compare", json={"questions": [" What is a list? ", "What is a string?"]})
    assert response.status_code == 200
    assert response.json() == {"results": [
        {"question": "What is a list?", "without": "A list holds items.", "without_ok": False,
         "with": GOOD, "with_ok": True},
        {"question": "What is a string?", "without": "A list holds items.", "without_ok": False,
         "with": GOOD, "with_ok": True},
    ]}


def test_a_question_gemini_did_not_answer_becomes_an_error_row(monkeypatch):
    def sometimes_fails(inputs):
        if inputs["question"] == "What is a bug?":
            raise RuntimeError("429 too many requests")
        return {"without": "x", "with": GOOD}
    monkeypatch.setattr(main, "chain", RunnableLambda(sometimes_fails))
    response = client.post("/api/compare", json={"questions": ["What is a list?", "What is a bug?"]})
    assert response.status_code == 200
    first, second = response.json()["results"]
    assert first["with_ok"] is True
    assert second == {"question": "What is a bug?", "error": "Gemini didn't answer (RuntimeError)."}


@pytest.mark.parametrize("questions, error_type", [
    ([], "too_short"),
    (["What is a list?"] * 11, "too_long"),
    (["   "], "string_too_short"),
    (["x" * 201], "string_too_long"),
])
def test_a_bad_list_gets_a_422_and_no_model_call(monkeypatch, questions, error_type):
    def must_not_run(inputs):
        raise AssertionError("the model was called for a bad request")
    monkeypatch.setattr(main, "chain", RunnableLambda(must_not_run))
    response = client.post("/api/compare", json={"questions": questions})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="rows"' in response.text
    assert api_key not in response.text


# ---- live: two questions with examples ----

@pytest.mark.live
def test_live_answers_with_examples_follow_the_format():
    with_branch = chain.steps__["with"]                  # just the "with examples" chain: one call per question
    for question in ["What is a list?", "What is a string?"]:
        answer = with_branch.invoke({"question": question})
        assert follows_format(answer), answer
