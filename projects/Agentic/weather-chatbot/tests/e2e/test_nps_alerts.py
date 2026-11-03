"""Park notices are readable and accessible on desktop and phones, with no secret in the browser."""

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


@pytest.mark.parametrize("park", ["zion", "yosemite", "grand-canyon"])
def test_notice_cards_empty_results_and_failures_fit_a_phone(page: Page, park: str) -> None:
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Park alerts", exact=True).click()
    expect(page.get_by_role("heading", name="Park alerts", level=1)).to_be_visible()
    page.get_by_label("Park", exact=True).select_option(park)
    page.get_by_role("button", name="Check alerts").click()
    expect(page).to_have_url("/api/parks/alerts")
    if park == "zion":
        expect(page.get_by_text("Synthetic maintenance", exact=True)).to_be_visible()
        expect(page.locator(".nps-indexed")).to_contain_text("Last indexed by NPS")
        expect(page.locator(".nps-report")).to_contain_text("Fetched")
    elif park == "yosemite":
        expect(page.locator(".nps-report")).to_contain_text("No notices were returned")
    else:
        expect(page.locator(".nps-report")).to_contain_text("could not be completed")
    expect(page.locator(".nps-scope")).to_contain_text("not an opening or safety guarantee")
    assert "synthetic-nps-key" not in page.content()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    result = Axe().run(page)
    assert result.violations_count == 0, result.generate_report()


def test_throttled_form_keeps_the_page_usable_and_accessible(page: Page) -> None:
    """A browser form refusal stays readable HTML with the selected park and the real retry status."""
    page.set_viewport_size({"width": 360, "height": 800})
    page.goto("/parks/alerts")
    for _ in range(12):
        page.request.post("/api/parks/alerts", form={"park": "zion"})
    page.get_by_label("Park", exact=True).select_option("yosemite")
    with page.expect_response("**/api/parks/alerts") as result:
        page.get_by_role("button", name="Check alerts").click()
    assert result.value.status == 429
    assert result.value.headers["retry-after"] == "60"
    expect(page.get_by_role("alert")).to_contain_text("Too many park alert checks")
    expect(page.get_by_label("Park", exact=True)).to_have_value("yosemite")
    expect(page.get_by_role("button", name="Check alerts")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    report = Axe().run(page)
    assert report.violations_count == 0, report.generate_report()
