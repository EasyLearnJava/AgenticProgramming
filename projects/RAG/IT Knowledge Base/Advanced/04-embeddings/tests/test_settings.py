"""
Tests for settings.py: kb_settings.toml read and checked at start; every way a settings file can be wrong stops the
run with one line that names the setting.
"""
import pytest

from settings import load_settings

SETTINGS = """text_fields = ["title", "problem", "resolution"]
label_fields = ["title", "system"]
id_fields = ["title", "system"]
[columns]
title = "title"
problem = "problem"
resolution = "resolution"
system = "system"
"""


def settings_file(tmp_path, text):
    path = tmp_path / "kb_settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_projects_settings_file_loads(tmp_path):
    from knowledge_base_loader import SETTINGS_FILE
    settings = load_settings(SETTINGS_FILE)
    assert settings.text_fields == ("title", "problem", "resolution", "notes")
    assert settings.id_fields == ("title", "system")
    assert settings.columns["priority"] == "priority"
    assert settings.spellings["system"]["WiFi"] == ["Wireless", "WLAN"]
    assert settings.chunking.model_dump() == {"chunk_size": 128, "chunk_overlap": 16, "min_tokens": 8,
                                              "max_tokens": 512}
    embeddings = settings.embeddings
    assert (embeddings.provider, embeddings.model, embeddings.dimensions, embeddings.model_name) == \
        ("google", "gemini-embedding-001", 768, "google/gemini-embedding-001")
    assert (embeddings.batch_size, embeddings.max_concurrency, embeddings.max_attempts) == (100, 2, 4)
    assert str(embeddings.cache_path).replace("\\", "/") == "data/embedding_cache.sqlite3"


def test_the_embedding_defaults_are_embedding_pys(tmp_path):
    import embedding
    settings = load_settings(settings_file(tmp_path, SETTINGS)).embeddings
    assert (settings.provider, settings.model, settings.dimensions, settings.batch_size, settings.batch_tokens,
            settings.max_concurrency, settings.max_attempts, settings.timeout_seconds, settings.backoff_seconds,
            settings.backoff_max_seconds) == (
        embedding.PROVIDER, embedding.MODEL, embedding.DIMENSIONS, embedding.BATCH_SIZE, embedding.BATCH_TOKENS,
        embedding.MAX_CONCURRENCY, embedding.MAX_ATTEMPTS, embedding.TIMEOUT_SECONDS, embedding.BACKOFF_SECONDS,
        embedding.BACKOFF_MAX_SECONDS)


def test_a_small_settings_file_loads_with_no_spellings_and_the_default_sizes(tmp_path):
    from chunking import CHUNK_OVERLAP, CHUNK_SIZE, MAX_TOKENS, MIN_TOKENS
    settings = load_settings(settings_file(tmp_path, SETTINGS))
    assert (settings.label_fields, settings.spellings) == (("title", "system"), {})
    assert (settings.chunking.chunk_size, settings.chunking.chunk_overlap, settings.chunking.min_tokens,
            settings.chunking.max_tokens) == (CHUNK_SIZE, CHUNK_OVERLAP, MIN_TOKENS, MAX_TOKENS)


def test_a_missing_settings_file_fails(tmp_path):
    with pytest.raises(FileNotFoundError, match="Settings file not found: .*nothing.toml"):
        load_settings(tmp_path / "nothing.toml")


def test_a_file_that_isnt_toml_fails(tmp_path):
    with pytest.raises(ValueError, match=r"isn't valid TOML \(.*line 1"):
        load_settings(settings_file(tmp_path, "text_fields = [title"))


@pytest.mark.parametrize("text, message", [
    (SETTINGS + 'owner = "Ana"\n', r"columns names a field an article doesn't have \(owner\)"),
    (SETTINGS.replace('label_fields = ["title", "system"]', 'label_fields = ["title", "sytem"]'),
     r"label_fields names a field an article doesn't have \(sytem\)"),
    (SETTINGS.replace('resolution = "resolution"\n', ""), r"no column for a required field \(resolution\)"),
    (SETTINGS.replace('system = "system"', 'system = "title"'), r"two fields from one column \(title\)"),
    (SETTINGS.replace('id_fields = ["title", "system"]', 'id_fields = ["tags"]'), "id_fields must name one or more"),
    (SETTINGS + '[spellings.system]\nWiFi = ["Wireless"]\nWLAN = ["wireless"]\n',
     '"wireless" is a spelling of both "WiFi" and "WLAN"'),
    (SETTINGS + '[spellings.priority]\nUrgent = ["P0"]\n', "a right spelling must be one of Low, Medium"),
    ('text_fields = ["title"]\n', "label_fields: Field required"),
    ('colour = "blue"\n' + SETTINGS, "colour: Extra inputs are not permitted"),
    (SETTINGS + "[chunking]\nchunk_size = 600\n", "chunk_size \\+ min_tokens <= max_tokens"),
    (SETTINGS + "[chunking]\nchunk_overlap = 200\n", "keep chunk_overlap and min_tokens below chunk_size"),
    (SETTINGS + "[chunking]\nchunk_sise = 100\n", "chunking.chunk_sise: Extra inputs are not permitted"),
    (SETTINGS + '[embeddings]\nprovider = "openai"\n', "embeddings.provider: Input should be 'google' or 'fake'"),
    (SETTINGS + "[embeddings]\nbatch_size = 500\n", "embeddings.batch_size: Input should be less than or equal to 100"),
], ids=["unknown column", "unknown field", "required field", "shared column", "id from tags", "ambiguous spelling",
        "priority spelling", "missing setting", "unknown setting", "past the ceiling", "overlap too big",
        "chunking typo", "unknown provider", "batch too big"])
def test_a_bad_setting_stops_the_run_naming_it(tmp_path, text, message):
    with pytest.raises(ValueError, match=f"Settings file has a bad setting .*{message}"):
        load_settings(settings_file(tmp_path, text))
