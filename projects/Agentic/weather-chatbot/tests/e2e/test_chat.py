"""
tests/e2e/test_chat.py: the chat in a real browser: each tool call shows as a chip, running then done, which opens to
its request; an answer streams in a piece at a time, and Stop ends it where it is, a call still running marked
stopped; Enter while an answer streams sends nothing more; a question too long, a chat that can't be reached, another
service's error page and an answer cut off each get our own sentence; and with an answer and an open chip on it, the
page logs no error, passes axe's checks, and fits a phone.
"""

import re

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import ConsoleMessage, Locator, Page, Route, expect

from nimbus.constants import QUESTION_MAX_CHARS
from nimbus.errors import CUT_OFF, QUESTION_TOO_LONG, STOPPED, UNREACHABLE
from tests.fakes import ANSWER, OpenMeteoRecordings

QUESTION = "Will it rain in Paris tomorrow?"
HAS_TEXT = re.compile(r"\S")
# The finished answer, as the page shows it: its Markdown made HTML, so without the asterisks.
ANSWER_TEXT = ANSWER.replace("**", "")


def ask(page: Page, question: str = QUESTION) -> None:
    """Opens the chat, types a question into the box, and presses Enter."""
    page.goto("/")
    box = page.get_by_label("Your question")
    box.fill(question)
    box.press("Enter")


def last_answer(page: Page) -> Locator:
    """The text of Nimbus's newest answer (the welcome has none)."""
    return page.locator(".message-bot .answer").last


def busy_answer(page: Page) -> Locator:
    """The text of the answer being written."""
    return page.locator('.message-bot[aria-busy="true"] .answer')


def test_an_answer_streams_in_a_piece_at_a_time(page: Page) -> None:
    ask(page)
    expect(page.locator(".message-user")).to_have_text(re.compile(re.escape(QUESTION)))
    expect(busy_answer(page)).to_have_text(HAS_TEXT)
    so_far = busy_answer(page).text_content() or ""
    assert 0 < len(so_far) < len(ANSWER)
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    expect(page.locator('[aria-busy="true"]')).to_have_count(0)
    expect(page.get_by_label("Your question")).to_have_value("")
    expect(page.get_by_role("button", name="Send")).to_be_visible()
    expect(page.get_by_role("button", name="Stop")).to_be_hidden()


def test_stop_ends_the_answer_where_it_is(page: Page) -> None:
    ask(page)
    expect(busy_answer(page)).to_have_text(HAS_TEXT)
    page.get_by_role("button", name="Stop").click()
    message = page.locator(".message-bot").last
    expect(message.locator(".message-note")).to_have_text(STOPPED)
    stopped_at = message.locator(".answer").text_content() or ""
    page.wait_for_timeout(500)
    assert message.locator(".answer").text_content() == stopped_at
    assert len(stopped_at) < len(ANSWER)
    expect(page.locator('[aria-busy="true"]')).to_have_count(0)
    expect(page.get_by_role("button", name="Send")).to_be_visible()


def test_enter_while_an_answer_streams_sends_nothing_more(page: Page) -> None:
    ask(page)
    expect(busy_answer(page)).to_have_count(1)
    box = page.get_by_label("Your question")
    box.fill("And in Lyon?")
    box.press("Enter")
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    expect(page.locator(".message-user")).to_have_count(1)
    expect(box).to_have_value("And in Lyon?")


def test_a_question_too_long_gets_our_sentence_and_stays_in_the_box(page: Page) -> None:
    page.goto("/")
    box = page.get_by_label("Your question")
    box.evaluate("input => input.removeAttribute('maxlength')")
    too_long = "a" * (QUESTION_MAX_CHARS + 1)
    box.fill(too_long)
    box.press("Enter")
    expect(page.locator(".message-error .message-note")).to_have_text(QUESTION_TOO_LONG)
    expect(page.locator(".message-user")).to_have_count(0)
    expect(box).to_have_value(too_long)


def test_when_the_chat_can_t_be_reached_it_says_so(page: Page) -> None:
    page.route("**/api/chat", lambda route: route.abort())
    ask(page)
    expect(page.locator(".message-error .message-note")).to_have_text(UNREACHABLE)
    expect(page.get_by_label("Your question")).to_have_value(QUESTION)


def test_another_service_s_error_page_is_never_shown(page: Page) -> None:
    def bad_gateway(route: Route) -> None:
        route.fulfill(status=502, content_type="text/html", body="<h1>Bad gateway at the proxy</h1>")

    page.route("**/api/chat", bad_gateway)
    ask(page)
    expect(page.locator(".message-error .message-note")).to_have_text(UNREACHABLE)
    expect(page.get_by_text("Bad gateway at the proxy")).to_have_count(0)


