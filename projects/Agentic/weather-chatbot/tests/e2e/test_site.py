"""
tests/e2e/test_site.py: the pages in a real browser: the menu, in its groups, takes you to each page and marks it,
the deprecated group folded until opened; the system design and a deprecated page show their diagrams, a deprecated
page keeps its links; the Observability pages show their numbers and their filters (step 14); no page logs an error (a
Content Security Policy refusal among them), every page passes axe's accessibility checks, and none scrolls sideways,
on a computer or a phone.
"""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Page, expect

from nimbus.docs import ALL_DOCS

# Every page: the chat, the two lists, each documentation page in the registry, and the Observability pages, one of
# Activity's views among them (step 14), and a link's narrowing (step 15).
OBSERVABILITY = [
    "/activity",
    "/activity?show=errors",
    "/activity?tool=get_forecast",
    "/performance",
    "/evaluations",
    "/health",
]
PAGES = ["/", "/docs", "/docs_deprecated", *(doc.path for doc in ALL_DOCS.values()), *OBSERVABILITY]
PHONE_WIDTH = 360
COMPUTER_WIDTH = 1280


def test_the_menu_opens_each_page_and_marks_it(page: Page) -> None:
    page.goto("/")
    expect(page.get_by_role("heading", name="Nimbus (Weather)")).to_be_visible()
    page.get_by_role("link", name="Documentation", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Documentation")).to_be_visible()
    expect(page.get_by_role("link", name="Documentation", exact=True)).to_have_attribute("aria-current", "page")
    page.get_by_role("link", name=re.compile(r"^Step 1:")).click()
    expect(page).to_have_url(re.compile(r"/docs/step-1$"))
    expect(page.get_by_role("link", name="Documentation", exact=True)).to_have_attribute("aria-current", "true")


def test_the_menu_shows_its_groups_and_folds_the_deprecated_pages_until_opened(page: Page) -> None:
    page.goto("/")
    menu = page.get_by_role("navigation", name="Main")
    for title in ("App", "Observability", "Learn", "Project", "Links"):
        expect(menu.get_by_role("list", name=title)).to_be_visible()
    expect(menu.get_by_role("link", name="Activity")).to_be_visible()
    folded = menu.get_by_role("link", name="System design_deprecated")
    expect(folded).to_be_hidden()
    menu.get_by_text("Deprecated", exact=True).click()
    expect(folded).to_be_visible()


def test_the_observability_pages_show_their_numbers_and_views(page: Page) -> None:
    page.goto("/")
    page.get_by_role("link", name="Performance", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="Performance")).to_be_visible()
    expect(page.get_by_role("meter", name="get_forecast")).to_have_attribute("value", "1.000")
    page.get_by_role("link", name="Activity", exact=True).click()
    page.get_by_role("navigation", name="Views").get_by_role("link", name="Errors").click()
    expect(page).to_have_url(re.compile(r"/activity\?show=errors$"))
    expect(page.get_by_role("link", name="Errors")).to_have_attribute("aria-current", "page")
    page.get_by_role("link", name="MCP server", exact=True).click()
    expect(page.get_by_role("heading", name="Our MCP server")).to_be_in_viewport()


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


def test_a_deprecated_page_says_so_and_keeps_its_diagram(page: Page) -> None:
    page.goto("/")
    page.get_by_text("Deprecated", exact=True).click()
    page.get_by_role("link", name="System design_deprecated").click()
    expect(page.get_by_role("note")).to_contain_text("Deprecated")
    diagram = page.get_by_role("img", name="How Nimbus is built today, steps 1 to 9")
    expect(diagram).to_be_visible()
    assert diagram.evaluate("img => img.naturalWidth") > 0


def test_the_system_design_shows_its_diagram(page: Page) -> None:
    page.goto("/")
    page.get_by_role("link", name="System design", exact=True).click()
    expect(page.get_by_role("heading", level=1, name="System Design")).to_be_visible()
    expect(page.get_by_role("link", name="System design", exact=True)).to_have_attribute("aria-current", "page")
    diagram = page.get_by_role("img", name=re.compile(r"^How Nimbus is built after step \d+$"))
    expect(diagram).to_be_visible()
    assert diagram.evaluate("img => img.naturalWidth") > 0


def test_follows_a_github_style_link_between_deprecated_pages(page: Page) -> None:
    page.goto("/docs_deprecated/step-2_deprecated")
    page.get_by_role("link", name="step 3", exact=True).click()
    expect(page).to_have_url(re.compile(r"/docs_deprecated/step-3_deprecated$"))


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
    page.goto("/docs_deprecated")
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
