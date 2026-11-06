"""Follow the normal chat-to-plan journey on a phone, with an independent provider failure."""

from datetime import UTC, datetime, timedelta

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect


@pytest.mark.parametrize(
    ("base_url", "hotels_enabled"),
    [("travel", True), ("flights-only", False)],
    indirect=["base_url"],
)
def test_plan_from_chat_has_verified_fare_and_independent_sections(
    page: Page,
    base_url: str,
    hotels_enabled: bool,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion National Park")
    box.press("Enter")
    form = page.locator('form[action="/api/parks/trip"]')
    expect(form.locator('[name="park"]')).to_have_value("zion")
    expect(form.get_by_label("Rooms", exact=True)).to_have_count(int(hotels_enabled))
    start = datetime.now(UTC).date() + timedelta(days=40)
    for key, value in {
        "arrival": start.isoformat(),
        "departure": (start + timedelta(days=3)).isoformat(),
        "origin": "ORD",
        "gateway": "LAS",
    }.items():
        form.locator(f'[name="{key}"]').fill(value)
    form.locator('[name="transport"]').select_option("fly")
    form.get_by_role("button", name="Build my trip plan").click()
    expect(page).to_have_url(f"{base_url}/api/parks/trip")
    for name in (
        "Flights",
        "Hotels near the park",
        "Weather for your visit",
        "Park preparation guidance",
        "Current official notices",
    ):
        expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()
    expect(page.get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    if hotels_enabled:
        expect(page.get_by_label("Trivago search results")).to_contain_text("rate limited")
    else:
        expect(page.get_by_text("Hotel search is disabled for this plan.")).to_be_visible()
        expect(page.get_by_label("Trivago search results")).to_have_count(0)
    expect(page.get_by_text("Synthetic maintenance", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
