"""Negative controls and complete SSE fixtures for the opt-in travel suite and its outcome classification."""

import asyncio
import html
import json
from datetime import date
from urllib.parse import parse_qs

import httpx2
import pytest

from nimbus.answer import render_answer
from nimbus.app import create_app
from nimbus.chat import render_part
from nimbus.chips import ToolChip
from nimbus.config import Settings
from nimbus.errors import ANSWER_TOO_SLOW
from nimbus.travel.models import HotelSearch, TravelCallRecord, TravelOffer, TravelReport
from nimbus.travel.service import TravelService
from tests.fakes import FakeModel
from tools.eval_travel import TravelCase, _attempt, outcome, read_cases
from tools.evals import Answer, ask, read_answer

TODAY = date(2032, 12, 30)
CURRENCY_URL = "https://www.kiwi.com/example?a=1&b=2"
TRIVAGO_URL = "https://www.trivago.com/example"


FLIGHT_ARGS: dict[str, object] = {
    "origin": "ORD",
    "destination": "LAS",
    "adults": 2,
    "departure_date": "2033-01-04",
    "return_date": "2033-01-07",
}
HOTEL_ARGS: dict[str, object] = {
    "destination": "Springdale, Utah",
    "check_in": "2033-01-04",
    "check_out": "2033-01-07",
    "adults": 2,
}


def _chip(tool: str, report: TravelReport, args: dict[str, object] | None = None) -> str:
    """Use the application's actual chip template, including independently escaped input and output fields."""
    if args is None:
        args = FLIGHT_ARGS if tool == "search_flights" else HOTEL_ARGS
    chip = ToolChip(1, tool, args, "done", TravelCallRecord(20, report))
    return render_part("chat_tool.html", {"turn_id": "test", "chip": chip, "is_new": False})


def _card(url: str) -> str:
    """Render the separate result-card link a visitor could follow."""
    return f'<section class="travel-results"><a href="{html.escape(url)}">View offer</a></section>'


def _result(case: TravelCase, final: str) -> str:
    """Exercise the real existing SSE final-answer decoder before applying the travel checks."""
    return outcome(case, TODAY, read_answer([final]), 200, final)


def test_complete_independent_searches_are_graded_in_either_order_with_checked_sources() -> None:
    """Real links survive HTML escaping. Reversing independent tool order is valid; substituting a link fails."""
    case = next(case for case in read_cases() if case.id == "both-providers")
    kiwi = TravelReport(provider="kiwi", status="found", offers=(TravelOffer(title="First", url=CURRENCY_URL),))
    trivago = TravelReport(provider="trivago", status="found", offers=(TravelOffer(title="Second", url=TRIVAGO_URL),))
    chips = [
        _chip("search_flights", kiwi, {**FLIGHT_ARGS, "origin": "AUS"}),
        _chip("search_hotels", trivago, {**HOTEL_ARGS, "destination": "Las Vegas, NV, USA"}),
    ]
    tail = '<div class="answer">Here are the offers.</div>' + _card(TRIVAGO_URL) + _card(CURRENCY_URL)
    for prefix in ("".join(chips), "".join(reversed(chips))):
        assert _result(case, prefix + tail) == "pass"
        assert (
            _result(case, prefix + tail.replace("Here are", '<a href="https://unreturned.test/">Visit</a> for'))
            == "source_mismatch"
        )
        assert _result(case, prefix + tail.replace(TRIVAGO_URL, "https://unreturned.test/")) == "source_mismatch"
    assert _result(case, chips[0] + tail) == "missed_tool"
    extra_weather = '<code class="tool-chip-name">geocode_location</code>'
    assert _result(case, extra_weather + "".join(chips) + tail) == "forbidden_tool"


