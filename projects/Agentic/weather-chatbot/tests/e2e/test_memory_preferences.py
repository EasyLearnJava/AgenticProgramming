"""Opt-in browser preference memory through real pages and chat, with an isolated in-memory Mem0 stand-in."""

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, ConsoleMessage, Page, expect
from pydantic import SecretStr

from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.memory.client import Mem0Service
from nimbus.memory.models import PreferenceProfile, Snapshot
from nimbus.request_trace import TraceParent
from tests.fakes import FakeModel


class BrowserMemory(Mem0Service):
    """Owned synthetic profiles with controllable failures; no network request or real credential is used."""

    def __init__(self) -> None:
        """Prepare a configured stand-in with separate scopes for every browser cookie."""
        super().__init__(SecretStr("synthetic-memory-key"))
        self.rows: dict[str, Snapshot] = {}
        self.unavailable = False
        self.fail_forget = False

    async def read(self, user_id: str, parent: TraceParent | None = None) -> Snapshot:
        """Return only this visitor's profile, or an explicit simulated outage; nothing here is traced."""
        if self.unavailable:
            return Snapshot(status="unavailable", reason="unavailable")
        return self.rows.get(user_id, Snapshot(status="empty"))

    async def save(self, user_id: str, preferences: PreferenceProfile, expected_revision: str) -> Snapshot:
        """Replace a confirmed profile, refusing a form based on a stale revision."""
        current = await self.read(user_id)
        if current.status == "unavailable":
            return current
        if current.revision != expected_revision:
            return Snapshot(status="conflict", reason="stale_revision")
        snapshot = Snapshot(status="ready", preferences=preferences, revision=str(uuid4()), memory_ids=(str(uuid4()),))
        self.rows[user_id] = snapshot
        return snapshot

    async def forget(self, user_id: str) -> bool:
        """Fail on demand, otherwise remove only the calling browser's preferences."""
        if self.fail_forget or self.unavailable:
            return False
        self.rows.pop(user_id, None)
        return True


@pytest.fixture
def memory_server() -> Iterator[tuple[str, BrowserMemory]]:
    """Serve the real app with memory explicitly enabled and every paid/external integration disabled."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    settings = Settings(
        _env_file=None,
        is_vercel=False,
        google_api_key=None,
        apify_token=None,
        axiom_token=None,
        axiom_query_token=None,
        sentry_dsn=None,
        langsmith_tracing=False,
        langsmith_api_key=None,
        nps_api_key=None,
        parks_enabled=False,
        flights_enabled=False,
        hotels_enabled=False,
        log_level="warning",
        memory_enabled=True,
        mem0_api_key=SecretStr("synthetic-memory-key"),
        memory_cookie_secret=SecretStr("synthetic-cookie-signing-secret-for-browser-tests"),
    )
    app = create_app(settings)
    store = BrowserMemory()
    app.state.mem0 = store
    app.state.chat_model = FakeModel(answer="Your current request takes priority over saved preferences.")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop), daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() >= deadline:
            raise RuntimeError("Memory browser test server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", store
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def base_url(memory_server: tuple[str, BrowserMemory]) -> str:
    """Use the memory-enabled server for this module's browser context."""
    return memory_server[0]


@pytest.fixture
def page(browser: Browser, base_url: str) -> Iterator[Page]:
    """Give each case a browser profile tied to its own isolated app and rate-limit state."""
    context = browser.new_context(base_url=base_url)
    yield context.new_page()
    context.close()


@pytest.fixture(autouse=True)
def empty_preferences(memory_server: tuple[str, BrowserMemory]) -> None:
    """Give each browser case fresh fake data and unexhausted request limits."""
    store = memory_server[1]
    store.rows.clear()
    store.unavailable = False
    store.fail_forget = False


def save_preferences(page: Page, *, origin: str = "DFW") -> None:
    """Save explicitly selected defaults through the real, same-origin consent form."""
    page.goto("/preferences")
    page.locator('input[name="origin"]').fill(origin)
    page.locator('select[name="unit_system"]').select_option("metric")
    page.locator('select[name="currency"]').select_option("USD")
    page.locator('select[name="activity"]').select_option("easy hikes")
    page.locator('select[name="depart_window"]').select_option("evening")
    page.locator('input[name="consent"]').check()
    page.get_by_role("button", name="Save preferences", exact=True).click()
    expect(page.get_by_text("Memory on", exact=True)).to_be_visible()
    expect(page.locator('input[name="origin"]')).to_have_value(origin)


