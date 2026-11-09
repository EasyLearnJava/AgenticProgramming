"""Weather cards use real chat rendering with synthetic data, preserving prose, history and accessible layout."""

import json
import re
from datetime import datetime
from pathlib import Path

import httpx2
import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Page, expect

from tests.fakes import FakeModel, OpenMeteoRecordings

QUESTION = "Dallas weather"
NARRATIVE = "Cloudy skies are expected. Check the forecast again before heading out."


@pytest.fixture
def weather_turn(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, chat_model: FakeModel) -> str:
    """A fixed Dallas current/forecast response; the model deliberately writes no temperatures or rain percentages."""
    scenario = str(getattr(request, "param", "metric"))
    imperial = scenario == "imperial"
    units = "imperial" if imperial else "metric"
    missing_daylight = scenario == "unknown-daylight"
    unit = "°F" if imperial else "°C"
    point = {"latitude": 32.78, "longitude": -96.81, "units": units}
    monkeypatch.setattr(chat_model, "answer", NARRATIVE)
    monkeypatch.setattr(
        chat_model,
        "tool_steps",
        [
            [{"name": "geocode_location", "args": {"query": "Dallas"}}],
            [
                {"name": "get_current_weather", "args": point},
                {"name": "get_forecast", "args": {**point, "days": 2, "include_hourly": True}},
            ],
        ],
    )

    def local_now(_now: datetime, _zone: str) -> str:
        """Keep Today/Tomorrow and upcoming hours stable independently of the machine's clock."""
        return "2026-11-09T10:00"

    async def provider(recordings: OpenMeteoRecordings, call: httpx2.Request) -> httpx2.Response:
        """Give only synthetic, consistent Dallas values through the existing Open-Meteo HTTP adapter."""
        recordings.requests.append(call)
        if call.url.path == "/v1/search":
            return httpx2.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Dallas",
                            "admin1": "Texas",
                            "country": "United States",
                            "country_code": "US",
                            "latitude": 32.78,
                            "longitude": -96.81,
                            "timezone": "America/Chicago",
                        }
                    ]
                },
            )
        if "current" in call.url.params:
            return httpx2.Response(
                200,
                json={
                    "timezone": "America/Chicago",
                    "current_units": {
                        "temperature_2m": unit,
                        "wind_speed_10m": "mph" if imperial else "km/h",
                    },
                    "current": {
                        "time": "2026-11-09T09:45",
                        "weather_code": 3,
                        "is_day": 1,
                        "temperature_2m": 64.6 if imperial else 18.1,
                        "apparent_temperature": 65.8 if imperial else 18.8,
                        "wind_speed_10m": 2.6 if imperial else 4.2,
                    },
                },
            )
        return httpx2.Response(
            200,
            json={
                "timezone": "America/Chicago",
                "utc_offset_seconds": -21600,
                "daily_units": {"temperature_2m_max": unit},
                "daily": {
                    "time": ["2026-11-09", "2026-11-10"],
                    "weather_code": [3, 1],
                    "temperature_2m_max": [70.7, 76.5] if imperial else [21.5, 24.7],
                    "temperature_2m_min": [56.7, 59.7] if imperial else [13.7, 15.4],
                    "precipitation_probability_max": [0, 20],
                    "sunrise": [None, None] if missing_daylight else ["2026-11-09T06:52", "2026-11-10T06:53"],
                    "sunset": [None, None] if missing_daylight else ["2026-11-09T17:28", "2026-11-10T17:27"],
                },
                "hourly": {
                    "time": [f"2026-11-09T{hour:02d}:00" for hour in range(9, 17)],
                    "temperature_2m": [64.4] * 8 if imperial else [18.0] * 8,
                    "precipitation_probability": [0] * 8,
                    "weather_code": [0 if missing_daylight else 3] * 8,
                },
            },
        )

    monkeypatch.setattr("nimbus.tools.to_local_now", local_now)
    monkeypatch.setattr(OpenMeteoRecordings, "__call__", provider)
    return unit


def ask_for_weather(page: Page) -> None:
    """Submit the normal chat form and wait for the completed visual answer."""
    page.goto("/")
    page.get_by_label("Your question").fill(QUESTION)
    page.get_by_role("button", name="Send", exact=True).click()
    expect(page.locator(".message-bot[aria-busy]")).to_have_count(0)
    expect(page.locator(".weather-card")).to_have_count(1)
    expect(page.get_by_role("button", name="Send", exact=True)).to_be_visible()


