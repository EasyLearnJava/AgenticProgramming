"""
tests/unit/test_actor.py: the Actor's input and its items (step 10), from its recorded answers for Dallas
(tests/fixtures/apify/): the point rounded and named by itself, daily or hourly; the items read into get_forecast's
shape, in °F when asked; and every answer we can't trust, a ContractError: none, another shape, another place, a day
missing, twice, or out of order.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from nimbus.actor import summarize_actor_forecast, to_actor_input, to_forecast
from nimbus.errors import ContractError
from nimbus.tools import ForecastInput
from tests.fakes import actor_items

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


def forecast_input(**changes: Any) -> ForecastInput:
    """Dallas's forecast, 2 days, metric, as the model would ask for it."""
    asked = {"latitude": 32.7767, "longitude": -96.797, "days": 2, "include_hourly": False, "units": "metric"}
    return ForecastInput.model_validate(asked | changes)


def test_the_actor_s_input_is_the_point_rounded_and_named_by_itself() -> None:
    assert to_actor_input(forecast_input()) == {
        "locations": [{"name": "32.78, -96.8", "latitude": 32.78, "longitude": -96.8}],
        "forecastDays": 2,
        "mode": "daily",
    }


def test_hours_are_asked_hourly_for_at_most_3_days() -> None:
    actor_input = to_actor_input(forecast_input(days=7, include_hourly=True))
    assert (actor_input["mode"], actor_input["forecastDays"]) == ("hourly", 3)


def test_a_daily_answer_is_get_forecast_s_shape() -> None:
    asked = forecast_input()
    output = to_forecast(actor_items(to_actor_input(asked)), asked, NOW)
    assert [(day.date, day.weekday) for day in output.days] == [("2026-10-29", "Thursday"), ("2026-10-30", "Friday")]
    first = output.days[0]
    assert (first.condition, first.temperature_min, first.temperature_max, first.rain_chance_percent) == (
        "Overcast",
        19.8,
        26.6,
        17,
    )
    assert (output.time_zone, output.temperature_unit, output.hours) == ("America/Chicago", "°C", None)
    assert summarize_actor_forecast(output) == "2 days · 20 to 27 °C · rain up to 17%"


def test_imperial_turns_the_actor_s_celsius_to_fahrenheit_here() -> None:
    asked = forecast_input(units="imperial")
    output = to_forecast(actor_items(to_actor_input(asked)), asked, NOW)
    assert (output.days[0].temperature_min, output.days[0].temperature_max, output.temperature_unit) == (
        67.6,
        79.9,
        "°F",
    )


def test_an_hourly_answer_is_its_hours_alone() -> None:
    asked = forecast_input(days=1, include_hourly=True)
    output = to_forecast(actor_items(to_actor_input(asked)), asked, NOW)
    assert (output.days, len(output.hours or [])) == ([], 24)
    assert summarize_actor_forecast(output).startswith("24 hours · ")


def broken(change: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Dallas's 2 days, broken as a test says."""
    items = actor_items(to_actor_input(forecast_input()))
    return change(items)


@pytest.mark.parametrize(
    "items",
    [
        [],
        broken(lambda items: [{**item, "temp_max_c": "warm"} for item in items]),
        broken(lambda items: [{**item, "latitude": 48.85} for item in items]),
        broken(lambda items: [items[0], {**items[1], "location": "elsewhere"}]),
        broken(lambda items: items[:1]),
        broken(lambda items: [items[0], items[0]]),
        broken(lambda items: [items[1], items[0]]),
    ],
    ids=["none", "another-shape", "another-place", "two-names", "a-day-missing", "a-day-twice", "out-of-order"],
)
def test_an_answer_we_cant_trust_is_a_contract_error(items: list[dict[str, Any]]) -> None:
    with pytest.raises(ContractError):
        to_forecast(items, forecast_input(), NOW)
