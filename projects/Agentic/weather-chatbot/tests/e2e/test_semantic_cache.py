"""A browser proves that real chat history receipts permit immediate weather repeats and a private cache inventory."""

import asyncio
import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page, expect

from nimbus.app import create_app
from nimbus.config import Settings
from tests.fakes import FakeModel
from tests.unit.test_semantic_cache_chat import CacheProvider, DallasWeather, configure_cache


@pytest.fixture
def cache_server() -> Iterator[tuple[str, FakeModel, CacheProvider]]:
    """Serve an isolated app with synthetic providers; no key, question or test leaves this computer."""
    settings = Settings(
        _env_file=None,
        google_api_key=None,
        langsmith_tracing=False,
        langsmith_api_key=None,
        memory_enabled=False,
        mem0_api_key=None,
        memory_cookie_secret=None,
        parks_enabled=False,
        nps_api_key=None,
        flights_enabled=False,
        hotels_enabled=False,
        axiom_token=None,
        axiom_query_token=None,
        sentry_dsn=None,
        apify_token=None,
        log_level="warning",
        is_vercel=False,
        semantic_cache_mode="off",
        qdrant_url="",
        qdrant_api_key=None,
    )
    app = create_app(settings)
    model, provider, weather = FakeModel(), CacheProvider(), DallasWeather()
    configure_cache(app, model, provider, weather)
    app.state.chat_model = model
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = int(available.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop),
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Synthetic semantic-cache app did not start")
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", model, provider
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def submit_weather(page: Page, question: str, expected_cards: int) -> None:
    """Drive the normal form and wait for the final rendered evidence, not an intermediate streaming piece."""
    page.get_by_label("Your question").fill(question)
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.locator(".weather-card")).to_have_count(expected_cards)
    expect(page.locator(".message-bot[aria-busy]")).to_have_count(0)


@pytest.mark.parametrize("width", [360, 1280])
def test_repeat_cache_inventory_and_new_chat_work_with_real_browser_history(
    browser: Browser,
    cache_server: tuple[str, FakeModel, CacheProvider],
    width: int,
) -> None:
    """Verify truthful zero-call reuse, browser-only inventory, keyboard flow and accessible responsive presentation."""
    url, model, provider = cache_server
    context = browser.new_context(
        locale="en-US", timezone_id="America/Chicago", viewport={"width": width, "height": 1000}
    )
    page = context.new_page()
    try:
        page.goto(url)
        expect(page.get_by_role("link", name="Weather cache", exact=True)).to_be_visible()
        submit_weather(page, "Dallas weather", 1)
        first = page.locator(".message-bot").last
        first_id = first.get_attribute("id")
        expect(first).to_have_attribute("data-cache-receipt", re.compile(r"[a-f0-9]{64}"))
        initial_calls = len(model.seen)
        initial_points = len(provider.points)
        submit_weather(page, "weather in Dallas", 2)
        latest = page.locator(".message-bot").last
        expect(latest).to_contain_text("Cached answer")
        expect(latest).to_contain_text("Gemini was not called")
        expect(latest.locator(".tool-chip")).to_have_count(0)
        assert latest.get_attribute("id") != first_id
        assert len(model.seen) == initial_calls
        assert len(provider.points) == initial_points == 1
        assert "Cached answer" not in page.locator("#history").input_value()
        assert page.locator("#cache-receipt").input_value()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        results = Axe().run(page)
        assert results.violations_count == 0, results.generate_report()
        capture = Path("test-results") / f"semantic-cache-chat-{width}.png"
        capture.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(capture), full_page=True)

        page.get_by_role("button", name="New chat").click()
        expect(page.locator("#history")).to_have_value("[]")
        expect(page.locator("#cache-receipt")).to_have_value("")
        submit_weather(page, "Dallas weather", 1)
        expect(page.locator(".message-bot").last).to_contain_text("Cached answer")
        assert len(model.seen) == initial_calls

        page.locator(".side-menu").get_by_role("link", name="Weather cache", exact=True).click()
        expect(page.get_by_role("heading", name="Weather cache", exact=True)).to_be_visible()
        expect(page.locator("main")).to_contain_text("Dallas")
        expect(page.locator("main")).to_contain_text("seconds")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        results = Axe().run(page)
        assert results.violations_count == 0, results.generate_report()
        page.screenshot(path=str(Path("test-results") / f"semantic-cache-inventory-{width}.png"), full_page=True)

        private = browser.new_context()
        try:
            other = private.new_page()
            other.goto(url + "/weather-cache")
            expect(other.locator(".cache-entry")).to_have_count(0)
            expect(other.get_by_role("heading", name="No active cached answers", exact=True)).to_be_visible()
        finally:
            private.close()
    finally:
        context.close()
