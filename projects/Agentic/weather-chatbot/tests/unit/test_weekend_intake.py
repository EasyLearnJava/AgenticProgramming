"""Dated park questions route by the visitor's expressed intent, local calendar, and literal place qualifiers."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from nimbus.config import Settings
from nimbus.parks import ParkKnowledge
from nimbus.travel.planner_intake import analyze_trip
from nimbus.travel.weekend_dates import visit_dates

THURSDAY = datetime(2026, 11, 5, 12, tzinfo=ZoneInfo("America/Chicago"))


@pytest.fixture
def index(settings: Settings) -> ParkKnowledge:
    return ParkKnowledge(settings.parks_index_path)


@pytest.mark.parametrize(
    ("question", "kind", "park", "origin"),
    [
        ("Play a trip to Zion this week end from DFW", "briefing", "zion", "DFW"),
        ("Plan a trip to Zion this weekend from DFW.", "briefing", "zion", "DFW"),
        (
            "Plan a trip to Zion this weekend from DFW. Check the weather and park notices first.",
            "briefing",
            "zion",
            "DFW",
        ),
        ("Plan a trip to Yosemitte next weekend from dfw.", "briefing", "yosemite", "DFW"),
        ("Plan a trip to Yosemite this weekend from DFW.", "briefing", "yosemite", "DFW"),
        ("Plan a trip to Zion", "form", "zion", ""),
        ("Plan a trip to Zion or Yosemite this weekend.", "choose_park", "", ""),
        ("Plan a trip to Zion, Illinois this weekend from DFW.", "other_place", "", "DFW"),
        ("Plan a trip to the Grand Canyon North Rim this weekend", "other_place", "", ""),
        (
            "Plan a trip to the Grand Canyon South Rim from DFW, December 4 to December 6.",
            "briefing",
            "grand-canyon",
            "DFW",
        ),
        ("Plan a trip to Zion Illinois this weekend, after a trip to Yosemite", "other_place", "", ""),
        ("Play a song about a trip to Zion this weekend.", None, "", ""),
        ("Don't plan a trip to Zion. Just show the park alerts.", None, "", ""),
        ("Will it rain in Zion this weekend?", None, "", ""),
        ("Is there a flash-flood warning for the Narrows this weekend?", None, "", ""),
        ("We plan a trip to Zion this weekend. Are there any closures?", None, "", ""),
    ],
)
def test_visitor_prompts_route_with_the_right_park_and_airport(
    question: str, kind: str | None, park: str, origin: str, index: ParkKnowledge
) -> None:
    intent = analyze_trip(question, index, "", THURSDAY, "America/Denver")
    if kind is None:
        assert intent is None
        return
    assert intent is not None
    assert intent.kind == kind
    assert intent.fields.get("park", "") == park
    assert intent.fields.get("origin", "") == origin
    if kind == "choose_park":
        assert set(intent.candidate_parks) == {"zion", "yosemite"}
        assert intent.fields["arrival"] == "2026-11-06"


@pytest.mark.parametrize(
    "lead",
    ["I want to", "We want to", "I'd like to", "We\N{RIGHT SINGLE QUOTATION MARK}d like to", "Let's", "Please help us"],
)
def test_polite_planning_requests_keep_destination(index: ParkKnowledge, lead: str) -> None:
    intent = analyze_trip(f"{lead} plan a trip to Zion this weekend from DFW", index, "", THURSDAY, "America/Chicago")
    assert intent
    assert intent.kind == "briefing"
    assert intent.fields["park"] == "zion"


@pytest.mark.parametrize(
    ("text", "park", "start", "end", "origin"),
    [
        ("Plan a weekend trip to Zion from DFW", "zion", "2026-11-06", "2026-11-08", "DFW"),
        ("Plan a trip to Zion this weekend from Dallas", "zion", "2026-11-06", "2026-11-08", "Dallas"),
        (
            "Plan a trip to Yosmite this weekend from San Francisco",
            "yosemite",
            "2026-11-06",
            "2026-11-08",
            "San Francisco",
        ),
        ("Plan a trip to Zion Nov 13 to Nov 15", "zion", "2026-11-13", "2026-11-15", ""),
        ("Plan a trip to Zion Thanksgiving weekend", "zion", "2026-11-27", "2026-11-29", ""),
        ("Plan a trip to Zion this Saturday", "zion", "2026-11-07", "", ""),
    ],
)
def test_common_weekend_requests_keep_dates_and_explicit_origins(
    index: ParkKnowledge, text: str, park: str, start: str, end: str, origin: str
) -> None:
    intent = analyze_trip(text, index, "", THURSDAY, "America/Chicago")
    assert intent
    assert intent.kind == ("briefing" if end else "form")
    assert intent.fields["park"] == park
    assert intent.fields["arrival"] == start
    assert intent.fields.get("departure", "") == end
    assert intent.fields.get("origin", "") == origin


@pytest.mark.parametrize(
    ("question", "previous", "expected", "origin", "hotels"),
    [
        ("Ok, plan a trip there this weekend", "Is there a flash flood warning in Zion?", "briefing", "", False),
        (
            "Can you help me plan a trip there this weekend?",
            "What's the weather in Zion tomorrow?",
            "briefing",
            "",
            False,
        ),
        ("Plan a trip there this weekend. Skip hotels.", "Will it rain in Zion?", "briefing", "", True),
        ("Plan a trip there this weekend from DFW, 2 adults", "Will it rain in Zion?", "briefing", "DFW", False),
        ("Plan a trip there from DFW this weekend.", "Will it rain in Zion?", "briefing", "DFW", False),
        ("Plan a trip there this weekend", "What's the weather in Zion, Illinois?", "other_place", "", False),
        ("Plan a trip there this weekend", "Is there a warning in Grand Canyon North Rim?", "other_place", "", False),
    ],
)
def test_weather_conversation_can_continue_as_visit(
    index: ParkKnowledge, question: str, previous: str, expected: str, origin: str, hotels: bool
) -> None:
    intent = analyze_trip(question, index, previous, THURSDAY, "UTC")
    assert intent
    assert intent.kind == expected
    assert intent.fields.get("park") == ("zion" if expected == "briefing" else None)
    assert intent.fields.get("origin", "") == origin
    assert intent.skip_hotels == hotels
    if "2 adults" in question:
        assert intent.fields["adults"] == "2"


def test_unspecified_park_prompts_for_choice_and_retains_flight_request(index: ParkKnowledge) -> None:
    previous = "Plan a trip to a national park this weekend flying from Dallas"
    prompt = analyze_trip(previous, index, "", THURSDAY, "UTC")
    assert prompt
    assert prompt.kind == "choose_park"
    assert set(prompt.candidate_parks) == {"zion", "yosemite", "grand-canyon"}
    intent = analyze_trip("Zion", index, previous, THURSDAY, "UTC")
    assert intent
    assert intent.kind == "briefing"
    assert intent.fields["origin"] == "Dallas"
    assert intent.fields["transport"] == "fly"
    assert intent.fields["arrival"] == "2026-11-06"


def test_dated_referential_planning_and_typed_park_choice(index: ParkKnowledge) -> None:
    followup = analyze_trip("Ok, plan a trip there this weekend", index, "Will it rain in Zion?", THURSDAY, "UTC")
    assert followup
    assert followup.kind == "briefing"
    assert followup.fields["park"] == "zion"
    previous = "Plan a trip to Zion or Yosemite next weekend from DFW for two adults. Skip hotels."
    selection = analyze_trip("Zion", index, previous, THURSDAY, "UTC")
    assert selection
    assert selection.kind == "briefing"
    assert selection.fields["arrival"] == "2026-11-13"
    assert selection.fields["adults"] == "2"
    assert selection.fields["origin"] == "DFW"
    assert selection.skip_hotels
    assert analyze_trip("Zion", index, "Will it rain in Yosemite?", THURSDAY, "UTC") is None
    assert analyze_trip("Grand Canyon", index, previous, THURSDAY, "UTC") is None
    assert analyze_trip("Zion, Illinois", index, previous, THURSDAY, "UTC") is None


@pytest.mark.parametrize(
    ("timing", "home_day", "window"),
    [
        ("I need to be back by 3pm Sunday", "2026-11-08", "by_15:00"),
        ("home by noon Sunday", "2026-11-08", "by_noon"),
        ("back Sunday by noon", "2026-11-08", "by_noon"),
        ("back by 12pm", "2026-11-08", "by_noon"),
        ("back by noon Saturday", "2026-11-07", "by_noon"),
        ("Monday morning", "2026-11-09", "morning"),
    ],
)
def test_return_deadline_retains_the_park_and_arrival_day(
    index: ParkKnowledge, timing: str, home_day: str, window: str
) -> None:
    intent = analyze_trip(f"Plan a trip to Zion this weekend from DFW. {timing}.", index, "", THURSDAY, "UTC")
    assert intent
    assert intent.kind == "briefing"
    assert intent.fields["park"] == "zion"
    assert intent.fields["departure"] == home_day
    assert intent.return_window == window


def test_polite_lead_and_city_origin_preserve_geographic_qualifiers(index: ParkKnowledge) -> None:
    for place in ("Zion, Illinois", "Grand Canyon of the Yellowstone", "Grand Canyon North Rim"):
        result = analyze_trip(f"I want to plan a trip to {place} this weekend from Dallas", index, "", THURSDAY, "UTC")
        assert result
        assert result.kind == "other_place"
        assert "park" not in result.fields
    city = analyze_trip("Plan a trip to Zion this weekend from Ely", index, "", THURSDAY, "UTC")
    assert city
    assert city.fields["origin"] == "Ely"
    assert "transport" not in city.fields


def test_scoped_trail_and_return_arrival_preference(index: ParkKnowledge) -> None:
    intent = analyze_trip(
        "Plan a trip to the Narrows this weekend from DFW. I need to be back by noon Sunday.",
        index,
        "",
        THURSDAY,
        "Europe/London",
    )
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.fields == {
        "origin": "DFW",
        "transport": "fly",
        "park": "zion",
        "arrival": "2026-11-06",
        "departure": "2026-11-08",
    }
    assert intent.destination_id == "zion-narrows"
    assert intent.depart_window == "evening"
    assert intent.return_window == "by_noon"

    assert intent.origin_zone == "America/Chicago"


@pytest.mark.parametrize(
    ("suffix", "adults", "ages"),
    [
        (". Will there be snow?", "", ""),
        (", 2 adults and 1 child age 8", "2", "8"),
        (", children aged 3 and 10", "", "3,10"),
        (", two kids ages 7, 9 and 1 room", "", "7,9"),
        (", two children aged 8", "", ""),
    ],
)
def test_generic_weather_and_party_clauses_preserve_the_park_and_observed_ages(
    suffix: str, adults: str, ages: str, index: ParkKnowledge
) -> None:
    intent = analyze_trip("Plan a trip to Zion this weekend from DFW" + suffix, index, "", THURSDAY, "America/Chicago")
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.fields["park"] == "zion"
    assert intent.fields.get("adults", "") == adults
    assert intent.fields.get("children_ages", "") == ages


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        ("Zion", "choose_park"),
        ("Zion, Illinois", "other_place"),
        ("Grand Canyon North Rim", "other_place"),
    ],
)
def test_an_unrecognized_extra_request_asks_for_confirmation_without_stripping_a_place_qualifier(
    destination: str, expected: str, index: ParkKnowledge
) -> None:
    prompt = f"Plan a trip to {destination} this weekend from DFW, wheelchair accessible lodging please."
    intent = analyze_trip(prompt, index, "", THURSDAY, "America/Chicago")
    assert intent is not None
    assert intent.kind == expected
    assert "park" not in intent.fields
    assert intent.candidate_parks == (("zion",) if expected == "choose_park" else ())


@pytest.mark.parametrize(
    ("clause", "mode", "skip_flights", "skip_hotels"),
    [
        (", but no flights or hotels", None, True, True),
        (". I am driving. Skip hotels.", "drive", False, True),
        (". Skip flights.", None, True, False),
        (". Skip hotels.", None, False, True),
    ],
)
def test_declining_quotes_does_not_select_a_travel_method(
    clause: str, mode: str | None, skip_flights: bool, skip_hotels: bool, index: ParkKnowledge
) -> None:
    intent = analyze_trip("Plan a trip to Zion this weekend" + clause, index, "", THURSDAY, "America/Chicago")
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.fields.get("transport") == mode
    assert intent.skip_flights is skip_flights
    assert intent.skip_hotels is skip_hotels


def test_flying_origin_controls_the_calendar_and_weekend_cutoff(index: ParkKnowledge) -> None:
    # Already Saturday in Utah-bound visitor's browser in London, still Friday evening in Dallas.
    late_friday = datetime(2026, 11, 7, 4, 0, tzinfo=ZoneInfo("UTC"))
    prompt = "Plan a trip to Zion this weekend from DFW"
    intent = analyze_trip(prompt, index, "", late_friday, "Europe/London")
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.fields["arrival"] == "2026-11-06"
    saturday = datetime(2026, 11, 7, 13, 0, tzinfo=ZoneInfo("UTC"))
    revised = analyze_trip(prompt, index, "", saturday, "Europe/London")
    assert revised is not None
    assert revised.kind == "choose_weekend"
    assert revised.weekend_options == (("2026-11-07", "2026-11-08"), ("2026-11-13", "2026-11-15"))


@pytest.mark.parametrize(
    ("now", "browser_zone", "defaults"),
    [
        ("2026-11-10T12:00:00-06:00", "America/Chicago", {}),
        ("2026-11-10T23:30:00-06:00", "Europe/London", {"origin": "DFW"}),
        ("2026-11-11T05:30:00+00:00", "Europe/London", {"origin": "DFW"}),
    ],
)
def test_november_10_week_end_request_uses_friday_through_sunday(
    index: ParkKnowledge, now: str, browser_zone: str, defaults: dict[str, str]
) -> None:
    # The last two timestamps are the same instant, still Tuesday evening in Dallas.
    intent = analyze_trip(
        "Plan a trip to Zion this week end",
        index,
        "",
        datetime.fromisoformat(now),
        browser_zone,
        defaults=defaults,
    )
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.fields["arrival"] == "2026-11-13"
    assert intent.fields["departure"] == "2026-11-15"
    assert intent.origin_zone == "America/Chicago"


def test_explicit_dates_preserve_requested_flight_windows(index: ParkKnowledge) -> None:
    intent = analyze_trip(
        "Plan a trip to Zion from DFW. 2026-11-13 Friday night to 2026-11-15 Sunday morning.",
        index,
        "",
        THURSDAY,
        "America/Chicago",
    )
    assert intent is not None
    assert intent.kind == "briefing"
    assert intent.depart_window == "evening"
    assert intent.return_window == "morning"


@pytest.mark.parametrize(
    ("text", "dates"),
    [
        ("next weekend", ("2026-11-13", "2026-11-15")),
        ("this weekend", ("2026-11-06", "2026-11-08")),
        ("this weekend 2026-12-01 to 2026-12-05", ("2026-12-01", "2026-12-05")),
        ("December 31 to January 2", ("2026-12-31", "2027-01-02")),
        ("this weekend, 2026-12-01", None),
        ("2026-12-12 to 2026-12-03", None),
        ("2026-02-30 to 2026-03-01", None),
        ("this weekend or next weekend", None),
        ("not this weekend", None),
        ("this weekend or next month", None),
        ("2026-12-01 to 2027-02-01", None),
        ("2025-11-01 to 2025-11-03", None),
    ],
)
def test_explicit_date_ranges_have_priority_and_invalid_ranges_need_editing(
    text: str, dates: tuple[str, str] | None
) -> None:
    assert visit_dates(text, THURSDAY, "America/Chicago").interval == dates
