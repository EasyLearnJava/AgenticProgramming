"""
Tests for src/config/settings.py: the shipped config.yaml and what it holds; paths found from the file's folder; a
typo, a missing value, a value out of range, a bad file or bad YAML each stopping the start with a message naming
it; and the API key: from the environment or .env, never shown, and each way it can be missing.
"""
import pytest
from pydantic import ValidationError
from support import write_config

from src.config.settings import PROJECT_DIR, load_api_key, load_settings
from src.exceptions import ConfigError

# --- The shipped settings ---

def test_the_shipped_config_loads_with_its_values():
    settings = load_settings()
    assert (settings.chunking.chunk_size, settings.chunking.chunk_overlap, settings.retrieval.top_k) == (512, 50, 5)
    assert (settings.embeddings.model, settings.embeddings.dimensions) == ("gemini-embedding-001", 768)
    assert (settings.llm.model, settings.llm.max_output_tokens) == ("gemini-3.5-flash-lite", 500)
    assert (settings.vectordb.location, settings.vectordb.collection) == (":memory:", "it_knowledge_base")
    assert (settings.api.host, settings.api.port) == ("127.0.0.1", 8000)
    assert len(settings.app.sample_questions) == 3


def test_paths_are_found_from_the_config_files_folder():
    settings = load_settings()
    assert settings.ingestion.path == PROJECT_DIR / "data" / "sample_it_kb.csv"
    assert settings.logging.file == PROJECT_DIR / "logs" / "app.log"


def test_a_relative_path_follows_the_config_file_wherever_it_is(tmp_path):
    settings = load_settings(write_config(tmp_path, ingestion={"path": "kb/articles.csv"}))
    assert settings.ingestion.path == tmp_path / "kb" / "articles.csv"


def test_settings_cant_be_changed_once_loaded():
    settings = load_settings()
    with pytest.raises(ValidationError, match="Instance is frozen"):
        settings.retrieval.top_k = 3


# --- Bad settings ---

@pytest.mark.parametrize("changes, message", [
    ({"chunking": {"chunk_szie": 400}}, "chunking.chunk_szie: Extra inputs are not permitted"),
    ({"chunking": {"chunk_overlap": 512}}, "chunk_overlap (512) must be less than chunk_size (512)"),
    ({"retrieval": {"top_k": 0}}, "retrieval.top_k: Input should be greater than or equal to 1"),
    ({"llm": {"provider": "openai"}}, "llm.provider: Input should be 'google'"),
    ({"embeddings": {"batch_size": 250}}, "embeddings.batch_size: Input should be less than or equal to 100"),
    ({"logging": {"level": "LOUD"}}, "logging.level: Input should be 'DEBUG', 'INFO', 'WARNING' or 'ERROR'"),
    ({"ingestion": {"required_columns": ["title", "owner"]}}, "required_columns names columns that aren't read: owner"),
    ({"ingestion": {"encoding": "utf-9"}}, "ingestion.encoding: Value error, 'utf-9' isn't an encoding Python knows"),
    ({"api": None}, "api: Input should be a valid dictionary"),
], ids=["typo", "overlap", "top_k", "provider", "batch_size", "level", "required column", "encoding",
         "missing section"])
def test_a_bad_setting_stops_the_start_and_is_named(tmp_path, changes, message):
    with pytest.raises(ConfigError, match="Config file has 1 bad setting") as caught:
        load_settings(write_config(tmp_path, **changes))
    assert message in str(caught.value)


def test_every_bad_setting_is_listed_at_once(tmp_path):
    with pytest.raises(ConfigError, match="Config file has 2 bad setting") as caught:
        load_settings(write_config(tmp_path, retrieval={"top_k": 0}, api={"port": 70000}))
    assert "retrieval.top_k" in str(caught.value) and "api.port" in str(caught.value)


def test_a_missing_file_or_bad_yaml_stops_the_start(tmp_path):
    with pytest.raises(ConfigError, match=r"Config file not found: .*missing\.yaml"):
        load_settings(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("app: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="isn't valid YAML"):
        load_settings(bad)
    bad.write_text("just a line\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must hold sections such as app: and ingestion:, not str"):
        load_settings(bad)


# --- The API key ---

def test_the_key_comes_from_the_environment_and_is_never_shown(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_API_KEY", "  a-key-from-the-environment  ")
    key = load_api_key(tmp_path / ".env")
    assert key.get_secret_value() == "a-key-from-the-environment"            # spaces trimmed
    assert "a-key" not in str(key) and "a-key" not in repr(key)               # printed or logged: **********


def test_the_key_comes_from_the_env_file_when_the_environment_has_none(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=a-key-from-the-file\n", encoding="utf-8")
    assert load_api_key(env_file).get_secret_value() == "a-key-from-the-file"


@pytest.mark.parametrize("value, message", [
    ("", "GOOGLE_API_KEY is not set. Copy .env.example to .env"),
    ("your-key-here", "GOOGLE_API_KEY is still the placeholder from .env.example"),
], ids=["missing", "placeholder"])
def test_a_missing_or_placeholder_key_says_what_to_do(monkeypatch, tmp_path, value, message):
    monkeypatch.setenv("GOOGLE_API_KEY", value)        # set, even to "": the .env file isn't used
    with pytest.raises(ConfigError, match=message):
        load_api_key(tmp_path / ".env")


def test_an_env_file_saved_as_utf16_says_to_save_it_as_utf8(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("GOOGLE_API_KEY=a-key\n", encoding="utf-16")         # what PowerShell 5's `echo > .env` does
    with pytest.raises(ConfigError, match=r"\.env isn't saved as UTF-8 text"):
        load_api_key(env_file)
