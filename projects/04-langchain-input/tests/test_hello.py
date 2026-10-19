"""
Tests for project 4: the chain with a {name}, hello.py as a script, POST /api/hello and its 422s, and the page.

    POST /api/hello  {"name": "Raghu"}  ->  200 {"answer": "Hello Raghu, welcome to LangChain!"}
    POST /api/hello  {"name": ""}       ->  422, and detail[0].type is "string_too_short"

No server is started: FastAPI's TestClient calls the app directly, and the page tests read index.html as text.
Run them from projects/04-langchain-input:   python -m pytest        (add -v for one line per test)
"""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hello import chain, prompt
from main import app

client = TestClient(app)
FOLDER = Path(__file__).resolve().parent.parent   # the project folder
SCRIPT = FOLDER / "hello.py"
PAGE = FOLDER / "index.html"


def test_prompt_has_one_variable_name():
    assert prompt.input_variables == ["name"]


def test_chain_fills_in_the_name():
    assert chain.invoke({"name": "Raghu"}) == "Hello Raghu, welcome to LangChain!"


def test_chain_without_the_name_fails():
    # pytest.raises passes only if the code inside the with-block raises a KeyError.
    with pytest.raises(KeyError):
        chain.invoke({})


# ids= gives each case a name, which pytest shows in its report: test_running_hello_py_prints_the_greeting[a name].
@pytest.mark.parametrize("args, expected", [
    ([], "Hello World, welcome to LangChain!"),
    (["Raghu"], "Hello Raghu, welcome to LangChain!"),
], ids=["no name", "a name"])
def test_running_hello_py_prints_the_greeting(args, expected):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("name, expected", [
    ("Raghu", "Hello Raghu, welcome to LangChain!"),
    ("  Raghu  ", "Hello Raghu, welcome to LangChain!"),   # spaces around the name are trimmed
    ("x" * 40, f"Hello {'x' * 40}, welcome to LangChain!"),   # 40 characters is the limit, still fine
], ids=["a name", "spaces around it", "40 characters"])
def test_api_greets_the_name(name, expected):
    response = client.post("/api/hello", json={"name": name})
    assert response.status_code == 200
    assert response.json() == {"answer": expected}


@pytest.mark.parametrize("body, error_type", [
    ({"name": ""}, "string_too_short"),
    ({"name": "   "}, "string_too_short"),     # only spaces: empty once trimmed
    ({"name": "x" * 41}, "string_too_long"),
    ({}, "missing"),
], ids=["empty", "only spaces", "41 characters", "no name field"])
def test_api_rejects_a_bad_name_with_422(body, error_type):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type


def test_api_no_longer_answers_get():
    assert client.get("/api/hello").status_code == 405   # Method Not Allowed: it's POST now


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_with_a_name_box(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<input id="name"' in response.text


def test_page_posts_the_name_as_json_only_on_submit():
    page = PAGE.read_text(encoding="utf-8")
    assert page.count('fetch("/api/hello"') == 1
    assert page.index('addEventListener("submit"') < page.index('fetch("/api/hello"')
    assert "event.preventDefault()" in page   # without it the browser reloads the page on every submit
    assert 'method: "POST"' in page
    assert '"Content-Type": "application/json"' in page   # without it FastAPI doesn't read the body as JSON
    assert "JSON.stringify({ name: nameBox.value })" in page


def test_page_puts_errors_into_plain_words():
    page = PAGE.read_text(encoding="utf-8")
    # the two 422 types a typed name can get (see test_api_rejects_a_bad_name_with_422)
    assert 'string_too_short: "Please type a name first."' in page
    assert 'string_too_long: "That name is too long: 40 characters at most."' in page
    # any other error status: the server did answer, so the page says which status it sent
    assert "throw new Error(`the server answered HTTP ${res.status}`)" in page
    assert "Something went wrong: ${err.message}" in page
