"""Build and edit a trip in its chat turn, or submit the standalone planner as a full page."""

import json
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Locator, Page, expect

from nimbus.nws_alerts import NwsAlertsService, NwsReport, WeatherWarning
from nimbus.parks import Destination
from nimbus.travel import briefing
from nimbus.travel.service import TravelService

# Start a fresh server for each travel case so other visitors in the suite cannot exhaust its rate limit.
INTAKE = 'form.trip-form[action="/api/parks/briefing"]'
QUOTES = 'form[action="/api/parks/trip"]'


@pytest.mark.parametrize("base_url", ["travel", "weather-only"], indirect=True, scope="function")
def test_city_trip_asks_for_dates_and_keeps_context_for_the_follow_up(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(base_url)
    question = "plan a trip to dallas"
    box = page.get_by_label("Your question")
    box.fill(question)
    box.press("Enter")
    turn = page.locator('li[id^="turn-"]')
    answer = turn.locator(".answer")
    expect(answer).to_contain_text(re.compile("Dallas", re.I))
    expect(answer).to_contain_text(re.compile(r"dates|when", re.I))
    expect(turn.locator(".tool-chip")).to_have_count(0)
    expect(turn.locator(INTAKE)).to_have_count(0)
    expect(turn.get_by_text("Give feedback", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Send", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    first_reply = answer.inner_text().strip()

    # The real browser should send the completed city clarification with the next question.
    box.fill("Can you check the forecast there for tomorrow?")
    with page.expect_request(lambda req: req.url.endswith("/api/chat") and req.method == "POST") as sent:
        box.press("Enter")
    fields = sent.value.post_data_json
    assert isinstance(fields, dict)
    assert json.loads(fields["history"]) == [
        {"role": "user", "text": question},
        {"role": "assistant", "text": first_reply},
    ]
    expect(turn.nth(1).locator(".tool-chip-done .tool-chip-name").filter(has_text="get_forecast")).to_be_visible()


def open_quotes(turn: Locator) -> Locator:
    """Choose to continue only after conditions are visible and the quote editor is collapsed."""
    expect(turn.get_by_role("heading", name="Official weather alerts")).to_be_visible()
    form = turn.locator(QUOTES)
    expect(form).to_be_hidden()
    turn.locator("summary").filter(has_text=re.compile("travel options", re.I)).click()
    expect(form).to_be_visible()
    return form


def fill_trip(form: Locator) -> None:
    """Use concrete dates and the airports matched by the local travel recordings."""
    start = datetime.now(UTC).date() + timedelta(days=40)
    form.locator('[name="transport"]').select_option("fly")
    for key, value in {
        "arrival": start.isoformat(),
        "departure": (start + timedelta(days=3)).isoformat(),
        "origin": "ORD",
        "gateway": "LAS",
    }.items():
        form.locator(f'[name="{key}"]').fill(value)


@pytest.mark.parametrize(
    ("base_url", "hotels_enabled", "width"),
    [("travel", True, 390), ("flights-only", False, 1280)],
    indirect=["base_url"],
    scope="function",
)
def test_plan_from_chat_has_verified_fare_and_independent_sections(
    page: Page,
    base_url: str,
    hotels_enabled: bool,
    width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion National Park")
    box.press("Enter")
    form = page.locator(INTAKE)
    expect(form.locator('[name="park"]')).to_have_value("zion")
    expect(form.get_by_label("Rooms", exact=True)).to_have_count(int(hotels_enabled))
    fill_trip(form)
    assert form.evaluate("f => f.scrollWidth <= f.clientWidth")
    form_audit = Axe().run(page)
    assert form_audit.violations_count == 0, form_audit.generate_report()
    box.fill("A follow-up I am drafting")
    turn_id = form.locator("xpath=ancestor::li[starts-with(@id, 'turn-')]").get_attribute("id")
    assert turn_id is not None
    turn = page.locator(f"#{turn_id}")
    quote_requests: list[str] = []
    page.on("request", lambda req: quote_requests.append(req.url) if req.url.endswith("/api/parks/trip") else None)
    with page.expect_response(f"{base_url}/api/parks/briefing") as submission:
        form.get_by_role("button", name="Build my trip plan").click()
    assert submission.value.request.method == "POST"
    assert not submission.value.request.is_navigation_request()
    assert page.context.pages == [page]
    expect(page).to_have_url(f"{base_url}/")
    expect(box).to_have_value("A follow-up I am drafting")
    expect(page.get_by_text("Plan a trip to Zion National Park", exact=True)).to_be_visible()
    quotes = open_quotes(turn)
    assert quote_requests == []
    expect(quotes.get_by_label("Flying from")).to_have_value("ORD")
    expect(quotes.get_by_label("Flying into")).to_have_value("LAS")
    briefing_audit = Axe().run(page)
    assert briefing_audit.violations_count == 0, briefing_audit.generate_report()
    with page.expect_response(f"{base_url}/api/parks/trip") as search:
        quotes.get_by_role("button", name=re.compile("^Search flights")).click()
    assert not search.value.request.is_navigation_request()
    assert len(quote_requests) == 1
    for name in (
        "Flights",
        "Hotels near the park",
        "Weather for your visit",
        "Park preparation guidance",
        "Current official notices",
    ):
        expect(turn.get_by_role("heading", name=name, exact=True)).to_be_visible()
    expect(page.get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    if hotels_enabled:
        expect(page.get_by_label("Trivago search results")).to_contain_text("rate limited")
    else:
        expect(page.get_by_text("Hotel search is disabled for this plan.")).to_be_visible()
        expect(page.get_by_label("Trivago search results")).to_have_count(0)
    expect(turn.locator(".trip-inline-result").get_by_text("Synthetic maintenance", exact=True)).to_be_visible()
    expect(quotes).to_be_hidden()
    assert page.context.pages == [page]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    audit = Axe().run(page)
    assert audit.violations_count == 0, audit.generate_report()


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_hotel_only_then_edit_flight_windows_in_the_same_briefing(
    page: Page, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 5, 18, tzinfo=UTC))
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion this weekend")
    box.press("Enter")
    turn = page.locator("li.trip-message")
    expect(turn.get_by_role("heading", name="Trip conditions · Zion")).to_be_focused()
    form = open_quotes(turn)
    mode = form.get_by_label("Search for")
    expect(mode).to_have_value("true")
    expect(form.get_by_label("Flying from")).to_be_disabled()
    # Hotel-only mode disables flight controls, but preparation, units and currency remain editable.
    expect(form.get_by_label("Weather units")).to_be_visible()
    expect(form.get_by_label("Weather units")).to_be_enabled()
    form.get_by_label("Weather units").select_option("imperial")
    form.get_by_label("Price currency").select_option("EUR")
    form.get_by_label("Activity or preparation topic").fill("camping")
    with page.expect_response("**/api/parks/trip") as sent:
        form.get_by_role("button", name="Search hotels", exact=True).click()
    assert sent.value.status == 200
    body = sent.value.request.post_data or ""
    assert "skip_flights=true" in body
    assert "gateway=" not in body
    assert "unit_system=imperial" in body
    assert "currency=EUR" in body
    assert "activity=camping" in body
    # Reopen the same form and switch to flights. An evening preference must be editable before retrying a search.
    expect(form).to_be_hidden()
    turn.locator("summary").filter(has_text=re.compile("travel options", re.I)).click()
    mode.select_option("false")
    expect(form.get_by_label("Flying from")).to_be_enabled()
    form.get_by_label("Departure at your origin").select_option("")
    form.get_by_label("Arrival back at your origin").select_option("by_noon")
    form.get_by_label("Flying from").fill("ORD")
    form.get_by_label("Flying into").select_option("LAS")
    with page.expect_response("**/api/parks/trip") as flight_search:
        form.get_by_role("button", name="Search flights and hotels").click()
    assert flight_search.value.status == 200
    assert "return_window=by_noon" in (flight_search.value.request.post_data or "")
    assert "skip_flights=false" in (flight_search.value.request.post_data or "")


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_typed_park_choice_keeps_the_previous_trip_in_chat(
    page: Page, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 5, 18, tzinfo=UTC))
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion or Yosemite this weekend from DFW, back by 3pm Sunday.")
    box.press("Enter")
    expect(page.get_by_text("Which park do you want to visit?")).to_be_visible()
    box.fill("Zion")
    box.press("Enter")
    turn = page.locator("li.trip-message").last
    expect(turn.get_by_role("heading", name="Trip conditions · Zion")).to_be_visible()
    expect(turn.locator(".brief-dates")).to_contain_text("from DFW")
    quotes = open_quotes(turn)
    expect(quotes.get_by_label("Arrival back at your origin")).to_have_value("by_15:00")


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_edit_rebuild_and_validation_stay_in_the_right_turn(page: Page, base_url: str) -> None:
    page.goto(base_url)
    box = page.get_by_label("Your question")
    # Keep a second planner open so a global target or a reused field id cannot pass this test.
    for park in ("Zion", "Yosemite"):
        box.fill(f"Plan a trip to {park} National Park")
        box.press("Enter")
        expect(page.locator(f'form select[name="park"] option[value="{park.lower()}"]:checked')).to_have_count(1)
    planners = page.locator("li.trip-message")
    first = planners.first
    other = planners.last
    form = first.locator(INTAKE)
    fill_trip(form)
    form.get_by_role("button", name="Build my trip plan").press("Enter")
    quotes = open_quotes(first)
    quotes.locator('[name="gateway"]').fill("ORD")
    build = quotes.get_by_role("button", name="Search flights and hotels")
    build.press("Enter")
    expect(first.get_by_role("alert")).to_contain_text("different departure and arrival")
    expect(quotes.locator('[name="gateway"]')).to_have_value("ORD")
    expect(other.get_by_role("alert")).to_have_count(0)
    quotes.locator('[name="gateway"]').fill("LAS")
    build.click()
    expect(first.get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    expect(first.get_by_role("alert")).to_have_count(0)
    expect(other.get_by_role("heading", name="Flights", exact=True)).to_have_count(0)
    expect(other.locator(INTAKE)).to_be_visible()
    first.locator("summary").filter(has_text="Change travel dates").press("Enter")
    date_editor = first.locator(".brief-edit form")
    revised_end = datetime.now(UTC).date() + timedelta(days=45)
    date_editor.locator('[name="departure"]').fill(revised_end.isoformat())
    date_editor.get_by_role("button", name="Check these dates").click()
    expect(first.get_by_text("Synthetic round trip", exact=True)).to_have_count(0)
    quotes = open_quotes(first)
    expect(quotes.locator('[name="departure"]')).to_have_value(revised_end.isoformat())
    expect(quotes.locator('[name="gateway"]')).to_have_value("LAS")
    quotes.get_by_role("button", name="Search flights and hotels").click()
    expect(first.get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    expect(other.locator(INTAKE)).to_be_visible()
    expect(page).to_have_url(f"{base_url}/")
    assert page.context.pages == [page]


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_chat_retries_after_network_and_firewall_failures(page: Page, base_url: str) -> None:
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion")
    box.press("Enter")
    form = page.locator(INTAKE)
    fill_trip(form)
    build = form.get_by_role("button", name="Build my trip plan")
    page.route("**/api/parks/briefing", lambda route: route.abort(), times=1)
    build.click()
    expect(form.get_by_role("status")).to_contain_text("reach Nimbus")
    page.route(
        "**/api/parks/briefing",
        lambda route: route.fulfill(status=429, content_type="text/html", body="<h1>Untrusted upstream message</h1>"),
        times=1,
    )
    build.click()
    expect(form.get_by_role("status")).to_contain_text("busy")
    expect(page.get_by_text("Untrusted upstream message", exact=True)).to_have_count(0)
    expect(form.locator('[name="origin"]')).to_have_value("ORD")
    build.click()
    quotes = open_quotes(page.locator("li.trip-message"))
    search = quotes.get_by_role("button", name="Search flights and hotels")
    page.route("**/api/parks/trip", lambda route: route.abort(), times=1)
    search.click()
    expect(quotes.get_by_role("status")).to_contain_text("connection")
    search.click()
    expect(page.get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    expect(page).to_have_url(f"{base_url}/")
    assert page.context.pages == [page]


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_dated_typo_request_opens_conditions_and_honors_declined_quotes(
    page: Page, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the visitor's wording in the browser, with a stable Thursday in Dallas."""
    monkeypatch.setattr(briefing, "utc_now", lambda: datetime(2026, 11, 5, 18, tzinfo=UTC))
    start_quotes = Mock(side_effect=AssertionError("No flight or hotel search was requested"))
    monkeypatch.setattr(TravelService, "new_turn", start_quotes)
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Play a trip to Zion this week end from DFW, but no flights or hotels.")
    box.press("Enter")
    turn = page.locator("li.trip-message")
    expect(turn.get_by_role("heading", name="Trip conditions · Zion")).to_be_visible()
    expect(turn.locator(".brief-dates")).to_contain_text("Nov 06, 2026")
    expect(turn.locator(".brief-dates")).to_contain_text("Nov 08, 2026")
    expect(turn.locator(".brief-dates")).to_contain_text("from DFW")
    expect(turn.get_by_role("heading", name="Weather for your dates")).to_be_visible()
    expect(turn.get_by_role("heading", name="Official weather alerts")).to_be_visible()
    expect(turn.get_by_role("heading", name="Current park notices")).to_be_visible()
    expect(turn.locator(INTAKE)).to_have_count(0)
    expect(turn.locator(QUOTES)).to_have_count(0)
    start_quotes.assert_not_called()
    expect(page).to_have_url(f"{base_url}/")


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_manual_dates_and_weekend_picker_pause_before_quotes(
    page: Page, base_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A severe recorded warning applies on both the manual-date path and the Saturday park picker."""
    saturday = datetime(2026, 11, 7, 16, tzinfo=UTC)
    monkeypatch.setattr(briefing, "utc_now", lambda: saturday)
    warning = WeatherWarning(
        "Flash Flood Warning",
        "Recorded warning",
        "Test area",
        "Severe",
        saturday - timedelta(hours=2),
        saturday + timedelta(days=3),
    )

    async def warnings(_self: NwsAlertsService, _point: Destination) -> NwsReport:
        return NwsReport((warning,), True, saturday, "https://www.weather.gov/")

    monkeypatch.setattr(NwsAlertsService, "get", warnings)
    start_quotes = Mock(side_effect=AssertionError("Conditions must precede both travel providers"))
    monkeypatch.setattr(TravelService, "new_turn", start_quotes)
    page.goto(base_url)
    box = page.get_by_label("Your question")
    box.fill("Plan a trip to Zion")
    box.press("Enter")
    first = page.locator("li.trip-message").first
    manual = first.locator(INTAKE)
    manual.locator('[name="arrival"]').fill("2026-11-07")
    manual.locator('[name="departure"]').fill("2026-11-08")
    manual.locator('[name="transport"]').select_option("drive")
    manual.get_by_role("button", name="Build my trip plan").click()
    expect(first.get_by_role("heading", name="Trip conditions · Zion")).to_be_focused()
    expect(first.locator('[data-brief-decision="pause"]')).to_be_visible()
    expect(first.get_by_text("Flash Flood Warning", exact=True)).to_be_visible()
    expect(first.locator(QUOTES)).to_have_count(0)
    box.fill("Plan a trip to Zion or Yosemite this weekend from DFW")
    box.press("Enter")
    turns = page.locator("li.trip-message")
    expect(turns).to_have_count(2)
    choice = turns.last
    choice.get_by_label("Travel dates").select_option("2026-11-07/2026-11-08")
    choice.get_by_role("button", name="Yosemite").click()
    expect(choice.get_by_role("heading", name="Trip conditions · Yosemite")).to_be_visible()
    expect(choice.locator('[data-brief-decision="pause"]')).to_be_visible()
    expect(choice.get_by_text(re.compile("from DFW", re.I)).first).to_be_visible()
    expect(choice.locator(QUOTES)).to_have_count(0)
    start_quotes.assert_not_called()
    expect(page).to_have_url(f"{base_url}/")
    assert page.context.pages == [page]


@pytest.mark.parametrize("base_url", ["travel"], indirect=True, scope="function")
def test_standalone_trip_submission_remains_full_page(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/parks/trip?park=zion")
    form = page.locator('form[action="/api/parks/trip"]')
    fill_trip(form)
    form.get_by_role("button", name="Build my trip plan").click()
    expect(page).to_have_url(f"{base_url}/api/parks/trip")
    expect(page.get_by_role("main").get_by_text("Synthetic round trip", exact=True)).to_be_visible()
    assert page.context.pages == [page]
