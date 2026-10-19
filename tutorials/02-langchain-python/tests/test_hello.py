"""
Tests for project 2: the chain itself, running hello.py as a script, the /api/hello endpoint and the page.

    GET /api/hello  ->  200 {"answer": "Hello World, welcome to LangChain!"}

No server is started: FastAPI's TestClient calls the app directly, inside the test run.
Run them:   python -m pytest   ->   7 passed        (add -v for one line per test)
"""
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.prompt_values import StringPromptValue

from hello import chain, prompt, to_text
from main import app

MESSAGE = "Hello World, welcome to LangChain!"
FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def test_chain_returns_the_message_as_a_string():
    answer = chain.invoke({})
    assert answer == MESSAGE
    assert isinstance(answer, str)


def test_prompt_gives_an_object_and_to_text_turns_it_into_text():
    value = prompt.invoke({})
    assert isinstance(value, StringPromptValue)      # an object, not a str yet
    assert to_text.invoke(value) == MESSAGE


def test_running_hello_py_prints_the_message():
    script = FOLDER / "hello.py"
    # sys.executable is the Python running these tests (the venv's), so hello.py gets the same packages.
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == MESSAGE


def test_api_returns_the_answer():
    response = TestClient(app).get("/api/hello")
    assert response.status_code == 200
    assert response.json() == {"answer": MESSAGE}


# parametrize runs this one function once per path, so pytest counts it as two tests.
@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_calls_the_api(path):
    response = TestClient(app).get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"   # the browser asks again before reusing its copy
    assert 'fetch("/api/hello")' in response.text


def test_page_checks_res_ok_and_shows_what_went_wrong():
    # fetch() doesn't fail on an error answer such as a 500, so the page must check res.ok itself.
    page = (FOLDER / "index.html").read_text(encoding="utf-8")
    assert "if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);" in page
    assert "`Something went wrong: ${err.message}`" in page
