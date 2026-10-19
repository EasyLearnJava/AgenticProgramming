"""Tests for project 17. The plain tests make no model call: reading and checking the prompt files, their
fingerprints (and that released versions are never edited), the active-version setting, the model's settings, the
chains and their trace labels, the start-up messages, the endpoints with stand-ins, and the page. The live test
sends each version to Gemini once and checks that each one gets an answer.

No test assumes that "v3" is the active version: they take it from prompt_versions.toml (through hello.ACTIVE), so
they still pass after a roll-back, or when you add a new version and release it."""
import asyncio
import os
import re
import shutil
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

# The fingerprint of every released version. A released file never changes: if one of these fails, that file was
# edited. Put it back, and save the change as a new version (greeting.v4.md) instead. A new file is a draft until
# you release it (make it the active version): then add its fingerprint here, so it's guarded too.
RELEASED = {"v1": "c3b43ae2", "v2": "89c586b3", "v3": "c27b3feb"}


# ---- the prompt files, no call ----

def test_every_released_version_is_loaded_in_order():
    assert list(hello.GREETINGS)[:len(RELEASED)] == list(RELEASED)     # v1, v2, v3; a new greeting.v4.md comes after


@pytest.mark.parametrize("version, released", RELEASED.items())
def test_released_versions_are_never_edited(version, released):
    assert hello.GREETINGS[version].fingerprint == released


def test_each_file_becomes_a_system_and_a_human_message(tmp_path):
    # A small file of its own, not greeting.v3.md: RELEASED is the one place that pins what the released files say.
    path = tmp_path / "greeting.v9.md"
    path.write_text("# a note\n\n## system\nLine one.\nLine two.\n\n## human\nHi {name}.\n", encoding="utf-8")
    messages = parse(path, {"name"}).template.format_messages(name="Asha")
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]
    assert messages[0].content == "Line one.\nLine two."      # every line of the section, not only the first
    assert messages[1].content == "Hi Asha."


def test_the_note_at_the_top_of_a_file_is_not_part_of_the_prompt():
    assert "#" not in hello.GREETINGS["v2"].system


def test_the_fingerprint_is_the_same_with_windows_line_endings(tmp_path):
    lf = (PROMPTS / "greeting.v2.md").read_text(encoding="utf-8")
    crlf_copy = tmp_path / "greeting.v2.md"
    crlf_copy.write_bytes(lf.replace("\n", "\r\n").encode("utf-8"))
    assert parse(crlf_copy, {"name"}).fingerprint == hello.GREETINGS["v2"].fingerprint


def test_changing_one_word_changes_the_fingerprint():
    line = "You write short, friendly welcomes for people who are starting to learn LangChain."
    assert fingerprint(line.replace("friendly", "cheerful")) != fingerprint(line)


@pytest.mark.parametrize("content, problem", [
    ("## system\nYou write welcomes.\n", "needs a '## system' and a '## human'"),         # no human section
    ("## system\n\n## human\nHi {name}.\n", "needs a '## system' and a '## human'"),     # an empty section
    ("## system\nA.\n## human\nHi {name}.\n## system\nB.\n", "needs a '## system' and a '## human'"),   # two systems
    ("## system\nYou write welcomes.\n## human\nHi {nmae}.\n", "uses ['nmae']"),         # a typo in a variable
    ("## system\nYou write welcomes.\n## human\nHi {name.\n", "has braces that don't make a variable"),   # no closing }
])
def test_a_broken_file_is_refused_at_load_time(tmp_path, content, problem):
    path = tmp_path / "greeting.v9.md"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PromptFileError, match=re.escape(problem)):     # re.escape: match the [ and ] as written
        parse(path, {"name"})


def test_versions_sort_by_number_so_v10_comes_after_v9(tmp_path, monkeypatch):
    for n in (1, 9, 10, 2):
        (tmp_path / f"greeting.v{n}.md").write_text("## system\nS\n## human\nHi {name}.\n", encoding="utf-8")
    monkeypatch.setattr("prompt_files.PROMPTS", tmp_path)
    assert list(load_all("greeting", {"name"})) == ["v1", "v2", "v9", "v10"]


def test_a_file_not_named_like_a_version_is_refused(tmp_path, monkeypatch):
    # The copy Windows Explorer makes of greeting.v3.md: it matches greeting.v*.md, but "3 - Copy" isn't a number.
    (tmp_path / "greeting.v3 - Copy.md").write_text("## system\nS\n## human\nHi {name}.\n", encoding="utf-8")
    monkeypatch.setattr("prompt_files.PROMPTS", tmp_path)
    with pytest.raises(PromptFileError, match=re.escape("greeting.v3 - Copy.md isn't named <prompt>.v<number>.md")):
        load_all("greeting", {"name"})


def test_the_active_version_comes_from_prompt_versions_toml(tmp_path):
    assert hello.ACTIVE == active_version("greeting")              # "v3" as shipped, or whatever the file says now
    rolled_back = tmp_path / "prompt_versions.toml"
    rolled_back.write_text('greeting = "v2"\n', encoding="utf-8")   # the one-line roll-back
    assert active_version("greeting", rolled_back) == "v2"


