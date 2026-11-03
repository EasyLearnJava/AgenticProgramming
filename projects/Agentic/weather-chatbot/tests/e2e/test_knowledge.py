"""Knowledge navigation, actual source text, vector selection, accessibility, and mobile layout in a browser."""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


def test_sources_can_be_filtered_and_opened_from_the_sidebar(page: Page) -> None:
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Source documents", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Source documents")).to_be_visible()
    expect(page.locator(".knowledge-source-card")).to_have_count(13)
    page.get_by_label("Park", exact=True).select_option("yosemite")
    page.get_by_label("Search documents", exact=True).fill("lightning")
    page.get_by_role("button", name="Apply filters").click()
    expect(page.locator(".knowledge-source-card")).to_have_count(1)
    page.get_by_role("link", name="Read indexed text").click()
    expect(page.get_by_role("heading", level=2, name="Indexed passages")).to_be_visible()
    expect(page.locator(".knowledge-passage").first).to_contain_text(re.compile("lightning", re.I))


def test_clicking_a_real_vector_selects_its_chunk_and_exposes_components(page: Page) -> None:
    page.goto("/knowledge/chunks")
    points = page.locator("#embedding-map a")
    expect(points).to_have_count(40)
    href = points.nth(2).get_attribute("href")
    assert href is not None
    points.nth(2).focus()
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(re.escape(href)))
    expect(page.locator("#chunk-detail")).to_be_in_viewport()
    page.get_by_text("Vector components (384)", exact=True).click()
    expect(page.locator(".knowledge-vector pre")).to_be_visible()
    expect(page.locator(".knowledge-row-selected")).to_have_count(1)
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


@pytest.mark.parametrize("path", ["/knowledge/sources", "/knowledge/chunks", "/knowledge/sources/zion-narrows-safety"])
def test_knowledge_pages_pass_accessibility_and_fit_a_phone(page: Page, path: str) -> None:
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto(path)
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
