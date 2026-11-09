"""Real-browser navigation, accessibility and layout for the private weather-cache inventory."""

import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Page, expect

from nimbus.semantic_cache.models import CacheEntry, CacheListing
from nimbus.semantic_cache.service import SemanticCacheService


@pytest.fixture
def populated_inventory(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Replace only the inventory provider; real routing, rendering, styles and Chrome remain in use."""
    touched: list[tuple[SemanticCacheService, Literal["off", "shadow", "on"]]] = []

    def configured(service: SemanticCacheService) -> bool:
        """Enable this page fixture without a credential or outbound request, restoring its mode afterward."""
        if not any(item is service for item, _ in touched):
            touched.append((service, service.mode))
        service.mode = "on"
        return True

    async def listing(_service: SemanticCacheService, scope: str) -> CacheListing:
        """Supply a synthetic display record with private answer text that must remain absent."""
        assert scope == "synthetic-browser"
        now = time.time()
        entry = cast(
            CacheEntry,
            SimpleNamespace(
                label="Dallas, Texas, US · current weather",
                created_at=now - 20,
                expires_at=now + 80,
                evidence_fetched_at=now - 70,
                answer="Private synthetic answer must not appear",
            ),
        )
        return CacheListing.model_construct(status="ready", entries=(entry,))

    monkeypatch.setattr(SemanticCacheService, "configured", property(configured))
    monkeypatch.setattr(SemanticCacheService, "list_entries", listing)
    monkeypatch.setattr("nimbus.semantic_cache.page.read_scope", lambda _: "synthetic-browser")
    yield
    for service, mode in touched:
        service.mode = mode


def test_cache_page_opens_from_observability_without_configuration(page: Page) -> None:
    """The always-visible sidebar link explains unavailable configuration instead of hiding the feature."""
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Weather cache", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Weather cache")).to_be_visible()
    expect(page.get_by_role("heading", name="Weather answer caching is off")).to_be_visible()
    expect(page.get_by_role("link", name="Refresh status")).to_be_visible()


@pytest.mark.parametrize("width", [320, 360, 1280])
def test_populated_cache_is_private_accessible_and_fits_phone_and_desktop(
    page: Page, populated_inventory: None, width: int
) -> None:
    """Cache labels and absolute expiry remain readable with no XSS, console failures or horizontal overflow."""
    errors: list[str] = []

    def capture_error(message: ConsoleMessage) -> None:
        """Capture missing assets and CSP errors while leaving ordinary browser messages alone."""
        if message.type == "error":
            errors.append(message.text)

    page.on("console", capture_error)
    page.set_viewport_size({"width": width, "height": 1000})
    response = page.goto("/weather-cache")
    assert response is not None
    assert response.headers["cache-control"] == "no-store"
    expect(page.locator(".cache-entry")).to_have_count(1)
    expect(page.locator(".cache-entry")).to_contain_text("Dallas, Texas, US")
    expect(page.locator(".cache-entry")).to_contain_text("seconds remaining")
    expect(page.locator(".cache-entry time")).to_contain_text("UTC")
    expect(page.locator("main")).not_to_contain_text("Private synthetic answer")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert errors == []
    capture = Path("test-results") / f"weather-cache-{width}.png"
    capture.parent.mkdir(exist_ok=True)
    page.screenshot(path=str(capture), full_page=True)
