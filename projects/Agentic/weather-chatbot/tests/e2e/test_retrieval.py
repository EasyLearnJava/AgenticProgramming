"""A visitor runs and inspects real retrieval from Knowledge, including keyboard access and phone layouts."""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


def run_question(page: Page) -> None:
    """Submit a preparation question using the same fields a visitor uses."""
    page.get_by_label("Question", exact=True).fill("What clothing should I pack for cold water?")
    page.get_by_label("Park or trail", exact=True).select_option("zion-narrows")
    page.get_by_label("Visit date (optional)", exact=True).fill("2026-12-01")
    page.get_by_role("button", name="Run retrieval", exact=True).click()
    expect(page.get_by_role("heading", name="Retrieval results", exact=True)).to_be_visible(timeout=10000)
    assert "?" not in page.url
    expect(page).to_have_url(re.compile(r"/api/knowledge/retrieval$"))


def test_playground_runs_from_the_sidebar_and_links_scores_to_actual_passages(page: Page) -> None:
    page.goto("/")
    navigation = page.get_by_role("navigation", name="Main")
    navigation.get_by_role("link", name="Retrieval Playground", exact=True).click()
    expect(navigation.get_by_role("link", name="Retrieval Playground")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("heading", name="No question run yet")).to_be_visible()
    run_question(page)
    expect(page.locator("#retrieval-ranking")).to_be_visible()
    expect(page.get_by_label("Visit date (optional)", exact=True)).to_have_value("2026-12-01")
    count = page.locator(".retrieval-passage").count()
    assert 1 <= count <= 4
    row = page.locator('#retrieval-ranking tr[data-selection="retrieved"]').first
    row.get_by_role("link").click()
    expect(page).to_have_url(re.compile(r"#retrieved-"))
    page.get_by_role("link", name="Inspect chunk & vector →", exact=True).first.click()
    expect(page).to_have_url(re.compile(r"/knowledge/chunks\?chunk="))
    expect(page.locator("#chunk-detail")).to_be_in_viewport()


@pytest.mark.parametrize("width", [1440, 360])
def test_playground_and_results_are_accessible_and_fit_the_viewport(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto("/knowledge/retrieval")
    result = Axe().run(page)
    assert result.violations_count == 0, result.generate_report()
    run_question(page)
    page.get_by_text("How to read the scores", exact=True).click()
    result = Axe().run(page)
    assert result.violations_count == 0, result.generate_report()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("link", name="Reset", exact=True).click()
    expect(page.get_by_label("Question", exact=True)).to_have_value("")
    expect(page.get_by_role("heading", name="No question run yet")).to_be_visible()