@pytest.mark.parametrize("weather_turn", ["metric", "imperial"], indirect=True)
def test_cards_show_provider_values_with_units_dates_and_expandable_evidence(page: Page, weather_turn: str) -> None:
    """The real SSE result renders numeric evidence even though the model's narrative contains no numbers."""
    ask_for_weather(page)
    card = page.locator(".weather-card")
    expect(card.get_by_role("heading", name=re.compile("Dallas"))).to_be_visible()
    current = card.locator(".weather-current")
    expect(current).to_contain_text("64.6" if weather_turn == "°F" else "18.1")
    expect(current).to_contain_text(weather_turn)
    expect(current).to_contain_text("65.8" if weather_turn == "°F" else "18.8")
    expect(current).to_contain_text("mph" if weather_turn == "°F" else "km/h")
    expect(current).to_contain_text("9:45 AM")
    expect(card.locator(".weather-day")).to_have_count(2)
    expect(card.locator(".weather-day").first).to_contain_text("Today")
    expect(card.locator(".weather-day").first).to_contain_text("0%")
    expect(card.locator(".weather-day").nth(1)).to_contain_text("Tomorrow")
    expect(card.locator(".weather-day").nth(1)).to_contain_text("20%")
    expect(card.locator(".weather-hour")).to_have_count(6)
    expect(card.locator(".weather-source")).to_contain_text("Open-Meteo")
    expect(card).to_contain_text("America/Chicago")
    expect(page.locator(".message-bot .answer").last).to_have_text(NARRATIVE)
    expect(page.locator(".answer .weather-card")).to_have_count(0)
    chips = page.locator(".message-bot").last.locator(".tool-chip")
    expect(chips).to_have_count(3)
    current_chip = chips.filter(has=page.locator(".tool-chip-name", has_text="get_current_weather"))
    current_chip.locator("summary").click()
    expect(current_chip.get_by_text("On the wire", exact=True)).to_be_visible()
    expect(current_chip.locator("pre").last).to_contain_text('"observed_at": "2026-11-09T09:45"')


def test_visual_weather_does_not_pollute_follow_up_conversation_history(page: Page, weather_turn: str) -> None:
    """The follow-up sends only the narrative, never duplicated card labels, provider values or source metadata."""
    ask_for_weather(page)
    box = page.get_by_label("Your question")
    box.fill("What about tomorrow?")
    with page.expect_request(lambda call: call.url.endswith("/api/chat") and call.method == "POST") as sent:
        box.press("Enter")
    fields = sent.value.post_data_json
    assert isinstance(fields, dict)
    assert json.loads(fields["history"]) == [
        {"role": "user", "text": QUESTION},
        {"role": "assistant", "text": NARRATIVE},
    ]
    expect(page.locator(".weather-card")).to_have_count(2)
    expect(page.locator(".message-bot[aria-busy]")).to_have_count(0)


@pytest.mark.parametrize("weather_turn", ["unknown-daylight"], indirect=True)
def test_clear_hours_without_daylight_times_show_text_not_an_invented_sun(page: Page, weather_turn: str) -> None:
    """Missing sunrise/sunset cannot turn a clear nighttime forecast into a sunny-hour picture."""
    ask_for_weather(page)
    hours = page.locator(".weather-hour")
    expect(hours).to_have_count(6)
    expect(hours.locator("svg")).to_have_count(0)
    expect(hours.locator(".weather-hour-condition")).to_have_text(["Clear sky"] * 6)
    expect(page.locator(".weather-day details")).to_have_count(0)


@pytest.mark.parametrize("width", [320, 360, 1280])
def test_weather_cards_are_accessible_and_fit_phone_and_desktop(page: Page, weather_turn: str, width: int) -> None:
    """Audit the rendered hero, daily cards and hourly strip, including browser console and narrow layout."""
    errors: list[str] = []

    def keep_errors(message: ConsoleMessage) -> None:
        """Keep console errors so unsupported assets or CSP regressions fail this presentation check."""
        if message.type == "error":
            errors.append(message.text)

    page.on("console", keep_errors)
    page.set_viewport_size({"width": width, "height": 1000})
    ask_for_weather(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator(".weather-card").evaluate("card => card.scrollWidth <= card.clientWidth")
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
    assert errors == []
    capture = Path("test-results") / f"weather-cards-{width}.png"
    capture.parent.mkdir(exist_ok=True)
    page.locator(".message-bot").last.screenshot(path=str(capture))
