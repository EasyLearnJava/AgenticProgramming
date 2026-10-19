"""Tests for project 6: RunnableParallel, RunnablePassthrough and .assign(), that the side-by-side steps really run
at the same time, the whole chain and its graph, hello.py as a script, the two endpoints, and the page."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

from hello import add_shout, chain, side_by_side
from main import app

client = TestClient(app)
FOLDER = Path(__file__).resolve().parent.parent   # the project folder
SCRIPT = FOLDER / "hello.py"
PAGE = FOLDER / "index.html"

RAGHU = {
    "original": "Hello Raghu, welcome to LangChain!",
    "upper": "HELLO RAGHU, WELCOME TO LANGCHAIN!",
    "length": 34,
    "shout": "HELLO RAGHU, WELCOME TO LANGCHAIN!!!",
}


@pytest.mark.parametrize("value", ["abc", 42, {"a": 1}, ["x", "y"]])
def test_passthrough_gives_back_exactly_what_it_gets(value):
    assert RunnablePassthrough().invoke(value) == value


def test_side_by_side_runs_every_step_on_the_same_input():
    assert side_by_side.invoke("abc") == {"original": "abc", "upper": "ABC", "length": 3}


def test_parallel_steps_really_run_at_the_same_time():
    # The real steps finish in microseconds, too fast to tell, so this uses three slow stand-in steps instead.
    def wait_half_a_second(text):
        time.sleep(0.5)
        return text

    three_slow_steps = RunnableParallel(
        a=RunnableLambda(wait_half_a_second),
        b=RunnableLambda(wait_half_a_second),
        c=RunnableLambda(wait_half_a_second),
    )
    start = time.perf_counter()
    assert three_slow_steps.invoke("x") == {"a": "x", "b": "x", "c": "x"}
    assert time.perf_counter() - start < 1.0   # side by side: about 0.5 s. One after another would take 1.5 s


def test_assign_keeps_every_key_and_adds_shout():
    result = add_shout.invoke({"upper": "HI!", "other": 1})
    assert result == {"upper": "HI!", "other": 1, "shout": "HI!!!"}


def test_chain_returns_all_four_results():
    assert chain.invoke({"name": "Raghu"}) == RAGHU


def test_chain_graph_has_a_box_for_every_step():
    graph = chain.get_graph()
    # Each box is named after its step's function (str.upper -> "upper", len -> "len"), not after its dict key.
    box_names = [node.name for node in graph.nodes.values()]
    for step in ["PromptTemplate", "to_text", "upper", "len", "make_shout"]:
        assert step in box_names
    assert box_names.count("Passthrough") == 2   # one in side_by_side, one inside .assign()
    assert "graph TD" in graph.draw_mermaid()


@pytest.mark.parametrize("args, name", [([], "Raghu"), (["Asha"], "Asha")])
def test_running_hello_py_prints_the_results_and_the_graph(args, name):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True)
    results_json, _, graph = result.stdout.partition("\n\n")
    assert json.loads(results_json)["original"] == f"Hello {name}, welcome to LangChain!"
    assert "graph TD" in graph


def test_running_hello_py_prints_a_name_like_jose_as_it_is():
    # A copy of this process's environment, plus PYTHONIOENCODING=utf-8: the script then writes UTF-8 on every
    # computer, so the test can read the é back.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, str(SCRIPT), "José"], capture_output=True, encoding="utf-8", env=env,
                            check=True)
    assert '"original": "Hello José, welcome to LangChain!"' in result.stdout   # not "Hello Jos\u00e9, ..."


def test_api_returns_all_four_results_in_one_answer():
    response = client.post("/api/hello", json={"name": "  Raghu "})
    assert response.status_code == 200
    assert response.json() == RAGHU


@pytest.mark.parametrize("body, error_type", [
    ({"name": ""}, "string_too_short"),
    ({"name": "   "}, "string_too_short"),     # only spaces: empty once trimmed
    ({"name": "x" * 41}, "string_too_long"),
    ({}, "missing"),
])
def test_api_rejects_a_bad_name_with_422(body, error_type):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type


def test_api_only_answers_post():
    assert client.get("/api/hello").status_code == 405   # Method Not Allowed: /api/hello takes POST only


def test_api_graph_returns_the_mermaid_text():
    response = client.get("/api/graph")
    assert response.status_code == 200
    assert response.json() == {"mermaid": chain.get_graph().draw_mermaid()}


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_with_a_cell_for_every_result(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for key in RAGHU:
        assert f'id="{key}"' in response.text


def test_page_posts_the_name_on_submit_and_loads_the_graph():
    page = PAGE.read_text(encoding="utf-8")
    assert page.count('fetch("/api/hello"') == 1
    assert page.index('addEventListener("submit"') < page.index('fetch("/api/hello"')
    assert 'fetch("/api/graph")' in page


def test_page_puts_errors_into_plain_words():
    page = PAGE.read_text(encoding="utf-8")
    # the two 422 types a typed name can get (see test_api_rejects_a_bad_name_with_422)
    assert 'string_too_short: "Please type a name first."' in page
    assert 'string_too_long: "That name is too long: 40 characters at most."' in page
    # any other error status, on either request: the server did answer, so the page says which status it sent
    assert page.count("throw new Error(`the server answered HTTP ${res.status}`)") == 2
    assert page.count("Something went wrong: ${err.message}") == 2