def test_an_answer_cut_off_says_so(page: Page) -> None:
    def first_event_only(route: Route) -> None:
        response = route.fetch()
        route.fulfill(response=response, body=response.text().split("\n\n")[0] + "\n\n")

    page.route("**/api/chat", first_event_only)
    ask(page)
    message = page.locator(".message-bot").last
    expect(message.locator(".message-note")).to_have_text(CUT_OFF)
    expect(page.locator('[aria-busy="true"]')).to_have_count(0)


def test_a_stream_that_ends_before_its_first_event_keeps_the_question_and_says_so(page: Page) -> None:
    def empty_stream(route: Route) -> None:
        route.fulfill(status=200, headers={"content-type": "text/event-stream"}, body="")

    page.route("**/api/chat", empty_stream)
    ask(page)
    expect(page.locator(".message-error .message-note")).to_have_text(CUT_OFF)
    expect(page.get_by_label("Your question")).to_have_value(QUESTION)


def test_after_send_is_clicked_the_focus_stays_in_the_box(page: Page) -> None:
    page.goto("/")
    box = page.get_by_label("Your question")
    box.fill(QUESTION)
    page.get_by_role("button", name="Send").click()
    expect(busy_answer(page)).to_have_count(1)
    expect(box).to_be_focused()


def test_with_an_answer_the_page_logs_no_error_and_passes_axe(page: Page) -> None:
    errors: list[str] = []

    def keep_errors(message: ConsoleMessage) -> None:
        if message.type == "error":
            errors.append(message.text)

    page.on("console", keep_errors)
    ask(page)
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    assert errors == []
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()


def test_a_long_question_and_its_answer_fit_a_phone(page: Page) -> None:
    page.set_viewport_size({"width": 360, "height": 800})
    ask(page, "x" * 300)
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0


def chips(page: Page) -> Locator:
    """The tool calls' chips of Nimbus's newest answer."""
    return page.locator(".message-bot").last.locator(".tool-chip")


def test_each_tool_call_shows_as_a_chip_running_then_done(page: Page, slow_open_meteo: OpenMeteoRecordings) -> None:
    ask(page)
    running = page.locator(".tool-chip-running")
    expect(running).to_have_count(1)
    expect(running.locator(".tool-chip-mark")).to_have_text("…")
    expect(running.locator(".tool-chip-name")).to_have_text("geocode_location")
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    expect(chips(page)).to_have_count(2)
    expect(page.locator(".tool-chip-done")).to_have_count(2)
    expect(chips(page).first.locator(".tool-chip-lane")).to_have_text(
        re.compile(r"^REST · no auth · geocoding-api\.open-meteo\.com · \d\.\d s$")
    )


def test_a_chip_opens_to_the_request_as_it_went_out_its_input_and_output(page: Page) -> None:
    ask(page)
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    forecast = chips(page).nth(1)
    forecast.locator("summary").click()
    expect(forecast.get_by_text("On the wire")).to_be_visible()
    wire = forecast.locator("pre").first
    expect(wire).to_have_text(
        re.compile(r"^GET https://api\.open-meteo\.com/v1/forecast\?latitude=48\.85&longitude=2\.35")
    )
    expect(forecast.locator("pre").nth(1)).to_have_text(re.compile(r'"days": 2'))
    expect(forecast.locator("pre").nth(2)).to_have_text(re.compile(r'"local_now"'))


def test_stop_marks_a_call_still_running_stopped(page: Page, slow_open_meteo: OpenMeteoRecordings) -> None:
    ask(page)
    expect(page.locator(".tool-chip-running")).to_have_count(1)
    page.get_by_role("button", name="Stop").click()
    stopped = page.locator(".tool-chip-stopped")
    expect(stopped).to_have_count(1)
    expect(stopped.locator(".tool-chip-mark")).to_have_text("■")
    expect(stopped.locator(".tool-chip-word")).to_have_text("Stopped:")
    expect(page.locator(".message-bot").last.locator(".message-note")).to_have_text(STOPPED)


def test_an_open_chip_passes_axe_and_fits_a_phone(page: Page) -> None:
    page.set_viewport_size({"width": 360, "height": 800})
    ask(page)
    expect(last_answer(page)).to_have_text(ANSWER_TEXT)
    for index in range(2):
        chips(page).nth(index).locator("summary").click()
    expect(chips(page).nth(1).get_by_text("On the wire")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
    results = Axe().run(page)
    assert results.violations_count == 0, results.generate_report()