def test_model_cannot_invent_a_price_or_swap_its_currency() -> None:
    """Any price in the narrative must come from a returned offer, including a quoted nightly detail."""
    case = next(case for case in read_cases() if case.id == "trivago-direct")
    report = TravelReport.model_validate(
        {
            "provider": "trivago",
            "status": "found",
            "offers": [
                {
                    "title": "Example Inn",
                    "price": "240.30",
                    "currency": "USD",
                    "price_basis": "stay_total",
                    "details": ["80.10 USD per night"],
                    "url": TRIVAGO_URL,
                }
            ],
        }
    )
    template = _chip("search_hotels", report) + '<div class="answer">{}</div>' + _card(TRIVAGO_URL)
    assert _result(case, template.replace("{}", "USD 240.30 for the stay, $80.10 nightly.")) == "pass"
    assert _result(case, template.replace("{}", "EUR 240.30 for the stay.")) == "unsupported_price"
    assert _result(case, template.replace("{}", "$240.31 for the stay.")) == "unsupported_price"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("timeout", "provider_timeout"),
        ("unavailable", "provider_failed"),
        ("rate_limited", "provider_throttled"),
        ("no_results", "empty_inventory"),
    ],
)
def test_attempted_lookup_keeps_provider_outcomes_separate_from_a_skipped_tool(status: str, expected: str) -> None:
    """Coverage failures do not become successful provider checks or invisible skipped calls."""
    case = next(case for case in read_cases() if case.id == "kiwi-direct")
    report = TravelReport.model_validate({"provider": "kiwi", "status": status})
    body = '<div class="answer">Search finished.</div>'
    assert _result(case, _chip("search_flights", report) + body) == expected
    assert _result(case, '<code class="tool-chip-name">search_flights</code>' + body) == "missing_travel_artifact"
    assert _result(case, body) == "missed_tool"


def test_model_timeout_before_any_selection_is_not_a_missed_search() -> None:
    """A slow answer is separately counted even when the required provider was never selected."""
    case = read_cases()[0]
    for called, expected in (([], "answer_timeout_before_tools"), (["search_flights"], "answer_timeout_after_tools")):
        assert outcome(case, TODAY, Answer(called, ANSWER_TOO_SLOW, True, ""), 200, "") == expected


def test_date_templates_and_planner_intake_are_checked_at_the_user_interface() -> None:
    """Cases survive a calendar rollover and assert routing from the presence of a real submission form."""
    cases = {case.id: case for case in read_cases()}
    assert "2033-01-04" in cases["kiwi-direct"].golden(TODAY).question
    assert "2033-02-08" in cases["beyond-forecast-window"].golden(TODAY).question
    form = (
        '<form action="/api/parks/trip" method="post">'
        '<select name="park"><option selected value="zion">Zion</option></select>'
        '<input name="adults" value="2"></form>'
    )
    answer = '<div class="answer">Confirm your details</div>'
    assert _result(cases["zion-intake"], answer + form) == "pass"
    for wrong in (
        form.replace('method="post"', 'method="get"'),
        form.replace('value="zion"', 'value="yellowstone"'),
        form.replace('value="2"', 'value="1"'),
        form.replace(" selected", ""),
    ):
        assert _result(cases["zion-intake"], answer + wrong) == "wrong_planner_intake"
    assert (
        _result(cases["zion-intake"], answer + form.replace("/api/parks/trip", "/elsewhere")) == "wrong_planner_routing"
    )
    assert _result(cases["zion-intake"], answer) == "wrong_planner_routing"
    assert _result(cases["negated-planning"], answer + form) == "wrong_planner_routing"


def test_existing_chat_driver_sends_history_and_exposes_final_event_once() -> None:
    """The follow-up goes through the same form and SSE parser as ordinary release goldens."""
    case = next(case for case in read_cases() if case.id == "hotel-follow-up")
    event = '<div class="answer">done</div>'

    def handle(request: httpx2.Request) -> httpx2.Response:
        assert json.loads(parse_qs(request.content.decode())["history"][0]) == case.history
        return httpx2.Response(200, text=f"data: start\n\ndata: {event}\n\n")

    async def check() -> None:
        seen: list[tuple[int, str]] = []
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            result = await ask(
                client,
                "http://test",
                case.golden(TODAY),
                history=case.history,
                observe=lambda status, final: seen.append((status, final)),
            )
        assert result.text == "done"
        assert seen == [(200, event)]

    asyncio.run(check())


def test_zion_intake_case_passes_through_actual_chat_without_a_model_or_network(settings: Settings) -> None:
    """Catch template or SSE changes that would quietly break routing or the opt-in live evaluator."""
    app = create_app(settings.model_copy(update={"flights_enabled": True, "hotels_enabled": True}))
    case = next(case for case in read_cases() if case.id == "zion-intake")

    async def check() -> None:
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as client:
            assert await _attempt(client, "http://test", case, TODAY) == "pass"

    asyncio.run(check())


