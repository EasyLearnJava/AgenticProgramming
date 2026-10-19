"""
Tests for project 3: the chain, running hello.py as a script, the /api/hello endpoint and the button page.

    GET /api/hello  ->  200 {"answer": "Hello World, welcome to LangChain!"}

No browser runs here: the page tests read index.html as text. Run them from tutorials/03-langchain-button:
    python -m pytest
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
PAGE = FOLDER / "index.html"


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
def test_page_is_served_with_a_button(path):
    response = TestClient(app).get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<button id="run">' in response.text


def test_page_calls_the_api_only_inside_the_click_handler():
    # The page's only fetch must come after the click listener. Project 2's sat at the top of the script,
    # so it ran as soon as the page opened.
    page = PAGE.read_text(encoding="utf-8")
    assert page.count('fetch("/api/hello"') == 1
    assert page.index('addEventListener("click"') < page.index('fetch("/api/hello"')


def test_page_checks_res_ok_and_always_turns_the_button_back_on():
    # fetch doesn't fail on a 404 or a 500 (the server did answer), so the page checks res.ok and says what happened.
    page = PAGE.read_text(encoding="utf-8")
    assert "if (!res.ok) throw new Error(`the server answered HTTP ${res.status}`);" in page
    assert "answer.textContent = `Something went wrong: ${err.message}`;" in page
    # finally runs after success and failure alike, so the button comes back even after an error.
    assert page.index("} finally {") < page.index("button.disabled = false")
