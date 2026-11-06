"""Follow a trace from Activity inside Nimbus, including a keyboard-only visit and a pending upload."""

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.parametrize("base_url", ["trace"], indirect=True)


@pytest.mark.parametrize("width", [360, 1280])
def test_activity_opens_its_own_trace_with_model_tool_timings_and_error(page: Page, base_url: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    page.goto(f"{base_url}/activity")
    request = page.locator("details.obs-details").filter(has_text="Ref 11111111")
    request.locator("summary").focus()
    page.keyboard.press("Enter")
    trace = request.get_by_role("link", name="View LangSmith trace for request 11111111")
    expect(trace).to_be_visible()
    assert not any("/activity/trace/" in url for url in seen)
    trace.press("Enter")
    expect(page.get_by_role("heading", level=1, name="LangSmith trace")).to_be_visible()
    assert page.url.startswith(f"{base_url}/activity/trace/")
    expect(page.get_by_role("navigation", name="Main").get_by_role("link", name="Activity")).to_have_attribute(
        "aria-current", "page"
    )
    timeline = page.get_by_role("table", name="Call timeline")
    model = timeline.get_by_role("row").filter(has_text="Gemini")
    for part in ("Model", "+30 ms", "880 ms", "Completed"):
        expect(model).to_contain_text(part)
    tool = timeline.get_by_role("row").filter(has_text="get_forecast")
    for part in ("Tool", "+920 ms", "12 ms", "Failed", "Tool call failed"):
        expect(tool).to_contain_text(part)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()
    page.get_by_role("link", name="Back to Activity").click()
    expect(page).to_have_url(f"{base_url}/activity")


def test_pending_trace_can_be_refreshed_and_legacy_request_has_no_trace_link(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/activity")
    legacy = page.locator("details.obs-details").filter(has_text="Ref 33333333")
    legacy.locator("summary").click()
    expect(legacy.get_by_text("No linked LangSmith trace for this request.")).to_be_visible()
    expect(legacy.get_by_role("link")).to_have_count(0)
    pending = page.locator("details.obs-details").filter(has_text="Ref 22222222")
    pending.locator("summary").click()
    pending.get_by_role("link", name="View LangSmith trace for request 22222222").click()
    expect(page.get_by_role("note")).to_contain_text("no visible calls")
    same_trace = page.url
    page.get_by_role("link", name="Refresh trace").click()
    expect(page).to_have_url(same_trace)
    expect(page.get_by_role("note")).to_contain_text("no visible calls")