def test_the_active_version_is_a_released_one():
    # Making a version active releases it: add its fingerprint to RELEASED, so that from then on it can't change.
    assert hello.ACTIVE in RELEASED


@pytest.mark.parametrize("content, problem", [
    ('greeting = v2\n', "isn't valid TOML"),                               # the quotes are missing
    ('greting = "v2"\n', "doesn't say which greeting version to use"),     # a typo in the name
])
def test_a_broken_prompt_versions_toml_is_refused(tmp_path, content, problem):
    path = tmp_path / "prompt_versions.toml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(PromptFileError, match=re.escape(problem)):
        active_version("greeting", path)


# ---- the model and the chains, no call ----

def test_model_settings():
    assert hello.model.model == hello.MODEL == "gemini-3.5-flash-lite"
    assert hello.model.max_output_tokens == hello.MAX_OUTPUT_TOKENS == 300


def test_each_chain_carries_its_version_into_the_trace():
    config = hello.chains["v2"].config
    assert config["run_name"] == "greeting.v2"
    assert config["metadata"] == {"prompt": "greeting", "prompt_version": "v2",
                                  "prompt_fingerprint": hello.GREETINGS["v2"].fingerprint}


def test_greet_labels_the_answer_with_the_version_that_produced_it(monkeypatch):
    monkeypatch.setitem(hello.chains, "v1", RunnableLambda(lambda inputs: f"Hi {inputs['name']}"))
    assert asyncio.run(hello.greet("Asha", "v1")) == {
        "answer": "Hi Asha", "prompt": "greeting", "version": "v1", "fingerprint": hello.GREETINGS["v1"].fingerprint,
    }


# ---- starting: no key, or a broken prompt file, stops with one line ----

def test_with_no_key_it_stops_with_the_message_not_a_stack_trace():
    env = {**os.environ, "GOOGLE_API_KEY": ""}
    result = subprocess.run([sys.executable, "hello.py"], cwd=FOLDER, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't build the chain: GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_broken_prompt_file_stops_the_start_with_one_line_not_a_stack_trace(tmp_path):
    # A copy of this project's code and prompts, plus the copy Windows Explorer leaves behind.
    for name in ("hello.py", "prompt_files.py", "config.py", "prompt_versions.toml"):
        shutil.copy(FOLDER / name, tmp_path)
    shutil.copytree(PROMPTS, tmp_path / "prompts")
    shutil.copy(PROMPTS / "greeting.v3.md", tmp_path / "prompts" / "greeting.v3 - Copy.md")
    env = {**os.environ, "GOOGLE_API_KEY": "fake-key-for-tests"}
    result = subprocess.run([sys.executable, "hello.py"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "Can't load the prompts: greeting.v3 - Copy.md isn't named <prompt>.v<number>.md" in result.stderr
    assert "Traceback" not in result.stderr


# ---- the endpoints, with stand-ins ----

def stand_in(version):
    """A stand-in for one version's chain: it answers "v1: hi Asha" straight away, with no model call."""
    return RunnableLambda(lambda inputs: f"{version}: hi {inputs['name']}")


def stand_in_every_version(monkeypatch):
    for version in hello.GREETINGS:
        monkeypatch.setitem(hello.chains, version, stand_in(version))


def test_api_prompts_lists_every_version_and_the_active_one():
    data = client.get("/api/prompts").json()
    assert data["active"] == hello.ACTIVE
    assert list(data["versions"]) == list(hello.GREETINGS)
    v1 = hello.GREETINGS["v1"]
    assert data["versions"]["v1"] == {"system": v1.system, "human": v1.human, "fingerprint": v1.fingerprint}


def test_api_hello_uses_the_active_version_by_default(monkeypatch):
    stand_in_every_version(monkeypatch)
    response = client.post("/api/hello", json={"name": "Asha"})
    active = hello.ACTIVE                                   # what prompt_versions.toml says: "v3" as shipped
    assert response.json() == {"answer": f"{active}: hi Asha", "prompt": "greeting", "version": active,
                               "fingerprint": hello.GREETINGS[active].fingerprint}


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


def test_a_failed_model_call_gets_a_502_without_the_details(monkeypatch, caplog):
    def fail(inputs):
        raise RuntimeError("quota exceeded for project 1234")
    for version in hello.GREETINGS:                        # every version, so this test can never reach Gemini
        monkeypatch.setitem(hello.chains, version, RunnableLambda(fail))
    response = client.post("/api/hello", json={"name": "Asha"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini didn't answer (RuntimeError)."}
    assert "quota exceeded for project 1234" in caplog.text        # the full reason is in the server's log


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert 'id="versions"' in response.text
    assert hello.api_key not in response.text


# ---- live: each version once ----

@pytest.mark.live
def test_live_every_version_gets_an_answer():
    # invoke(), the plain call `python hello.py` makes, once per version. Not asyncio.run(hello.greet(...)) in a loop:
    # each asyncio.run() starts a new event loop and closes it at the end, but the model keeps its connection to
    # Gemini open for the next call, and that connection belongs to the first loop, so the second call would fail
    # with "Event loop is closed". (The server runs one loop the whole time, so greet() is fine there.)
    for version, chain in hello.chains.items():
        answer = chain.invoke({"name": "Asha"})
        assert answer.strip(), f"greeting {version} gave an empty answer"
