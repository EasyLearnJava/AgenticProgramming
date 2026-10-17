"""Tests for project 17. The plain tests make no model call: reading the prompt files, their fingerprints (and that
old versions are never edited), the active-version setting, the chains and their trace metadata, the endpoints with
a stand-in, and the page. The live test asks Gemini once with each version and checks every answer is labelled."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

import hello
import main
from prompt_files import PROMPTS, PromptFileError, active_version, fingerprint, load_all, parse

client = TestClient(main.app)
FOLDER = Path(__file__).resolve().parent.parent

# The fingerprint of every version, as it was released. If one of these tests fails, an old version's file was
# edited: put it back, and save the change as a new version (greeting.v4.md) instead.
RELEASED = {"v1": "c3b43ae2", "v2": "89c586b3", "v3": "c27b3feb"}


# ---- the prompt files, no call ----

def test_every_version_is_loaded_in_order():
    assert list(hello.GREETINGS) == ["v1", "v2", "v3"]


@pytest.mark.parametrize("version, released", RELEASED.items())
def test_released_versions_are_never_edited(version, released):
    assert hello.GREETINGS[version].fingerprint == released


def test_each_file_becomes_a_system_and_a_human_message():
    messages = hello.GREETINGS["v3"].template.format_messages(name="Asha")
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]
    assert messages[1].content == "Write a welcome for Asha, in at most two sentences."
    assert "Use no emoji." in messages[0].content          # every line of the section, not only the first


def test_the_note_at_the_top_of_a_file_is_not_part_of_the_prompt():
    assert "#" not in hello.GREETINGS["v2"].system


def test_the_fingerprint_is_the_same_with_windows_line_endings(tmp_path):
    lf = (PROMPTS / "greeting.v2.md").read_text(encoding="utf-8")
    crlf_copy = tmp_path / "greeting.v2.md"
    crlf_copy.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))
    assert parse(crlf_copy, {"name"}).fingerprint == RELEASED["v2"]


def test_changing_one_word_changes_the_fingerprint():
    text = (PROMPTS / "greeting.v2.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert fingerprint(text) == RELEASED["v2"]
    assert fingerprint(text.replace("friendly", "cheerful")) != RELEASED["v2"]


@pytest.mark.parametrize("content, problem", [
    ("## system\nYou write welcomes.\n", "needs a '## system' and a '## human'"),         # no human section
    ("## system\n\n## human\nHi {name}.\n", "needs a '## system' and a '## human'"),     # an empty section
    ("## system\nYou write welcomes.\n## human\nHi {nmae}.\n", "uses ['nmae']"),         # a typo in a variable
])
def test_a_broken_file_is_refused_at_load_time(tmp_path, content, problem):
    path = tmp_path / "greeting.v9.md"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PromptFileError, match=problem.replace("[", r"\[").replace("]", r"\]")):
        parse(path, {"name"})


def test_versions_sort_by_number_so_v10_comes_after_v9(tmp_path, monkeypatch):
    for n in (1, 9, 10, 2):
        (tmp_path / f"greeting.v{n}.md").write_text("## system\nS\n## human\nHi {name}.\n", encoding="utf-8")
    monkeypatch.setattr("prompt_files.PROMPTS", tmp_path)
    assert list(load_all("greeting", {"name"})) == ["v1", "v2", "v9", "v10"]


def test_the_active_version_comes_from_prompt_versions_toml(tmp_path):
    assert active_version("greeting") == hello.ACTIVE == "v3"
    rolled_back = tmp_path / "prompt_versions.toml"
    rolled_back.write_text('greeting = "v2"\n', encoding="utf-8")         # the one-line roll-back
    assert active_version("greeting", rolled_back) == "v2"


# ---- the chains, no call ----

def test_each_chain_carries_its_version_into_the_trace():
    config = hello.chains["v2"].config
    assert config["run_name"] == "greeting.v2"
    assert config["metadata"] == {"prompt": "greeting", "prompt_version": "v2", "prompt_fingerprint": RELEASED["v2"]}


def test_greet_labels_the_answer_with_the_version_that_produced_it(monkeypatch):
    monkeypatch.setitem(hello.chains, "v1", RunnableLambda(lambda inputs: f"Hi {inputs['name']}"))
    assert asyncio.run(hello.greet("Asha", "v1")) == {
        "answer": "Hi Asha", "prompt": "greeting", "version": "v1", "fingerprint": RELEASED["v1"],
    }


def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoints, with stand-ins ----

def stand_in_every_version(monkeypatch):
    for version in hello.GREETINGS:
        monkeypatch.setitem(hello.chains, version, RunnableLambda(lambda inputs, v=version: f"{v}: hi {inputs['name']}"))


def test_api_prompts_lists_every_version_and_the_active_one():
    data = client.get("/api/prompts").json()
    assert data["active"] == "v3"
    assert {v: p["fingerprint"] for v, p in data["versions"].items()} == RELEASED


def test_api_hello_uses_the_active_version_by_default(monkeypatch):
    stand_in_every_version(monkeypatch)
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.json() == {"answer": "v3: hi Asha", "prompt": "greeting", "version": "v3",
                               "fingerprint": RELEASED["v3"]}


def test_api_hello_can_use_an_older_version(monkeypatch):
    stand_in_every_version(monkeypatch)
    assert client.post("/api/hello", json={"name": "Asha", "version": "v1"}).json()["answer"] == "v1: hi Asha"


@pytest.mark.parametrize("body, field", [({"name": ""}, "name"), ({"name": "Asha", "version": "v99"}, "version")])
def test_a_bad_request_gets_a_422_and_no_model_call(monkeypatch, body, field):
    def must_not_run(inputs):
        raise AssertionError("the model was called for a bad request")
    for version in hello.GREETINGS:
        monkeypatch.setitem(hello.chains, version, RunnableLambda(must_not_run))
    response = client.post("/api/hello", json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]


def test_a_failed_model_call_gets_a_502(monkeypatch):
    def fail(inputs):
        raise RuntimeError("no network")
    monkeypatch.setitem(hello.chains, "v3", RunnableLambda(fail))
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="versions"' in response.text
    assert hello.api_key not in response.text


# ---- live: each version once ----

@pytest.mark.live
def test_live_every_version_answers_and_is_labelled():
    for version in hello.GREETINGS:
        result = asyncio.run(hello.greet("Asha", version))
        assert result["answer"].strip()
        assert (result["version"], result["fingerprint"]) == (version, RELEASED[version])
