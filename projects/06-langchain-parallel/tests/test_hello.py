"""Tests for project 6: RunnableParallel, RunnablePassthrough and .assign(), the whole chain and its graph,
hello.py as a script, the two endpoints, and the page."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.runnables import RunnablePassthrough

from hello import add_shout, chain, side_by_side
from main import app

client = TestClient(app)
SCRIPT = Path(__file__).resolve().parent.parent / "hello.py"

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


def test_assign_keeps_every_key_and_adds_shout():
    result = add_shout.invoke({"upper": "HI!", "other": 1})
    assert result == {"upper": "HI!", "other": 1, "shout": "HI!!!"}


def test_chain_returns_all_four_results():
    assert chain.invoke({"name": "Raghu"}) == RAGHU


def test_chain_graph_shows_the_parallel_steps():
    mermaid = chain.get_graph().draw_mermaid()
    assert "graph TD" in mermaid
    for step in ["PromptTemplate", "to_text", "Passthrough", "upper", "len", "shout"]:
        assert step in mermaid


@pytest.mark.parametrize("args, name", [([], "Raghu"), (["Asha"], "Asha")])
def test_running_hello_py_prints_the_results_and_the_graph(args, name):
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True)
    results_json, _, graph = result.stdout.partition("\n\n")
    assert json.loads(results_json)["original"] == f"Hello {name}, welcome to LangChain!"
    assert "graph TD" in graph


def test_api_returns_all_four_results_in_one_answer():
    response = client.post("/api/hello", json={"name": "  Raghu "})
    assert response.status_code == 200
    assert response.json() == RAGHU


@pytest.mark.parametrize("body, error_type", [
    ({"name": ""}, "string_too_short"),
    ({"name": "x" * 41}, "string_too_long"),
    ({}, "missing"),
])
def test_api_rejects_a_bad_name_with_422(body, error_type):
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == error_type


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
    page = SCRIPT.with_name("index.html").read_text(encoding="utf-8")
    assert page.count('fetch("/api/hello"') == 1
    assert page.index('addEventListener("submit"') < page.index('fetch("/api/hello"')
    assert 'fetch("/api/graph")' in page
