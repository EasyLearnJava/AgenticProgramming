"""tests/unit/test_config.py: the settings: what the environment and a .env file give, checked."""

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from nimbus.config import Settings


def test_a_build_on_a_computer_is_local() -> None:
    settings = Settings(_env_file=None)
    assert settings.is_vercel is False
    assert settings.environment == "local"
    assert settings.commit is None
    assert settings.build_label == "Build: local"
    assert settings.log_level == "info"


def test_a_vercel_build_names_its_commit_and_environment(settings: Settings) -> None:
    assert settings.commit == "c7165ac"
    assert settings.build_label == "Build c7165ac · production"


def test_reads_the_environment_vercel_sets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "abcdef1234567")
    settings = Settings(_env_file=None)
    assert settings.is_vercel is True
    assert settings.environment == "preview"
    assert settings.commit == "abcdef1"


def test_an_empty_value_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_ENV", "")
    monkeypatch.setenv("LOG_LEVEL", "")
    settings = Settings(_env_file=None)
    assert settings.environment == "local"
    assert settings.log_level == "info"


def test_refuses_a_value_it_does_not_know(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_reads_env_local_on_a_computer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env.local").write_text("LOG_LEVEL=debug\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert Settings().log_level == "debug"


def test_reads_workspace_from_dotenv_and_prefers_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local, deployed = UUID(int=17), UUID(int=18)
    monkeypatch.chdir(tmp_path)
    assert Settings().langsmith_workspace_id is None
    (tmp_path / ".env.local").write_text(f"LANGSMITH_WORKSPACE_ID={local}\n", encoding="utf-8")
    assert Settings().langsmith_workspace_id == local
    monkeypatch.setenv("LANGSMITH_WORKSPACE_ID", str(deployed))
    assert Settings().langsmith_workspace_id == deployed
    monkeypatch.setenv("LANGSMITH_WORKSPACE_ID", "not-a-workspace-uuid")
    with pytest.raises(ValidationError, match="langsmith_workspace_id"):
        Settings()


def test_a_pulled_env_local_never_makes_a_computer_look_like_vercel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `vercel env pull` copies Vercel's own variables into .env.local, beside yours.
    pulled = 'VERCEL="1"\nVERCEL_ENV="development"\nVERCEL_GIT_COMMIT_SHA="abc1234"\nLOG_LEVEL=debug\n'
    (tmp_path / ".env.local").write_text(pulled, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.is_vercel is False
    assert settings.environment == "local"
    assert settings.commit is None
    assert settings.log_level == "debug"


def test_reads_axiom_s_and_sentry_s_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_TOKEN", "test-axiom-token-5150")
    monkeypatch.setenv("AXIOM_DATASET", "weather-chatbot")
    monkeypatch.setenv("SENTRY_DSN", "https://public@o0.ingest.sentry.test/0")
    settings = Settings(_env_file=None)
    assert settings.axiom_token is not None
    assert settings.axiom_token.get_secret_value() == "test-axiom-token-5150"
    assert settings.axiom_dataset == "weather-chatbot"
    assert settings.sentry_dsn is not None
    assert "test-axiom-token-5150" not in repr(settings)


def test_reads_the_observability_pages_query_token_and_never_shows_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_QUERY_TOKEN", "xaat-query-token-5150")
    settings = Settings(_env_file=None)
    assert settings.axiom_query_token is not None
    assert settings.axiom_query_token.get_secret_value() == "xaat-query-token-5150"
    assert "xaat-query-token-5150" not in repr(settings)
