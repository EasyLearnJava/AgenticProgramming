"""
tests/unit/conftest.py: what the unit tests share: no setting from the shell's environment or a .env file, settings of
their own, a stand-in for Gemini, and a client that calls the app in memory, without a server.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import AliasChoices

from nimbus.app import create_app
from nimbus.config import Settings
from tests.fakes import FakeModel


@pytest.fixture(autouse=True)
def no_settings_from_the_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removes every variable the settings read, so a test's result never depends on the shell it runs in."""
    for name, field in Settings.model_fields.items():
        alias = field.validation_alias
        for variable in alias.choices if isinstance(alias, AliasChoices) else [name]:
            monkeypatch.delenv(str(variable).upper(), raising=False)


@pytest.fixture
def settings() -> Settings:
    """A production build's settings, as Vercel sets them, but served as on a computer, stylesheet included."""
    return Settings(
        _env_file=None,
        vercel_env="production",
        vercel_git_commit_sha="c7165ac9d2b84e1f",
        vercel_deployment_id="dpl_TestDeployment",
    )


@pytest.fixture
def chat_model() -> FakeModel:
    """The stand-in for Gemini the app answers with: a known answer, a word at a time, with no pause."""
    return FakeModel()


@pytest.fixture
def client(settings: Settings, chat_model: FakeModel) -> Iterator[TestClient]:
    """A client for the app built with those settings, which answers with the stand-in model."""
    app = create_app(settings)
    app.state.chat_model = chat_model
    with TestClient(app) as test_client:
        yield test_client
