"""A traveler's stated return day and clock take precedence over the weekend defaults."""

from datetime import UTC, datetime

import pytest

from nimbus.travel.return_times import return_dates, return_preference
from nimbus.travel.weekend_dates import VisitDates, visit_dates

THURSDAY = datetime(2026, 11, 5, 18, tzinfo=UTC)


@pytest.mark.parametrize(
    ("clause", "deadline", "end"),
    [
        ("I need to be back by 3pm Sunday", "by_15:00", "2026-11-08"),
        ("home by noon Sunday", "by_noon", "2026-11-08"),
        ("back Sunday by noon", "by_noon", "2026-11-08"),
        ("by 12pm", "by_noon", "2026-11-08"),
        ("by 3:15 p.m. on Sunday", "by_15:15", "2026-11-08"),
        ("Monday morning", "morning", "2026-11-09"),
        ("back on Monday", "", "2026-11-09"),
        ("return Monday evening", "evening", "2026-11-09"),
        ("back by noon Saturday", "by_noon", "2026-11-07"),
        ("back before 1pm Sunday", "by_12:59", "2026-11-08"),
        ("back by midnight Sunday", "by_00:00", "2026-11-08"),
    ],
)
def test_return_clause_applies_to_its_actual_day(clause: str, deadline: str, end: str) -> None:
    text = "Plan a trip to Zion this weekend from DFW, " + clause
    result = return_preference(text)
    dates = return_dates(visit_dates(text, THURSDAY, "America/Chicago"), result)
    assert not result.ambiguous
    assert result.window == deadline
    assert result.text.strip() == "Plan a trip to Zion this weekend from DFW,"
    assert dates.interval == ("2026-11-06", end)


@pytest.mark.parametrize(
    "clause",
    [
        "back by 25:00 Sunday",
        "back by 2:61pm Sunday",
        "back at 3pm Sunday",
        "back after 3 on Sunday",
        "by noon Sunday or Monday morning",
    ],
)
def test_invalid_or_contradictory_arrivals_require_clarification(clause: str) -> None:
    result = return_preference(clause)
    assert result.ambiguous
    assert result.window == ""
    assert return_dates(VisitDates(("2026-11-06", "2026-11-08"), weekend=True), result) == VisitDates()


def test_preserves_fixed_dates_and_explicit_departure() -> None:
    result = return_preference("depart Friday morning, home by noon Sunday")
    assert "depart Friday morning" in result.text
    assert return_dates(VisitDates(("2026-11-06", "2026-11-09")), result).interval is None
    assert return_dates(VisitDates(("2026-11-06", "2026-11-08")), result).interval == ("2026-11-06", "2026-11-08")
    assert return_dates(VisitDates(arrival_only="2026-11-07"), result).interval == ("2026-11-07", "2026-11-08")
    assert return_preference("depart Sunday morning").window is None


@pytest.mark.parametrize(
    "activity",
    [
        "depart Sunday morning",
        "leave DFW by noon Sunday",
        "arrive at Zion by noon Sunday",
        "hike the Narrows Monday morning",
    ],
)
def test_activity_and_outbound_clocks_do_not_override_home_arrival(activity: str) -> None:
    result = return_preference(activity)
    assert result.window is None
    assert result.text == activity


def test_midweek_deadline_does_not_become_sunday_and_options_keep_the_correct_week() -> None:
    dates = VisitDates(options=(("2026-11-07", "2026-11-08"), ("2026-11-13", "2026-11-15")), weekend=True)
    assert not return_dates(dates, return_preference("back Tuesday morning")).options
    assert return_dates(dates, return_preference("back Saturday morning")).options == (("2026-11-13", "2026-11-14"),)
    assert return_dates(dates, return_preference("Monday morning")).options == (
        ("2026-11-07", "2026-11-09"),
        ("2026-11-13", "2026-11-16"),
    )
