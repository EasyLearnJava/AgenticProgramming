"""Tests for project 7: RunnableBranch's paths, batch() and max_concurrency, the plain-if version, hello.py as a
script, the two endpoints and their 422s, and the page."""
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from hello import casual_chain, chain, formal_chain, greet_with_if, is_formal
from main import app

client = TestClient(app)
FOLDER = Path(__file__).resolve().parent.parent   # the project folder
SCRIPT = FOLDER / "hello.py"
PAGE = FOLDER / "index.html"

FIVE = [
    {"name": "Raghu", "style": "formal"},
    {"name": "Asha", "style": "casual"},
    {"name": "Ken", "style": "formal"},
    {"name": "Mia", "style": "casual"},
    {"name": "Li", "style": "casual"},
]
FIVE_ANSWERS = [
    "Good day, Raghu. Welcome to LangChain.",
    "Hey Asha! Welcome to LangChain!",
    "Good day, Ken. Welcome to LangChain.",
    "Hey Mia! Welcome to LangChain!",
    "Hey Li! Welcome to LangChain!",
]


def test_is_formal_reads_the_style():
    assert is_formal({"name": "Raghu", "style": "formal"}) is True
    assert is_formal({"name": "Raghu", "style": "casual"}) is False


def test_each_path_on_its_own():
    assert formal_chain.invoke({"name": "Raghu"}) == "Good day, Raghu. Welcome to LangChain."
    assert casual_chain.invoke({"name": "Raghu"}) == "Hey Raghu! Welcome to LangChain!"


@pytest.mark.parametrize("style, expected", [
    ("formal", "Good day, Raghu. Welcome to LangChain."),
    ("casual", "Hey Raghu! Welcome to LangChain!"),
    ("loud", "Hey Raghu! Welcome to LangChain!"),   # no condition is true -> the default path
])
def test_branch_picks_the_path_from_the_style(style, expected):
    assert chain.invoke({"name": "Raghu", "style": style}) == expected


@pytest.mark.parametrize("person", FIVE)
def test_plain_if_gives_the_same_text(person):
    assert greet_with_if(person) == chain.invoke(person)


def test_batch_returns_one_answer_per_input_in_order():
    assert chain.batch(FIVE, config={"max_concurrency": 3}) == FIVE_ANSWERS


def test_max_concurrency_caps_how_many_run_at_once():
    # The greetings finish in microseconds, too fast to overlap, so this batches a slow stand-in step instead.
    # batch() runs slow() on several threads at once: `running` counts how many are inside it right now,
    # and `most` keeps the highest count seen.
    running, most = 0, 0
    lock = threading.Lock()                 # so two threads never change the counts at the same moment

    def slow(x):
        nonlocal running, most              # change the test's two variables, not new ones local to slow()
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.05)                    # long enough for the other threads to start meanwhile
        with lock:
            running -= 1
        return x

    assert RunnableLambda(slow).batch(list(range(8)), config={"max_concurrency": 3}) == list(range(8))
    assert most == 3                        # three at once: the cap was reached, and never passed


@pytest.mark.parametrize("args, expected_lines", [
    ([], ["Good day, Raghu. Welcome to LangChain.", "Hey Raghu! Welcome to LangChain!", "", *FIVE_ANSWERS]),
    (["Asha"], ["Good day, Asha. Welcome to LangChain.", "Hey Asha! Welcome to LangChain!", "", *FIVE_ANSWERS]),
    (["Asha", "formal"], ["Good day, Asha. Welcome to LangChain."]),
], ids=["no arguments", "a name", "a name and a style"])
def test_running_hello_py_prints_the_greetings(args, expected_lines):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True)
    assert result.stdout.strip().splitlines() == expected_lines


@pytest.mark.parametrize("style, expected", [
    ("formal", "Good day, Raghu. Welcome to LangChain."),
    ("casual", "Hey Raghu! Welcome to LangChain!"),
])
def test_api_hello_greets_in_the_chosen_style(style, expected):
    response = client.post("/api/hello", json={"name": " Raghu ", "style": style})
    assert response.status_code == 200
    assert response.json() == {"answer": expected}


@pytest.mark.parametrize("body, field, error_type", [
    ({"name": "Raghu", "style": "loud"}, "style", "literal_error"),   # the server only allows the two styles
    ({"name": "Raghu", "style": " formal "}, "style", "literal_error"),   # exactly: a Literal isn't stripped
    ({"name": "Raghu"}, "style", "missing"),
    ({"name": "", "style": "formal"}, "name", "string_too_short"),
    ({"name": "   ", "style": "formal"}, "name", "string_too_short"),   # only spaces: empty once stripped
    ({"name": "x" * 41, "style": "formal"}, "name", "string_too_long"),
], ids=["unknown style", "style with spaces", "no style", "empty name", "blank name", "41-character name"])
def test_api_hello_rejects_a_bad_field(body, field, error_type):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    [problem] = response.json()["detail"]   # unpacking into [problem] also checks there is exactly one error
    assert problem["loc"] == ["body", field]
    assert problem["type"] == error_type


def test_api_batch_greets_five_people_in_one_call():
    response = client.post("/api/batch", json={"people": FIVE})
    assert response.status_code == 200
    assert response.json() == {"answers": FIVE_ANSWERS}


@pytest.mark.parametrize("people, error_type", [
    ([], "too_short"),
    ([{"name": "Raghu", "style": "casual"}] * 11, "too_long"),
])
def test_api_batch_limits_the_list(people, error_type):
    response = client.post("/api/batch", json={"people": people})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type


def test_api_batch_says_which_person_and_field_is_bad():
    people = [{"name": "Raghu", "style": "formal"}, {"name": "Asha", "style": "loud"}]
    response = client.post("/api/batch", json={"people": people})
    assert response.status_code == 422
    [problem] = response.json()["detail"]
    assert problem["loc"] == ["body", "people", 1, "style"]


@pytest.mark.parametrize("path", ["/api/hello", "/api/batch"])
def test_api_only_answers_post(path):
    assert client.get(path).status_code == 405


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_with_both_forms(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="one-form"' in response.text
    assert 'id="batch-form"' in response.text


def test_page_posts_only_from_the_submit_handlers():
    page = PAGE.read_text(encoding="utf-8")
    assert page.count("fetch(") == 1   # every request goes through post()
    assert page.count('post("/api/hello"') == 1
    assert page.count('post("/api/batch"') == 1
    first_submit = page.index('addEventListener("submit"')
    assert page.index('post("/api/hello"') > first_submit
    assert page.index('post("/api/batch"') > first_submit


def test_page_names_the_bad_person_and_shows_other_errors():
    page = PAGE.read_text(encoding="utf-8")
    # a 422 for loc ["body", "people", 1, "style"] says "Person 2, style: ...": counted by person, so a blank line
    # in the box doesn't shift the number
    assert "`Person ${p.loc[2] + 1}, ${p.loc[3]}: `" in page
    # any other error status: the server did answer, so the page says which status it sent
    assert "throw new Error(`the server answered HTTP ${res.status}`)" in page
    assert page.count("Something went wrong: ${err.message}") == 2   # one in each form's catch
