"""Tests for project 9: where the key is read from, the fail-fast check, config.py and the server with no key,
that the key never reaches a response or the page, and that git ignores .env. Every key here is fake."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FAKE_KEY = "fake-key-for-tests-123"
os.environ["GOOGLE_API_KEY"] = FAKE_KEY          # before importing main, which checks the key at import

from fastapi.testclient import TestClient        # noqa: E402

from config import MissingKeyError, load_api_key  # noqa: E402
from main import app                              # noqa: E402

client = TestClient(app)
FOLDER = Path(__file__).resolve().parent.parent


def run(script_args, key):
    """Run a command in this folder with GOOGLE_API_KEY set to `key`. An empty key also stops .env from being used:
    load_dotenv() never overwrites a variable that is already set, even to ""."""
    env = {**os.environ, "GOOGLE_API_KEY": key}
    return subprocess.run([sys.executable, *script_args], cwd=FOLDER, env=env, capture_output=True, text=True)


def test_the_key_is_read_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY")
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=key-from-the-file\n")
    assert load_api_key(env_file) == "key-from-the-file"


def test_a_key_already_in_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "key-from-a-codespaces-secret")
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=key-from-the-file\n")
    assert load_api_key(env_file) == "key-from-a-codespaces-secret"


@pytest.mark.parametrize("key, message", [
    (None, "GOOGLE_API_KEY is not set"),          # no .env, nothing in the environment
    ("   ", "GOOGLE_API_KEY is not set"),         # only spaces counts as missing
    ("your-key-here", "still the placeholder"),   # copied .env.example but didn't put the key in
])
def test_no_usable_key_stops_with_a_clear_message(tmp_path, monkeypatch, key, message):
    if key is None:
        monkeypatch.delenv("GOOGLE_API_KEY")
    else:
        monkeypatch.setenv("GOOGLE_API_KEY", key)
    with pytest.raises(MissingKeyError, match=message):
        load_api_key(tmp_path / "no-such.env")


def test_config_py_says_the_key_is_set_without_printing_it():
    result = run(["config.py"], FAKE_KEY)
    assert result.returncode == 0
    assert result.stdout.strip() == "GOOGLE_API_KEY is set."
    assert FAKE_KEY not in result.stdout + result.stderr


@pytest.mark.parametrize("script_args", [["config.py"], ["-m", "uvicorn", "main:app", "--port", "8597"]])
def test_with_no_key_it_stops_with_the_message_not_a_stack_trace(script_args):
    result = run(script_args, "")
    assert result.returncode == 1
    assert "GOOGLE_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


def test_api_status_says_the_key_is_set_and_nothing_more():
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"key_set": True}
    assert FAKE_KEY not in response.text


@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page_is_served_and_holds_no_key(path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'fetch("/api/status")' in response.text
    assert FAKE_KEY not in response.text


def test_example_file_holds_only_the_placeholder():
    assert (FOLDER / ".env.example").read_text().splitlines()[-1] == "GOOGLE_API_KEY=your-key-here"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_ignores_env_but_not_the_example():
    def ignored(name):
        return subprocess.run(["git", "check-ignore", "-q", name], cwd=FOLDER).returncode == 0
    assert ignored(".env")
    assert not ignored(".env.example")
