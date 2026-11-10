"""The park source card in a browser: cited guidance, keyboard access, accessibility, and a narrow screen."""

from collections.abc import Iterator

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect

from tests.fakes import FakeModel


@pytest.fixture
def park_answer(chat_model: FakeModel) -> Iterator[None]:
    """Make the model retrieve recorded remote Narrows guidance, restoring the shared model after the test."""
    previous_steps, previous_answer = chat_model.tool_steps, chat_model.answer
    chat_model.tool_steps = [
        [{"name": "resolve_destination", "args": {"query": "Zion Narrows"}}],
        [
            {
                "name": "search_park_guidance",
                "args": {"destination_id": "zion-narrows", "query": "warm clothing dry bag"},
            }
        ],
    ]
    chat_model.answer = (
        "Check the park's [Narrows preparation guide](https://www.nps.gov/zion/planyourvisit/narrowssafety.htm). "
        "Current closures have not been checked."
    )
    try:
        yield
    finally:
        chat_model.tool_steps, chat_model.answer = previous_steps, previous_answer


def test_park_guidance_shows_accessible_sources_and_fits_a_phone(page: Page, park_answer: None) -> None:
    """Render actual indexed passages through the agent and source card, without external model or weather calls."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    box = page.get_by_label("Your question")
    box.fill("What should I pack for the Zion Narrows?")
    box.press("Enter")
    expect(page.locator(".message-bot .answer").last).to_contain_text("Current closures have not been checked.")
    expect(page.locator('.message-bot[aria-busy="true"]')).to_have_count(0)
    card = page.locator(".tool-chip").filter(has=page.get_by_text("search_park_guidance", exact=True))
    expect(card).to_have_count(1)
    card.locator("summary").focus()
    page.keyboard.press("Enter")
    expect(card.get_by_text("Park guidance sources", exact=True)).to_be_visible()
    expect(card.locator('a[href="https://www.nps.gov/zion/planyourvisit/narrowssafety.htm"]')).to_be_visible()
    expect(card.get_by_text("On the wire", exact=True)).to_have_count(0)
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
