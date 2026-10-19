"""Tests for project 10. The plain tests make no model call: the prompt, the model's settings, the parser, the
missing-key message, the endpoint's 422 and 502 (with the reason in the server's log), and the page. The live test
calls the real Gemini once and checks the shape of the answer, not its words (it changes every time)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import main
from hello import MAX_OUTPUT_TOKENS, MODEL, api_key, chain, model, parser, prompt

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent


# ---- the chain's parts, no call ----

def test_prompt_puts_the_name_into_the_instruction():
    text = prompt.invoke({"name": "Asha"}).to_string()
    assert text == "Write a short, friendly welcome for Asha, who is starting to learn LangChain. One or two sentences."


def test_chain_is_prompt_then_model_then_parser():
    assert chain.first is prompt
    assert chain.middle == [model]
    assert chain.last is parser


def test_model_settings():
    assert model.model == MODEL == "gemini-3.5-flash-lite"
    assert model.max_output_tokens == MAX_OUTPUT_TOKENS == 200


def test_the_model_hides_the_key():
    assert repr(model.google_api_key) == "SecretStr('**********')"
    assert api_key not in repr(model)


def test_parser_keeps_only_the_text_of_the_reply():
    assert parser.invoke(AIMessage(content="Welcome, Asha!")) == "Welcome, Asha!"


# ---- no key: the script and the server stop with a message ----

@pytest.mark.parametrize("script_args", [["hello.py"], ["-m", "uvicorn", "main:app", "--port", "8596"]],
                         ids=["python hello.py", "uvicorn main:app"])
def test_with_no_key_it_stops_with_the_message_not_a_stack_trace(script_args):
    # A copy of this process's environment, with GOOGLE_API_KEY set to "". An empty key also stops .env from being
    # used: load_dotenv() never overwrites a variable that is already set.
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, *script_args], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoint, with the chain swapped out so no call is made ----

def test_api_hello_returns_the_chains_answer(monkeypatch):
    monkeypatch.setattr(main, "chain", RunnableLambda(lambda inputs: f"Welcome, {inputs['name']}!"))
    response = client.post("/api/hello", json={"name": " Asha "})
    assert response.status_code == 200
    assert response.json() == {"answer": "Welcome, Asha!"}


# The page shows each problem in a 422 as "<the last part of loc>: <msg>", here "name: String should have ...".
@pytest.mark.parametrize("name, message", [
    ("", "String should have at least 1 character"),
    ("x" * 41, "String should have at most 40 characters"),
], ids=["empty", "41 characters"])
def test_a_bad_name_gets_a_422_and_no_model_call(monkeypatch, name, message):
    calls = []                                    # the stand-in chain writes down every input it gets

    def stand_in(inputs):
        calls.append(inputs)
        return "Welcome!"

    monkeypatch.setattr(main, "chain", RunnableLambda(stand_in))
    response = client.post("/api/hello", json={"name": name})
    assert response.status_code == 422
    problem = response.json()["detail"][0]
    assert problem["loc"] == ["body", "name"]
    assert problem["msg"] == message
    assert calls == []                            # the chain never ran: a bad name costs nothing


def test_a_failed_model_call_gets_a_502_without_the_details(monkeypatch, caplog):
    def fail(inputs):
        raise RuntimeError("quota exceeded for project 1234")
    monkeypatch.setattr(main, "chain", RunnableLambda(fail))
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}
    # caplog is a pytest fixture that collects what the code logs: the full reason is in the server's log.
    assert "quota exceeded for project 1234" in caplog.text


def test_api_hello_only_answers_post():
    assert client.get("/api/hello").status_code == 405


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'fetch("/api/hello"' in response.text
    assert api_key not in response.text


# ---- live: one real call to Gemini ----

@pytest.mark.live
def test_live_gemini_writes_a_short_welcome_for_the_name():
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 200
    answer = response.json()["answer"]
    assert isinstance(answer, str)
    assert 0 < len(answer) < 1000       # some text, and short: max_output_tokens caps it
    assert "Asha" in answer             # the name reached the model
    assert api_key not in answer
