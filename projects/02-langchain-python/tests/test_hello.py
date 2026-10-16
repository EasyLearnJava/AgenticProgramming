"""Tests for project 2: the chain itself, running hello.py as a script, the /api/hello endpoint and the page."""
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from hello import chain, prompt, to_text
from main import app

MESSAGE = "Hello World, welcome to LangChain!"


def test_chain_returns_the_message_as_a_string():
    answer = chain.invoke({})
    assert answer == MESSAGE
    assert isinstance(answer, str)


def test_prompt_gives_an_object_and_to_text_turns_it_into_text():
    value = prompt.invoke({})
    assert type(value).__name__ == "StringPromptValue"
    assert to_text.invoke(value) == MESSAGE


def test_running_hello_py_prints_the_message():
    script = Path(__file__).resolve().parent.parent / "hello.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == MESSAGE


def test_api_returns_the_answer():
    response = TestClient(app).get("/api/hello")
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == MESSAGE
    assert body["server_ms"] >= 0
    assert body["python"].startswith("3.")


def test_page_is_served_and_calls_the_api():
    response = TestClient(app).get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'fetch("/api/hello")' in response.text
