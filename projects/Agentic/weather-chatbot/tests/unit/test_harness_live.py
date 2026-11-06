"""The scorecard consumes only graded synthetic attempts and preserves failed repeats and provider evidence."""

import asyncio
import json
from datetime import datetime
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx2
import pytest

from nimbus.app import create_app
from nimbus.cache import WeatherCache
from nimbus.config import Settings
from nimbus.errors import ANSWER_TOO_SLOW, NOT_SET_UP
from nimbus.goldens import Expect, Golden
from nimbus.travel.models import HotelSearch, TravelReport
from nimbus.travel.service import TravelService
from tests.fakes import PARIS_STEPS, FakeCacheStore, FakeModel, OpenMeteoRecordings
from tools import eval_parks, eval_travel, harness_live

BASE = "http://nimbus.test"


def stream(body: str) -> httpx2.Response:
    """CRLF framing and a terminal heartbeat occur with some streaming transports."""
    return httpx2.Response(200, text=f"data: {body}\r\n\r\n: ping\r\n\r\n")


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (httpx2.Response(429, text="proxy refused the request"), "request_throttled"),
        (httpx2.Response(503, text=f'<p class="message-note">{NOT_SET_UP}</p>'), "model_not_configured"),
        (httpx2.Response(302, headers={"location": "https://other.example"}), "answer_failed"),
        (stream('<div class="answer answer-streaming">Paris</div>'), "incomplete_response"),
        (stream('<p class="message-error">' + ANSWER_TOO_SLOW + "</p>"), "answer_timeout_before_tools"),
        (
            stream(
                '<code class="tool-chip-name">geocode_location</code><p class="message-error">'
                + ANSWER_TOO_SLOW
                + "</p>"
            ),
            "answer_timeout_after_tools",
        ),
        (stream('<div class="answer">The forecast is for Paris.</div>'), "required_tool_sequence"),
    ],
)
def test_transport_and_model_outcomes_are_not_missed_tools(reply: httpx2.Response, expected: str) -> None:
    def handle(req: httpx2.Request) -> httpx2.Response:
        assert str(req.url) == BASE + "/api/chat"
        return reply

    rows = asyncio.run(
        harness_live.live_cases(BASE, suites=("golden",), repeats=1, smoke=True, transport=httpx2.MockTransport(handle))
    )
    assert len(rows) == 1
    assert rows[0]["outcome"] == expected


def test_attempts_and_scope_keep_only_measured_synthetic_results() -> None:
    paris = '<div class="answer">Paris will see rain.</div>'
    chips = "".join(f'<code class="tool-chip-name">{tool}</code>' for tool in ("geocode_location", "get_forecast"))
    sent = 0

    def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal sent
        sent += 1
        assert parse_qs(request.content.decode())["time_zone"] == ["America/Chicago"]
        if sent == 2:
            raise httpx2.ReadTimeout("private timeout sentinel")
        return stream(chips + paris)

    rows = asyncio.run(
        harness_live.live_cases(
            BASE, suites=("golden",), repeats=3, pause=0, smoke=True, transport=httpx2.MockTransport(handle)
        )
    )
    assert [(row["attempt"], row["outcome"]) for row in rows] == [(1, "pass"), (2, "client_timeout"), (3, "pass")]
    assert all(row["case_id"] == "rain-tomorrow" and row["duration_ms"] >= 0 for row in rows)
    assert "Paris" not in json.dumps(rows)
    assert "sentinel" not in json.dumps(rows)


