"""
tests/unit/conftest.py: what the unit tests share: no setting from the shell's environment or a .env file, settings of
their own, stand-ins for Gemini and Open-Meteo, and a client that calls the app in memory, without a server.
"""

from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import AliasChoices

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from tests.fakes import FakeCacheStore, FakeModel, OpenMeteoRecordings


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
def open_meteo() -> OpenMeteoRecordings:
    """The stand-in for Open-Meteo the weather tools call: its recorded answers, with no pause."""
    return OpenMeteoRecordings()


@pytest.fixture
def cache_store() -> FakeCacheStore:
    """The stand-in for Vercel's Runtime Cache, empty for each test, so no test's weather comes from another's."""
    return FakeCacheStore()


@pytest.fixture
def client(
    settings: Settings, chat_model: FakeModel, open_meteo: OpenMeteoRecordings, cache_store: FakeCacheStore
) -> Iterator[TestClient]:
    """A client for the app built with those settings, which answers with the stand-ins: no call leaves the test."""
    app = create_app(settings)
    app.state.chat_model = chat_model
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(cache_store)
    with TestClient(app) as test_client:
        yield test_client