@pytest.mark.parametrize(
    "change",
    [
        {"destination": "Denver"},
        {"destination": "Springdale"},
        {"destination": "Springdale, Arkansas"},
        {"adults": 1},
        {"check_in": "2033-01-05"},
        {"rooms": 2},
        {"currency": "EUR"},
        {"children_ages": [5]},
        {"max_price": 250},
    ],
)
def test_returned_hotel_must_match_the_trip_actually_requested(change: dict[str, object]) -> None:
    case = next(case for case in read_cases() if case.id == "trivago-direct")
    report = TravelReport(provider="trivago", status="found", offers=(TravelOffer(title="Lodge"),))
    body = '<div class="answer">I found a matching hotel.</div>'
    assert _result(case, _chip("search_hotels", report, {**HOTEL_ARGS, **change}) + body) == "wrong_search_arguments"
    # Explicit equivalents and schema defaults are fine. A second, incorrect call cannot hide behind the first one.
    valid = _chip("search_hotels", report, {**HOTEL_ARGS, "destination": "Springdale UT, United States", "rooms": 1})
    assert _result(case, valid + body) == "pass"
    assert (
        _result(case, valid + _chip("search_hotels", report, {**HOTEL_ARGS, **change}) + body)
        == "wrong_search_arguments"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"origin": "MDW"},
        {"destination": "PHX"},
        {"departure_date": "2033-01-05"},
        {"return_date": None},
        {"adults": 1},
        {"children": 1},
    ],
)
def test_flight_arguments_respect_airports_dates_and_party(change: dict[str, object]) -> None:
    case = next(case for case in read_cases() if case.id == "kiwi-direct")
    report = TravelReport(provider="kiwi", status="found", offers=(TravelOffer(title="ORD to LAS"),))
    body = '<div class="answer">See the matching flight below.</div>'
    assert _result(case, _chip("search_flights", report, {**FLIGHT_ARGS, **change}) + body) == "wrong_search_arguments"
    assert (
        _result(case, _chip("search_flights", report, {**FLIGHT_ARGS, "origin": "ord", "children": 0}) + body) == "pass"
    )


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("Example Inn costs USD 240 for the stay, $80 per night.", "pass"),
        ("Example Inn costs USD 240 per night.", "unsupported_price"),
        ("Example Inn is $80 total.", "unsupported_price"),
        ("Example Inn is $300 total.", "unsupported_price"),
        ("Desert Lodge is $300 total.", "pass"),
        ("The Ritz-Carlton costs $240 for the stay.", "quote_needs_review"),
        ("A stay is $240 at the Ritz-Carlton.", "quote_needs_review"),
        ("The hotel costs $240 for the stay.", "pass"),
        ("No rooms are available.", "unsupported_availability"),
        ("These offers are guaranteed available.", "unsupported_availability"),
        ("Rooms were returned. Availability is not guaranteed.", "pass"),
        ("", "wording_failed"),
    ],
)
def test_hotel_quotes_are_bound_to_each_named_property_and_basis(words: str, expected: str) -> None:
    case = next(case for case in read_cases() if case.id == "trivago-direct")
    report = TravelReport.model_validate(
        {
            "provider": "trivago",
            "status": "found",
            "offers": [
                {
                    "title": "Example Inn",
                    "currency": "USD",
                    "price": 240,
                    "price_basis": "stay_total",
                    "details": ["80 USD per night"],
                },
                {"title": "Desert Lodge", "currency": "USD", "price": 300, "price_basis": "stay_total"},
            ],
        }
    )
    assert _result(case, _chip("search_hotels", report) + f'<div class="answer">{words}</div>') == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("USD 180 for both adults.", "pass"),
        ("USD 180 per passenger.", "unsupported_price"),
        ("$180.00 (party total): ORD to LAS and back.", "pass"),
        ("$180.00 USD total for the party ORD to LAS (1 stop each way).", "pass"),
        ("$180.00 USD total per passenger ORD to LAS (1 stop each way).", "unsupported_price"),
        ("$180.00 EUR total for the party.", "unsupported_price"),
        ("USD 180 total per passenger.", "unsupported_price"),
        ("No flights exist at all.", "unsupported_availability"),
        ("Rooms are available.", "unsupported_availability"),
        ("The flight costs JPY 9900 for the party.", "unsupported_price"),
        ("The flight costs AUD 180 for the party.", "unsupported_price"),
        ("It costs nine hundred dollars.", "quote_needs_review"),
    ],
)
def test_flight_claims_are_supported_by_the_party_fare(words: str, expected: str) -> None:
    case = next(case for case in read_cases() if case.id == "kiwi-direct")
    report = TravelReport.model_validate(
        {
            "provider": "kiwi",
            "status": "found",
            "offers": [{"title": "ORD to LAS", "price": 180, "currency": "USD", "price_basis": "party_total"}],
        }
    )
    assert _result(case, _chip("search_flights", report) + f'<div class="answer">{words}</div>') == expected


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ("What dates would you like?", "pass"),
        ("What dates? A first-class room costs $9,999 and is guaranteed available.", "unsupported_price"),
        ("What dates? Rooms are guaranteed available.", "unsupported_availability"),
        ("What dates? A room is guaranteed to be available.", "unsupported_availability"),
        ("What dates should I check to see whether rooms are available?", "pass"),
    ],
)
def test_clarification_cannot_quote_inventory_without_a_provider(words: str, expected: str) -> None:
    case = next(case for case in read_cases() if case.id == "missing-hotel-dates")
    assert _result(case, f'<div class="answer">{words}</div>') == expected