def test_grade_binds_words_links_and_required_tools_to_the_actual_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    source = "https://www.nps.gov/zion/index.htm"
    question = Golden(id="private-check", question="private question", expect=Expect(says=["Zion"], cites=[source]))
    monkeypatch.setattr(harness_live, "read_goldens", lambda: [question])
    cards = f'<section><a href="{source}">Zion</a></section>'
    finals = iter(
        [
            '<div class="answer">A park.</div>' + cards,
            '<div class="answer">Zion is in Utah.</div>' + cards,
            f'<div class="answer">Zion is in Utah. <a href="{source}">NPS</a></div>',
        ]
    )
    rows = asyncio.run(
        harness_live.live_cases(
            BASE, suites=("golden",), pause=0, transport=httpx2.MockTransport(lambda _: stream(next(finals)))
        )
    )
    assert [row["outcome"] for row in rows] == ["source_mismatch", "source_mismatch", "pass"]
    assert source not in json.dumps(rows)


def test_target_and_suite_fail_closed_before_requests() -> None:
    def handle(_request: httpx2.Request) -> httpx2.Response:
        pytest.fail("invalid target or selection reached the network")

    for url in ("https://visitor:secret@preview.example", BASE + "/?key=secret", BASE + "/api/chat", BASE + "#ref"):
        with pytest.raises(ValueError, match="origin"):
            asyncio.run(harness_live.live_cases(url, transport=httpx2.MockTransport(handle)))
    with pytest.raises(ValueError, match="suites"):
        harness_live.live_catalog(("weekend",))
    with pytest.raises(ValueError, match="attempts"):
        asyncio.run(harness_live.live_cases(BASE, repeats=0, transport=httpx2.MockTransport(handle)))


def test_live_travel_retains_grading_and_observed_provider_state() -> None:
    case = next(case for case in eval_travel.read_cases() if case.id == "trivago-direct")
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    stay = eval_travel._dates(today)
    query = {
        "destination": "Springdale, UT",
        "adults": 2,
        "rooms": 1,
        "check_in": stay["arrival"],
        "check_out": stay["departure"],
        "currency": "USD",
    }
    report = TravelReport(provider="trivago", status="timeout")
    chip = (
        '<li class="tool-chip tool-chip-done"><details><code class="tool-chip-name">search_hotels</code>'
        f'<p class="tool-chip-label">Input</p><pre>{json.dumps(query)}</pre>'
        f'<p class="tool-chip-label">Output</p><pre>{report.model_dump_json()}</pre></details></li>'
    )

    def handle(request: httpx2.Request) -> httpx2.Response:
        question = parse_qs(request.content.decode())["question"]
        assert question == [case.golden(today).question]
        return stream(chip + '<div class="answer">The lodging lookup timed out.</div>')

    rows = asyncio.run(
        harness_live.live_cases(BASE, suites=("travel",), repeats=1, smoke=True, transport=httpx2.MockTransport(handle))
    )
    assert rows[0]["outcome"] == "provider_timeout"
    assert rows[0]["provider_calls"] == [{"provider": "trivago", "status": "timeout"}]
    assert "Springdale" not in json.dumps(rows)


