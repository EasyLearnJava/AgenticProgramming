"""
Tests for config.py: the key is read from the environment or .env and handed over as a secret value; a missing key,
the placeholder or a .env that isn't UTF-8 stops the run with a message that says what to do, and never shows a key.
"""
import os

import pytest

from config import MissingKeyError, load_api_key


@pytest.fixture
def no_key(monkeypatch):
    """No GOOGLE_API_KEY in the environment, and whatever load_dotenv() sets is undone after the test."""
    monkeypatch.setenv("GOOGLE_API_KEY", "set, so that the undo removes it")
    monkeypatch.delenv("GOOGLE_API_KEY")


def env_file(tmp_path, text: str, encoding: str = "utf-8"):
    path = tmp_path / ".env"
    path.write_text(text, encoding=encoding)
    return path


def test_the_key_comes_from_env_as_a_secret_that_never_prints(tmp_path, no_key):
    key = load_api_key(env_file(tmp_path, "GOOGLE_API_KEY=AIza-test-value\n"))
    assert key.get_secret_value() == "AIza-test-value"
    assert "AIza" not in str(key) and "AIza" not in repr(key)


def test_a_key_set_outside_the_file_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "from-the-environment")
    assert load_api_key(env_file(tmp_path, "GOOGLE_API_KEY=from-the-file\n")).get_secret_value() == \
        "from-the-environment"


def test_no_key_says_how_to_set_one_or_run_without_one(tmp_path, no_key):
    with pytest.raises(MissingKeyError, match='GOOGLE_API_KEY is not set.*provider = "fake"'):
        load_api_key(tmp_path / "missing.env")


def test_the_placeholder_isnt_a_key(tmp_path, no_key):
    with pytest.raises(MissingKeyError, match="still the placeholder"):
        load_api_key(env_file(tmp_path, "GOOGLE_API_KEY=your-key-here\n"))


def test_a_env_file_that_isnt_utf8_says_how_to_save_it(tmp_path, no_key):
    with pytest.raises(MissingKeyError, match="isn't saved as UTF-8"):
        load_api_key(env_file(tmp_path, "GOOGLE_API_KEY=AIza-test-value\n", encoding="utf-16"))
    assert "GOOGLE_API_KEY" not in os.environ