def test_preferences_require_opt_in_and_survive_new_chat_and_browser_reopening(
    page: Page, browser: Browser, base_url: str, memory_server: tuple[str, BrowserMemory]
) -> None:
    """Viewing a page saves nothing; an explicit save persists beyond a conversation and a restored browser session."""
    page.goto("/preferences")
    assert not memory_server[1].rows
    assert not any(cookie["name"] == "nimbus_preferences" for cookie in page.context.cookies())
    expect(page.locator('input[name="consent"]')).not_to_be_checked()
    save_preferences(page)
    page.goto("/")
    page.get_by_role("button", name="New chat", exact=True).click()
    page.goto("/preferences")
    expect(page.locator('input[name="origin"]')).to_have_value("DFW")
    state = page.context.storage_state()
    restored = browser.new_context(base_url=base_url, storage_state=state)
    try:
        reopened = restored.new_page()
        reopened.goto("/preferences")
        expect(reopened.locator('input[name="origin"]')).to_have_value("DFW")
        expect(reopened.locator('select[name="unit_system"]')).to_have_value("metric")
        expect(reopened.locator('select[name="currency"]')).to_have_value("USD")
    finally:
        restored.close()


def test_browser_profiles_are_isolated_and_edits_replace_the_previous_value(
    page: Page, browser: Browser, base_url: str, memory_server: tuple[str, BrowserMemory]
) -> None:
    """A second anonymous visitor sees no first visitor data, and a confirmed edit replaces its own profile."""
    save_preferences(page)
    other_context = browser.new_context(base_url=base_url)
    try:
        other = other_context.new_page()
        other.goto("/preferences")
        expect(other.locator('input[name="origin"]')).to_have_value("")
        save_preferences(other, origin="BOS")
        page.reload()
        expect(page.locator('input[name="origin"]')).to_have_value("DFW")
        page.locator('input[name="origin"]').fill("ORD")
        page.locator('input[name="consent"]').check()
        page.get_by_role("button", name="Save preferences", exact=True).click()
        expect(page.locator('input[name="origin"]')).to_have_value("ORD")
        other.reload()
        expect(other.locator('input[name="origin"]')).to_have_value("BOS")
        assert len(memory_server[1].rows) == 2
        assert {row.preferences.origin for row in memory_server[1].rows.values()} == {"ORD", "BOS"}
    finally:
        other_context.close()


def test_pause_resume_and_failed_deletion_keep_honest_controls(
    page: Page, memory_server: tuple[str, BrowserMemory]
) -> None:
    """Pause preserves the record; failed deletion preserves a usable retry until Mem0 confirms removal."""
    save_preferences(page)
    page.get_by_role("button", name="Pause memory", exact=True).click()
    expect(page.get_by_text("Memory paused", exact=True)).to_be_visible()
    assert len(memory_server[1].rows) == 1
    page.get_by_role("button", name="Resume memory", exact=True).click()
    expect(page.get_by_text("Memory on", exact=True)).to_be_visible()
    memory_server[1].fail_forget = True
    page.get_by_text("Forget saved preferences", exact=True).click()
    page.get_by_role("button", name="Delete saved preferences", exact=True).click()
    expect(page.get_by_role("alert")).to_be_visible()
    expect(page.get_by_text("Deletion pending", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Save preferences", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Resume memory", exact=True)).to_have_count(0)
    assert len(memory_server[1].rows) == 1
    memory_server[1].fail_forget = False
    page.get_by_text("Forget saved preferences", exact=True).click()
    page.get_by_role("button", name="Delete saved preferences", exact=True).click()
    expect(page.locator('input[name="origin"]')).to_have_value("")
    assert not memory_server[1].rows