def test_park_suite_grades_every_case_once_using_bundled_index() -> None:
    rows = asyncio.run(harness_live.park_cases())
    assert {row["case_id"] for row in rows} == {case.id for case in eval_parks.read_cases()}
    assert {row["outcome"] for row in rows} == {"pass"}
    assert {(row["attempt"], row["suite"]) for row in rows} == {(1, "parks")}


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        ("<h3>Unlisted property</h3><p>$100 per night.</p>", "quote_review_unmatched_heading"),
        ("$100 per night at Example Inn or Park Lodge.", "quote_review_multiple_properties"),
        ("An unlisted property charges $100 per night.", "quote_review_unclear_property"),
        ("Example Inn costs $100.", "quote_review_missing_price_basis"),
        ("Example Inn costs $100 per night per person.", "quote_review_conflicting_price_bases"),
        ("Example Inn is a hundred dollars per night.", "quote_review_spelled_out_amount"),
    ],
)
def test_hotel_review_keeps_the_failure_and_exposes_only_its_fixed_check(body: str, diagnostic: str) -> None:
    dates = eval_travel._dates(datetime.now(ZoneInfo("America/Chicago")).date())
    query = {
        "destination": "Springdale, UT",
        "check_in": dates["arrival"],
        "check_out": dates["departure"],
        "rooms": 1,
        "adults": 2,
        "currency": "USD",
    }
    report = TravelReport.model_validate(
        {
            "provider": "trivago",
            "status": "found",
            "offers": [
                {"title": name, "price": 100, "price_basis": "per_night", "currency": "USD"}
                for name in ("Example Inn", "Park Lodge")
            ],
        }
    )
    final = (
        f'<li class="tool-chip tool-chip-done"><details><code class="tool-chip-name">search_hotels</code>'
        f'<p class="tool-chip-label">Input</p><pre>{json.dumps(query)}</pre>'
        f'<p class="tool-chip-label">Output</p><pre>{report.model_dump_json()}</pre></details></li>'
        f'<div class="answer">{body}</div>'
    )
    rows = asyncio.run(
        harness_live.live_cases(
            BASE, suites=("travel",), smoke=True, repeats=1, transport=httpx2.MockTransport(lambda _: stream(final))
        )
    )
    assert rows[0]["outcome"] == "quote_needs_review"
    assert rows[0]["checks"] == [diagnostic]
    assert rows[0]["provider_calls"] == [{"provider": "trivago", "status": "found"}]
    assert "Example Inn" not in json.dumps(rows)


def test_missing_park_cases_cannot_improve_the_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eval_parks, "read_cases", lambda: [])
    with pytest.raises(ValueError, match="parks"):
        asyncio.run(harness_live.park_cases())


def test_every_attempt_must_be_attributed_to_the_requested_preview() -> None:
    # Same preview before and after cannot vouch for the middle attempt on a moving alias.
    deployments = iter(["dpl_test", "dpl_different", None])

    def handle(_request: httpx2.Request) -> httpx2.Response:
        reply = stream(
            '<code class="tool-chip-name">geocode_location</code>'
            '<code class="tool-chip-name">get_forecast</code><div class="answer">Paris.</div>'
        )
        if deployment := next(deployments):
            reply.headers["x-nimbus-deployment"] = deployment
        return reply

    rows = asyncio.run(
        harness_live.live_cases(
            BASE,
            suites=("golden",),
            smoke=True,
            pause=0,
            expected_deployment="dpl_test",
            transport=httpx2.MockTransport(handle),
        )
    )
    assert [row["outcome"] for row in rows] == ["pass", "deployment_mismatch", "deployment_mismatch"]


@pytest.mark.parametrize("suite", ["golden", "travel"])
def test_live_smoke_runs_three_actual_chat_turns_offline(
    suite: str, settings: Settings, open_meteo: OpenMeteoRecordings
) -> None:
    app = create_app(settings.model_copy(update={"hotels_enabled": True}))
    app.state.make_http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(open_meteo))
    app.state.weather_cache = WeatherCache(FakeCacheStore())
    stay = eval_travel._dates(datetime.now(ZoneInfo("America/Chicago")).date())
    if suite == "golden":
        app.state.chat_model = FakeModel(tool_steps=PARIS_STEPS)
    else:
        query = {
            "destination": "Springdale, UT",
            "check_in": stay["arrival"],
            "check_out": stay["departure"],
            "adults": 2,
        }
        app.state.chat_model = FakeModel(
            tool_steps=[[{"name": "search_hotels", "args": query}]],
            answer="Example Inn costs USD 240 for the stay.",
        )

        async def hotel(_query: HotelSearch) -> TravelReport:
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
                            "url": "https://www.trivago.com/example",
                        }
                    ],
                }
            )

        app.state.travel_service = TravelService(hotels=hotel)

    async def run() -> list[str]:
        async with app.router.lifespan_context(app):
            attempts = await harness_live.live_cases(
                BASE, suites=(suite,), pause=0, smoke=True, transport=httpx2.ASGITransport(app=app)
            )
        return [row["outcome"] for row in attempts]

    assert asyncio.run(run()) == ["pass", "pass", "pass"]
