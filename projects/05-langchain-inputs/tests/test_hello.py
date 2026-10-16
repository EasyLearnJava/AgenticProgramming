"""Tests for project 5: three variables and a partial(), hello.py as a script, POST /api/hello and its
per-field 422s, and the page."""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hello import chain, prompt, prompt_with_default
from main import app

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "hello.py"


def test_prompt_lists_all_three_variables():
    assert prompt.input_variables == ["city", "greeting", "name"]


def test_partial_fills_in_the_greeting_and_leaves_the_original_alone():
    assert prompt_with_default.input_variables == ["city", "name"]
    assert prompt_with_default.partial_variables == {"greeting": "Hello"}
    assert prompt.input_variables == ["city", "greeting", "name"]


def test_chain_uses_the_default_greeting_when_none_is_given():
    assert chain.invoke({"name": "Raghu", "city": "Dallas"}) == "Hello Raghu from Dallas, welcome to LangChain!"


def test_a_greeting_passed_in_replaces_the_default():
    answer = chain.invoke({"greeting": "Good morning", "name": "Raghu", "city": "Dallas"})
    assert answer == "Good morning Raghu from Dallas, welcome to LangChain!"


@pytest.mark.parametrize("args, expected", [
    ([], "Hello Raghu from Dallas, welcome to LangChain!"),
    (["Asha", "Pune"], "Hello Asha from Pune, welcome to LangChain!"),
    (["Asha", "Pune", "Good morning"], "Good morning Asha from Pune, welcome to LangChain!"),
])
def test_running_hello_py_prints_the_greeting(args, expected):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("body, expected", [
    ({"greeting": "Good morning", "name": "Raghu", "city": "Dallas"},
     "Good morning Raghu from Dallas, welcome to LangChain!"),
    ({"greeting": "Namaste", "name": "Asha", "city": "Pune"}, "Namaste Asha from Pune, welcome to LangChain!"),
    ({"name": "Raghu", "city": "Dallas"}, "Hello Raghu from Dallas, welcome to LangChain!"),          # default
    ({"greeting": None, "name": "Raghu", "city": "Dallas"}, "Hello Raghu from Dallas, welcome to LangChain!"),
    ({"name": "  Raghu ", "city": " Dallas  "}, "Hello Raghu from Dallas, welcome to LangChain!"),    # trimmed
])
def test_api_greets_with_every_field(body, expected):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 200
    assert response.json() == {"answer": expected}


@pytest.mark.parametrize("body, field, error_type", [
    ({"greeting": "Hi", "name": "Raghu", "city": "Dallas"}, "greeting", "literal_error"),
    ({"name": "", "city": "Dallas"}, "name", "string_too_short"),
    ({"name": "Raghu", "city": "   "}, "city", "string_too_short"),
    ({"name": "Raghu", "city": "x" * 41}, "city", "string_too_long"),
    ({"name": "Raghu"}, "city", "missing"),
])
def test_api_names_the_bad_field(body, field, error_type):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", field]
    assert problem["type"] == error_type


def test_api_reports_every_bad_field_at_once():
    response = client.post("/api/hello", json={"greeting": "Hi", "name": "", "city": "x" * 41})
    assert response.status_code == 422
    problems = {p["loc"][-1]: p["type"] for p in response.json()["detail"]}
    assert problems == {"greeting": "literal_error", "name": "string_too_short", "city": "string_too_long"}


def test_api_only_answers_post():
    assert client.get("/api/hello").status_code == 405


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_with_all_three_fields(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for field in ["greeting", "name", "city"]:
        assert f'id="{field}"' in response.text
        assert f'id="{field}-error"' in response.text


def test_page_posts_only_on_submit():
    page = SCRIPT.with_name("index.html").read_text(encoding="utf-8")
    assert page.count('fetch("/api/hello"') == 1
    assert page.index('addEventListener("submit"') < page.index('fetch("/api/hello"')
    assert 'method: "POST"' in page