def test_memory_outage_does_not_present_empty_defaults_as_saved_data(
    page: Page, memory_server: tuple[str, BrowserMemory]
) -> None:
    """An unavailable provider blocks editing and gives a retry, without disabling ordinary chat."""
    save_preferences(page)
    memory_server[1].unavailable = True
    page.reload()
    expect(page.get_by_role("heading", name="Saved preferences could not be checked")).to_be_visible()
    expect(page.get_by_role("button", name="Save preferences", exact=True)).to_have_count(0)
    page.goto("/")
    page.get_by_label("Your question").fill("Hello")
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.locator(".message-bot .answer").last).to_contain_text("Your current request takes priority")


def test_chat_memory_preview_is_explicit_and_cancel_does_not_erase_the_chat(
    page: Page, memory_server: tuple[str, BrowserMemory]
) -> None:
    """A request to remember offers typed fields; cancelling does not save or navigate away."""
    page.goto("/")
    page.get_by_label("Your question").fill(
        "Remember that I usually fly from DFW, prefer Fahrenheit, and enjoy easy hikes."
    )
    page.get_by_role("button", name="Send", exact=True).click()
    preview = page.locator(".memory-preview")
    expect(preview).to_be_visible()
    expect(preview.locator('[name="origin"]')).to_have_value("DFW")
    expect(preview.locator('[name="unit_system"]')).to_have_value("imperial")
    expect(preview.locator('[name="activity"]')).to_have_value("easy hikes")
    assert not memory_server[1].rows
    expect(page.locator(".answer .preference-form")).to_have_count(0)
    preview.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.locator(".memory-preview")).to_have_count(0)
    expect(page.locator(".message-user").last).to_contain_text("Remember that I usually fly from DFW")
    assert not memory_server[1].rows


def test_chat_preview_requires_consent_and_preserves_other_saved_fields(
    page: Page, memory_server: tuple[str, BrowserMemory]
) -> None:
    """An airport update offers the existing defaults, requires consent, and saves only the reviewed values."""
    save_preferences(page)
    page.goto("/")
    page.get_by_label("Your question").fill("Remember that I usually fly from ORD.")
    page.get_by_role("button", name="Send", exact=True).click()
    preview = page.locator(".memory-preview")
    expect(preview).to_be_visible()
    expect(preview.locator('[name="origin"]')).to_have_value("ORD")
    expect(preview.locator('[name="unit_system"]')).to_have_value("metric")
    expect(preview.locator('[name="activity"]')).to_have_value("easy hikes")
    expect(preview.locator('[name="depart_window"]')).to_have_value("evening")
    preview.get_by_role("button", name="Save preferences", exact=True).click()
    expect(preview).to_be_visible()
    assert {row.preferences.origin for row in memory_server[1].rows.values()} == {"DFW"}
    preview.locator('[name="consent"]').check()
    preview.get_by_role("button", name="Save preferences", exact=True).click()
    expect(page.get_by_text("Memory on", exact=True)).to_be_visible()
    expect(page.locator('input[name="origin"]')).to_have_value("ORD")
    assert len(memory_server[1].rows) == 1
    saved = next(iter(memory_server[1].rows.values())).preferences
    assert saved == PreferenceProfile(
        origin="ORD", unit_system="metric", currency="USD", activity="easy hikes", depart_window="evening"
    )


@pytest.mark.parametrize("width", [360, 1280])
def test_private_preferences_are_accessible_and_fit_the_screen(page: Page, width: int, tmp_path: Path) -> None:
    """Check the real opt-in form for keyboard semantics, contrast, console errors and horizontal overflow."""
    errors: list[str] = []

    def keep_errors(message: ConsoleMessage) -> None:
        """Keep browser errors without collecting conversation or saved values."""
        if message.type == "error":
            errors.append(message.text)

    page.on("console", keep_errors)
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/preferences")
    expect(page.get_by_role("heading", name="My preferences", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert errors == []
    capture = tmp_path / f"memory-preferences-{width}.png"
    page.screenshot(path=str(capture), full_page=True)
    page.goto("/")
    page.get_by_label("Your question").fill("Remember that I fly from DFW and prefer Fahrenheit.")
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.locator(".memory-preview")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert errors == []
    page.screenshot(path=str(capture.with_name(f"memory-preview-{width}.png")), full_page=True)
