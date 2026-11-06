"""A visitor chooses what to send and stays in the same chat, including when a feedback request fails."""

from urllib.parse import parse_qs

from playwright.sync_api import Page, expect


def test_feedback_is_opt_in_and_private(page: Page, base_url: str) -> None:
    page.goto(base_url)
    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.post_data or "") if req.url.endswith("/api/feedback") else None)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion")
    box.press("Enter")
    panel = page.locator(".answer-feedback")
    panel.locator("summary").click()
    panel.get_by_label("How was this answer?").select_option("trip-dates")
    assert requests == []
    page.route("**/api/feedback", lambda route: route.abort(), times=1)
    send = panel.get_by_role("button", name="Send feedback")
    send.click()
    expect(panel.get_by_role("status")).to_contain_text("try again")
    send.click()
    expect(panel.get_by_role("status")).to_have_text("Feedback received.")
    expect(send).to_be_disabled()
    assert len(requests) == 2
    payload = parse_qs(requests[-1])
    assert set(payload) == {"turn", "category"}
    assert payload["category"] == ["trip-dates"]
    expect(page).to_have_url(f"{base_url}/")