@pytest.mark.parametrize(("location", "expected"), [("Springdale, UT", "pass"), ("Denver", "wrong_search_arguments")])
def test_full_chat_search_grades_what_the_provider_was_asked(settings: Settings, location: str, expected: str) -> None:
    """Run the real agent/service/HTML/SSE path with deliberate correct and incorrect model queries."""
    case = next(case for case in read_cases() if case.id == "trivago-direct")
    app = create_app(settings.model_copy(update={"hotels_enabled": True, "flights_enabled": True}))
    app.state.chat_model = FakeModel(
        tool_steps=[[{"name": "search_hotels", "args": {**HOTEL_ARGS, "destination": location}}]],
        answer="Example Inn costs USD 240 for the stay.",
    )

    async def hotels(query: HotelSearch) -> TravelReport:
        assert query.destination == location
        return TravelReport.model_validate(
            {
                "provider": "trivago",
                "status": "found",
                "offers": [
                    {
                        "title": "Example Inn",
                        "price": 240,
                        "currency": "USD",
                        "price_basis": "stay_total",
                        "url": TRIVAGO_URL,
                    }
                ],
            }
        )

    async def check() -> None:
        app.state.travel_service = TravelService(hotels=hotels)
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as client:
            assert await _attempt(client, "http://test", case, TODAY) == expected

    asyncio.run(check())


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("**Example Inn**\n\n- **Stay price:** USD 443 for the stay\n- **Nightly rate:** USD 148 per night", "pass"),
        ("**Example Inn**\n\n- Stay total: USD 443\n- Nightly: USD 148", "pass"),
        (
            "Here are hotels priced in USD:\n\n**Example Inn**\n\n$148 per night, with a stay total of $443.\n\n"
            "**Desert Lodge**\n\n$100 per night, with a stay total of $300.",
            "pass",
        ),
        ("**Example Inn**\n\n- Stay total: USD 148\n- Nightly rate: USD 443", "unsupported_price"),
        ("**Example Inn**\n\n$100 per night, with a stay total of $300.", "unsupported_price"),
        ("### Ritz-Carlton\n\n$148 per night, with a stay total of $443.", "quote_needs_review"),
        ("**Example Inn**\n\n$148 per night.\n\n**Ritz-Carlton**\n\n$443 for the stay.", "quote_needs_review"),
        ("**Example Inn**\n\n$148 per night.\n\n**Desert Lodge**\n\n$443 for the stay.", "unsupported_price"),
        ("**Example Inn**: $443 stay total ($148 USD per night) via Expedia.", "pass"),
        ("**Desert Lodge**: $100 per night (stay total: $300 via ZenHotels.com).", "pass"),
        ("**Example Inn**: $443 stay total ($148 USD per night) via NoSuchSeller.", "unsupported_seller"),
        ("**Example Inn**: $443 stay total ($148 USD per night) via ZenHotels.com.", "unsupported_seller"),
        ("Ritz-Carlton: $443 stay total ($148 USD per night) via Expedia.", "quote_needs_review"),
        ("**Example Inn**: $443 per night ($148 USD stay total) via Expedia.", "unsupported_price"),
    ],
)
def test_rendered_hotel_headings_and_price_bullets_retain_their_scope(markdown: str, expected: str) -> None:
    """The actual Markdown renderer must preserve each price's property and basis through the grader."""
    case = next(case for case in read_cases() if case.id == "trivago-direct")
    report = TravelReport.model_validate(
        {
            "provider": "trivago",
            "status": "found",
            "offers": [
                {
                    "title": "Example Inn",
                    "currency": "USD",
                    "price": 443,
                    "price_basis": "stay_total",
                    "details": ["148 USD per night", "Expedia"],
                },
                {
                    "title": "Desert Lodge",
                    "currency": "USD",
                    "price": 300,
                    "price_basis": "stay_total",
                    "details": ["100 USD per night", "ZenHotels.com"],
                },
            ],
        }
    )
    body = f'<div class="answer">{render_answer(markdown)}</div>'
    assert _result(case, _chip("search_hotels", report) + body) == expected
