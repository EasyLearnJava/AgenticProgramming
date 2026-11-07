"""
tests/e2e/test_site.py: the pages in a real browser: the menu, in its groups, takes you to each page and marks it,
the system design shows its diagram; the Observability pages show their numbers and their filters (step 14);
no page logs an error (including Content Security Policy refusals), every page passes axe's accessibility checks,
and none scrolls sideways
on a computer or a phone.
"""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Page, expect

from nimbus.docs import ALL_DOCS

# Every published documentation page, the chat, the index, Observability, and filtered Activity views.
OBSERVABILITY = [
    "/activity",
    "/activity?show=errors",
    "/activity?tool=get_forecast",
    "/performance",
    "/evaluations",
    "/health",
]
PAGES = ["/", "/docs", *(doc.path for doc in ALL_DOCS.values()), *OBSERVABILITY]
PHONE_WIDTH = 360
COMPUTER_WIDTH = 1280


def test_the_menu_opens_each_page_and_marks_it(page: Page) -> None:
    page.goto("/")
    expect(page.get_by_role("heading", name="Nimbus", exact=True)).to_be_visible()
    page.get_by_role("link", name="Documentation", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Documentation")).to_be_visible()
    expect(page.get_by_role("link", name="Documentation", exact=True)).to_have_attribute("aria-current", "page")
    page.get_by_role("link", name=re.compile(r"^Step 1:")).click()
    expect(page).to_have_url(re.compile(r"/docs/step-1$"))
    expect(page.get_by_role("link", name="Documentation", exact=True)).to_have_attribute("aria-current", "true")


def test_the_menu_groups_current_links_and_offers_both_project_endpoints(page: Page) -> None:
    page.goto("/")
    menu = page.get_by_role("navigation", name="Main")
    for title in ("App", "Knowledge", "Observability", "Learn", "Project"):
        expect(menu.get_by_role("list", name=title)).to_be_visible()
    expect(menu.get_by_role("link", name="Activity")).to_be_visible()
    expect(menu.get_by_text("Deprecated", exact=True)).to_have_count(0)
    expect(menu.locator('a[href*="_deprecated"]')).to_have_count(0)
    project = menu.get_by_role("list", name="Project")
    expect(project.get_by_role("link", name="Health check (JSON)")).to_have_attribute("href", "/api/health")
    expect(project.get_by_role("link", name="Weather MCP server")).to_have_attribute("href", "/health#mcp-server")


def test_the_observability_pages_show_their_numbers_and_views(page: Page) -> None:
    page.goto("/")
    page.get_by_role("link", name="Performance", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Performance")).to_be_visible()
    expect(page.get_by_role("meter", name="get_forecast")).to_have_attribute("value", "1.000")
    tools = page.locator('section[aria-labelledby="tools"]')
    forecast = tools.locator("li").filter(has_text="get_forecast")
    expect(forecast).to_contain_text("435 ms average")
    expect(forecast).to_contain_text("12 calls, 0 failed")
    geocode = tools.locator("li").filter(has_text="geocode_location")
    expect(geocode).to_contain_text("200 ms average")
    expect(geocode).to_contain_text("12 calls, 1 failed")
    expect(page.get_by_role("meter", name="From our cache")).to_have_attribute("value", "0.750")
    page.get_by_role("link", name="Activity", exact=True).click()
    page.get_by_role("navigation", name="Views").get_by_role("link", name="Errors").click()
    expect(page).to_have_url(re.compile(r"/activity\?show=errors$"))
    expect(page.get_by_role("link", name="Errors")).to_have_attribute("aria-current", "page")
    failed = page.locator("details.obs-details").filter(has_text="Ref 11112222")
    failed.locator("summary").click()
    expect(failed).to_contain_text("UpstreamTimeoutError")
    expect(failed).to_contain_text("after 8.0 s")
    expect(failed).to_contain_text("ModelBusyError")
    page.get_by_role("link", name="Weather MCP server", exact=True).click()
    expect(page.get_by_role("heading", name="Weather MCP server", exact=True)).to_be_in_viewport()


def test_a_row_elsewhere_links_to_its_questions_and_each_opens_onto_its_timeline(page: Page) -> None:
    page.goto("/performance")
    page.get_by_role("link", name="get_forecast", exact=True).click()
    expect(page).to_have_url(re.compile(r"/activity\?tool=get_forecast$"))
    expect(page.get_by_text("Questions that called get_forecast.")).to_be_visible()
    step = page.get_by_text("+4.6 s", exact=True)
    expect(step).to_be_hidden()
    page.locator("summary").filter(has_text="Answered in 5.8 s").click()
    expect(step).to_be_visible()
    expect(page.get_by_text("Ref 0a1b2c3d")).to_be_visible()
    page.get_by_role("link", name="Show them all").click()
    expect(page).to_have_url(re.compile(r"/activity$"))
    # A day's link, not followed: the recorded day leaves the 7 days, and its page is then a 404.
    page.goto("/health")
    day = page.get_by_role("link", name="Sunday 1 November")
    expect(day).to_have_attribute("href", "/activity?show=errors&day=2026-11-01")


def test_the_system_design_shows_its_diagram(page: Page) -> None:
    page.goto("/")
    page.get_by_role("link", name="System design", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="System Design")).to_be_visible()
    expect(page.get_by_role("link", name="System design", exact=True)).to_have_attribute("aria-current", "page")
    diagram = page.get_by_role("img", name=re.compile(r"^How a dated park request"))
    expect(diagram).to_be_visible()
    assert diagram.evaluate("img => img.naturalWidth") > 0


def test_an_old_bookmark_leads_to_the_missing_page_and_back_to_chat(page: Page) -> None:
    response = page.goto("/docs_deprecated/step-3_deprecated")
    assert response is not None
    assert response.status == 404
    expect(page.get_by_role("heading", level=1, name="Page not found")).to_be_visible()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Chat", exact=True).click()
    expect(page.get_by_role("heading", name="Nimbus", exact=True)).to_be_visible()


@pytest.mark.parametrize("path", PAGES)
def test_logs_no_error_in_the_browser(page: Page, path: str) -> None:
    errors: list[str] = []

    def keep_errors(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", keep_errors)
    page.goto(path)
    page.wait_for_load_state("networkidle")
    assert errors == []


@pytest.mark.parametrize("path", PAGES)
def test_has_no_accessibility_violations(page: Page, path: str) -> None:
    page.goto(path)
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


@pytest.mark.parametrize("width", [COMPUTER_WIDTH, PHONE_WIDTH])
def test_every_menu_link_fits_inside_the_menu(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 800})
    page.goto("/docs")
    too_wide = page.eval_on_selector_all(
        ".side-menu-link", "links => links.filter(l => l.scrollWidth > l.clientWidth).map(l => l.textContent.trim())"
    )
    assert too_wide == []


@pytest.mark.parametrize("width", [COMPUTER_WIDTH, PHONE_WIDTH])
@pytest.mark.parametrize("path", PAGES)
def test_never_scrolls_sideways(page: Page, path: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(path)
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
