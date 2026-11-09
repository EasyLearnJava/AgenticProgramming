"""The weather-cache page shows only this browser's live entries and never serves a shared cached response."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nimbus.config import Settings
from nimbus.semantic_cache.models import CacheEntry, CacheListing
from nimbus.semantic_cache.page import router

NOW = 1_800_000_000.0


def entry(label: str = "Dallas · current weather", **changes: object) -> CacheEntry:
    """A display fixture carries private fields too, so accidental template exposure is observable."""
    return cast(
        CacheEntry,
        SimpleNamespace(
            **{
                "label": label,
                "created_at": NOW - 30,
                "expires_at": NOW + 70,
                "evidence_fetched_at": NOW - 90,
                "answer": "private-answer-must-not-appear",
                "question": "private-question-must-not-appear",
                "scope": "private-browser-identity",
                **changes,
            }
        ),
    )


class ListingService:
    """Record which browser scope was requested without accessing any provider."""

    configured = True
    mode = "on"

    def __init__(self) -> None:
        """Start with one live entry and no calls."""
        self.scopes: list[str] = []
        self.status = "ready"
        self.entries: tuple[CacheEntry, ...] = (entry(),)
        self.error: Exception | None = None

    async def list_entries(self, scope: str) -> CacheListing:
        """Return controlled metadata, or a provider failure that must not reach the page."""
        self.scopes.append(scope)
        if self.error:
            raise self.error
        return cast(CacheListing, SimpleNamespace(status=self.status, entries=self.entries))


@pytest.fixture
def service() -> ListingService:
    """One cache service per test."""
    return ListingService()


@pytest.fixture
def cache_page(settings: Settings, service: ListingService, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Render the real page with a fixed clock and a server-resolved browser scope."""
    app = FastAPI()
    app.state.settings = settings
    app.state.semantic_cache = service
    app.include_router(router)
    monkeypatch.setattr("nimbus.semantic_cache.page.time.time", lambda: NOW)
    monkeypatch.setattr("nimbus.semantic_cache.page.read_scope", lambda _: "this-browser")
    with TestClient(app) as client:
        yield client


def test_cache_page_lists_only_browser_metadata_with_expiry(cache_page: TestClient, service: ListingService) -> None:
    """The label, original data age and remaining lifetime are visible without stored conversation contents."""
    response = cache_page.get("/weather-cache")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"
    assert "set-cookie" not in response.headers
    assert service.scopes == ["this-browser"]
    assert "Dallas · current weather" in response.text
    assert "70 seconds" in response.text
    assert "90 seconds" in response.text
    assert "UTC" in response.text
    assert 'href="/weather-cache" aria-current="page"' in response.text
    assert "private-" not in response.text


def test_cache_page_without_identity_never_lists_any_scope(
    cache_page: TestClient, service: ListingService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh browser gets an empty page, not a global list or a new cookie."""
    monkeypatch.setattr("nimbus.semantic_cache.page.read_scope", lambda _: None)
    response = cache_page.get("/weather-cache")
    assert "No active cached answers" in response.text
    assert not service.scopes
    assert "Dallas · current weather" not in response.text
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("configured", [True, False])
def test_disabled_cache_page_does_not_query_provider(
    cache_page: TestClient, service: ListingService, configured: bool
) -> None:
    """An off feature or missing credentials reports disabled without contacting Qdrant."""
    service.configured = configured
    service.mode = "off" if configured else "on"
    response = cache_page.get("/weather-cache")
    assert "Weather answer caching is off" in response.text
    assert not service.scopes


@pytest.mark.parametrize("failure", ["status", "exception"])
def test_cache_page_handles_provider_outage_without_private_error(
    cache_page: TestClient, service: ListingService, failure: str
) -> None:
    """An outage must not look like a confirmed empty cache or leak an upstream exception."""
    if failure == "status":
        service.status = "unavailable"
    else:
        service.error = RuntimeError("private-provider-url-and-key")
    response = cache_page.get("/weather-cache")
    assert response.status_code == 200
    assert "Cache status is temporarily unavailable" in response.text
    assert "No active cached answers" not in response.text
    assert "private-" not in response.text


def test_cache_page_filters_expired_entries_and_escapes_labels(cache_page: TestClient, service: ListingService) -> None:
    """Expired entries cannot look reusable, even when a provider accidentally includes them in its list."""
    service.entries = (
        entry("expired-marker", expires_at=NOW),
        entry("<img src=x onerror=alert(1)>"),
        entry("future-marker", created_at=NOW + 1),
        entry("invalid-marker", expires_at=float("inf")),
    )
    response = cache_page.get("/weather-cache")
    assert "expired-marker" not in response.text
    assert "future-marker" not in response.text
    assert "invalid-marker" not in response.text
    assert "&lt;img" in response.text
    assert "<img src=x" not in response.text


def test_cache_page_caps_entries_and_marks_shadow_mode(cache_page: TestClient, service: ListingService) -> None:
    """The page remains bounded and shadow entries are not described as bypassing the model."""
    service.mode = "shadow"
    service.entries = tuple(entry(f"Cached city {index}") for index in range(60))
    response = cache_page.get("/weather-cache")
    assert response.text.count('class="cache-entry"') == 50
    assert "Shadow mode" in response.text
    assert "Gemini still answers" in response.text


def test_cache_scope_cannot_be_chosen_in_the_address(cache_page: TestClient, service: ListingService) -> None:
    """A query parameter is never an authority to inspect somebody else's cache."""
    assert cache_page.get("/weather-cache?scope=another-browser").status_code == 400
    assert not service.scopes
