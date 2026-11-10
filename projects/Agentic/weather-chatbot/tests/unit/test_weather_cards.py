"""Weather cards use validated tool evidence, with local dates and separate locations and units."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import date, timedelta

import pytest

from nimbus.answer import AnswerEvent, AnswerStats, ToolEnded, ToolStarted
from nimbus.chat import render_part, stream_turn
from nimbus.chips import ChipStatus, ToolChip
from nimbus.open_meteo import Place, WireRequest
from nimbus.scope_guard import ScopeGuard
from nimbus.tools import CurrentWeatherOutput, Day, ForecastOutput, GeocodeOutput, Hour, ToolCallRecord
from nimbus.weather_cards import to_weather_cards
from tests.fakes import FakeModel

RECORD = ToolCallRecord(
    "rest-no-auth", WireRequest(method="GET", url="https://api.open-meteo.com/v1/forecast", headers={}), 10, "Weather"
)
CURRENT = CurrentWeatherOutput(
    latitude=32.78,
    longitude=-96.81,
    time_zone="America/Chicago",
    observed_at="2026-11-09T04:15",
    condition="Overcast",
    is_day=False,
    temperature=18.1,
    feels_like=18.8,
    temperature_unit="°C",
    wind_speed=4.2,
    wind_speed_unit="km/h",
)
FORECAST = ForecastOutput(
    latitude=32.78,
    longitude=-96.81,
    time_zone="America/Chicago",
    local_now="2026-11-09T04:30",
    temperature_unit="°C",
    days=[
        Day(
            date="2026-11-09",
            weekday="Monday",
            condition="Overcast",
            temperature_min=13.7,
            temperature_max=21.5,
            rain_chance_percent=0,
            sunrise="2026-11-09T06:51",
            sunset="2026-11-09T17:28",
        ),
        Day(
            date="2026-11-10",
            weekday="Tuesday",
            condition="Mainly clear",
            temperature_min=15.4,
            temperature_max=24.7,
            rain_chance_percent=None,
            sunrise=None,
            sunset=None,
        ),
    ],
    hours=[
        Hour(time="2026-11-09T04:00", condition="Overcast", temperature=18.1, rain_chance_percent=0),
        Hour(time="2026-11-09T05:00", condition="Overcast", temperature=18.4, rain_chance_percent=0),
    ],
)
GEOCODE = GeocodeOutput(
    candidates=[Place(name="Dallas", admin1="Texas", country_code="US", latitude=32.78306, longitude=-96.80667)],
    is_ambiguous=False,
)


def weather_chip(name: str, payload: str, *, cached: bool = False) -> ToolChip:
    """One completed weather call, as the real event stream records it."""
    return ToolChip(
        index=0, name=name, args={}, status="done", output=payload, record=replace(RECORD, from_cache=cached)
    )


def sample_chips() -> list[ToolChip]:
    """A geocoded Dallas current-weather and forecast response."""
    return [
        weather_chip("geocode_location", GEOCODE.model_dump_json()),
        weather_chip("get_current_weather", CURRENT.model_dump_json()),
        weather_chip("get_forecast", FORECAST.model_dump_json()),
    ]


def test_cards_join_matching_evidence_and_keep_local_dates_and_probabilities() -> None:
    (card,) = to_weather_cards(sample_chips())
    assert card.location == "Dallas, Texas, US"
    assert card.time_zone == "America/Chicago"
    assert card.current
    assert card.current.temperature == 18.1
    assert card.current.wind_speed == 4.2
    assert card.temperature_unit == "°C"
    assert card.current_icon == "cloud"
    assert [(day.label, day.high, day.low, day.rain) for day in card.days] == [
        ("Today", 21.5, 13.7, 0),
        ("Tomorrow", 24.7, 15.4, None),
    ]
    assert card.days[0].sunrise == "6:51 AM"
    assert "2026" in card.observed_label
    assert "4:15 AM" in card.observed_label
    assert len(card.hours) == 1
    assert card.hours[0].label == "5 AM"
    assert card.source == "Open-Meteo"
    assert not card.cached


def test_multiple_locations_units_and_repeated_calls_do_not_cross_contaminate() -> None:
    chips = sample_chips()
    chips += [
        weather_chip("get_current_weather", CURRENT.model_copy(update={"temperature": 19}).model_dump_json()),
        weather_chip(
            "get_current_weather",
            CURRENT.model_copy(
                update={"temperature_unit": "°F", "temperature": 64.6, "wind_speed_unit": "mph"}
            ).model_dump_json(),
        ),
        weather_chip(
            "get_forecast",
            FORECAST.model_copy(
                update={"latitude": 48.85, "longitude": 2.35, "time_zone": "Europe/Paris"}
            ).model_dump_json(),
        ),
    ]
    metric, imperial, paris = to_weather_cards(chips)
    assert metric.current
    assert metric.current.temperature == 19
    assert len(metric.days) == 2
    assert imperial.current
    assert imperial.current.temperature == 64.6
    assert not imperial.days
    assert imperial.temperature_unit == "°F"
    assert "Dallas" not in paris.location
    assert "48.85" in paris.location
    assert paris.current is None


@pytest.mark.parametrize("status", ["failed", "running", "stopped"])
def test_unsuccessful_weather_calls_cannot_create_cards(status: ChipStatus) -> None:
    chip = sample_chips()[1]
    chip.status = status
    assert not to_weather_cards([chip])


@pytest.mark.parametrize("payload", ["{}", "not json", "[]", '{"temperature": 22}'])
def test_malformed_weather_evidence_does_not_break_rendering(payload: str) -> None:
    assert not to_weather_cards([weather_chip("get_current_weather", payload)])


def test_missing_zero_negative_and_unknown_conditions_stay_distinct() -> None:
    current = CURRENT.model_copy(
        update={
            "temperature": 0,
            "feels_like": -2,
            "wind_speed": None,
            "condition": "Unknown conditions (WMO code 123)",
        }
    )
    (card,) = to_weather_cards([weather_chip("get_current_weather", current.model_dump_json())])
    assert card.current
    assert card.current.temperature == 0
    assert card.current.feels_like == -2
    assert card.current.wind_speed is None
    assert card.current_icon == "unknown"


def test_midnight_and_timezone_aware_dates_use_the_destination_day() -> None:
    forecast = FORECAST.model_copy(update={"local_now": "2026-11-10T00:30:00+00:00"})
    (card,) = to_weather_cards([weather_chip("get_forecast", forecast.model_dump_json())])
    assert [day.label for day in card.days] == ["Today", "Tomorrow"]
    assert "6:30 PM" in card.forecast_label


def test_cache_and_provenance_are_taken_from_the_displayed_results() -> None:
    chip = weather_chip("get_current_weather", CURRENT.model_dump_json(), cached=True)
    (card,) = to_weather_cards([chip])
    assert card.cached
    chip.record = replace(
        RECORD,
        lane="rest-with-auth",
        request=WireRequest(method="POST", url="https://api.apify.com/v2/acts/run", headers={}),
    )
    (card,) = to_weather_cards([chip])
    assert card.source == "Weather tools"


def test_cards_do_not_reuse_an_unmatched_geocode_or_unknown_tool_payload() -> None:
    chips = sample_chips()
    chips[0].output = GEOCODE.model_copy(
        update={"candidates": [Place(name="Paris", latitude=48.85, longitude=2.35)]}
    ).model_dump_json()
    (card,) = to_weather_cards(chips)
    assert "Dallas" not in card.location
    assert "Paris" not in card.location
    chips[1].name = "search_park_guidance"
    assert not to_weather_cards([chips[1]])


@pytest.mark.parametrize("failure", ["none", "generation", "guard"])
def test_final_stream_keeps_verified_cards_after_generation_or_guard_failure(failure: str) -> None:
    async def answer() -> AsyncGenerator[AnswerEvent]:
        """Successful tools, then narrative or a model failure after the weather arrived."""
        for index, chip in enumerate(sample_chips()):
            yield ToolStarted(str(index), chip.name, {})
            yield ToolEnded(str(index), chip.name, chip.output or "", chip.record, False)
        yield "A light jacket may help in the evening."
        if failure == "generation":
            raise RuntimeError("private provider error")

    async def ending() -> str:
        """Collect the final server-rendered event without an external service."""
        model = FakeModel(guard_error=RuntimeError("private guard error") if failure == "guard" else None)
        events = [
            event
            async for event in stream_turn(
                answer(), "Dallas weather", "test-id", AnswerStats(), "fake", scope_guard=ScopeGuard(model)
            )
        ]
        return events[-1]

    final = asyncio.run(ending())
    assert 'class="weather-card' in final
    assert "Dallas, Texas, US" in final
    assert ("A light jacket may help in the evening." in final) is (failure == "none")
    assert "private provider error" not in final
    assert "private guard error" not in final
    assert ("message-error" in final) is (failure != "none")


def test_template_escapes_source_text_and_distinguishes_missing_from_zero() -> None:
    """Provider text cannot become markup, and absent metrics cannot turn into false zero readings."""
    current = CURRENT.model_copy(update={"temperature": 0, "feels_like": None, "condition": "<script>bad()</script>"})
    geocode = GEOCODE.model_copy(
        update={"candidates": [Place(name='<img src=x onerror="bad()">', latitude=32.78, longitude=-96.81)]}
    )
    cards = to_weather_cards(
        [
            weather_chip("geocode_location", geocode.model_dump_json()),
            weather_chip("get_current_weather", current.model_dump_json()),
            weather_chip("get_forecast", FORECAST.model_dump_json()),
        ]
    )
    html = render_part("chat_end.html", {"turn_id": "test", "answer": "Context", "chips": [], "weather_cards": cards})
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert "Not available" in html
    assert '0<span class="weather-unit">°C</span>' in html
    assert '0<span class="weather-unit">%</span>' in html


@pytest.mark.parametrize(
    ("condition", "is_day", "icon"),
    [
        ("Clear sky", True, "clear"),
        ("Clear sky", False, "night"),
        ("Partly cloudy", True, "partly"),
        ("Moderate rain", True, "rain"),
        ("Snow grains", True, "snow"),
        ("Thunderstorm with hail", True, "storm"),
        ("Depositing rime fog", True, "fog"),
        ("Unrecognized condition", True, "unknown"),
    ],
)
def test_conditions_have_appropriate_decorative_icons(condition: str, is_day: bool, icon: str) -> None:
    """Night and unknown weather never acquire an unearned sunny icon."""
    current = CURRENT.model_copy(update={"condition": condition, "is_day": is_day})
    (card,) = to_weather_cards([weather_chip("get_current_weather", current.model_dump_json())])
    assert card.current_icon == icon


def test_all_requested_days_remain_available_and_hourly_samples_are_bounded() -> None:
    """A long forecast preserves its requested coverage while the labelled hourly preview stays compact."""
    days = [FORECAST.days[0].model_copy(update={"date": str(date(2026, 11, 9) + timedelta(days=i))}) for i in range(16)]
    hours = (
        [FORECAST.hours[0].model_copy(update={"time": f"2026-11-09T{i:02}:00"}) for i in range(18)]
        if FORECAST.hours
        else []
    )
    forecast = FORECAST.model_copy(update={"days": days, "hours": list(reversed(hours))})
    (card,) = to_weather_cards([weather_chip("get_forecast", forecast.model_dump_json())])
    assert len(card.days) == 16
    assert card.days[-1].date == "2026-11-24"
    assert len(card.hours) == 6
    assert [hour.label for hour in card.hours] == ["5 AM", "6 AM", "7 AM", "8 AM", "9 AM", "10 AM"]


def test_bad_timestamps_and_out_of_range_values_do_not_create_false_measurements() -> None:
    """Invalid provider timing loses relative labels, while invalid probabilities remain unavailable."""
    forecast = FORECAST.model_copy(
        update={"local_now": "invalid", "days": [FORECAST.days[0].model_copy(update={"rain_chance_percent": 120})]}
    )
    (card,) = to_weather_cards([weather_chip("get_forecast", forecast.model_dump_json())])
    assert card.days[0].label == "Mon"
    assert card.days[0].rain is None
    assert card.hours == ()
    assert card.forecast_label == "Time unavailable"
    current = CURRENT.model_copy(update={"latitude": 100})
    assert to_weather_cards([weather_chip("get_current_weather", current.model_dump_json())]) == ()


def test_fresh_replacement_does_not_inherit_old_cached_provenance() -> None:
    """Only the visible result supplies the cache indicator."""
    old = weather_chip("get_current_weather", CURRENT.model_dump_json(), cached=True)
    new = weather_chip("get_current_weather", CURRENT.model_copy(update={"temperature": 20}).model_dump_json())
    (card,) = to_weather_cards([old, new])
    assert not card.cached
    assert card.current
    assert card.current.temperature == 20


@pytest.mark.parametrize("stamp", ["0001-01-01T00:00:00+00:00", "9999-12-31T12:00"])
def test_extreme_provider_timestamps_cannot_break_the_answer(stamp: str) -> None:
    """Out-of-range timezone arithmetic remains an optional presentation detail."""
    current = CURRENT.model_copy(update={"observed_at": stamp})
    forecast = FORECAST.model_copy(update={"local_now": stamp})
    (card,) = to_weather_cards(
        [
            weather_chip("get_current_weather", current.model_dump_json()),
            weather_chip("get_forecast", forecast.model_dump_json()),
        ]
    )
    assert card.current is not None
    assert card.current.temperature == 18.1
    assert len(card.days) == 2


def test_hourly_icons_use_daylight_and_never_guess_a_sun_for_unknown_times() -> None:
    """A clear evening gets a moon; missing daylight evidence leaves condition text without an invented sun."""
    hours = [Hour(time="2026-11-09T18:00", condition="Clear sky", temperature=16, rain_chance_percent=0)]
    forecast = FORECAST.model_copy(update={"local_now": "2026-11-09T17:45", "hours": hours})
    (card,) = to_weather_cards([weather_chip("get_forecast", forecast.model_dump_json())])
    assert card.hours[0].icon == "night"
    forecast = forecast.model_copy(update={"days": []})
    (card,) = to_weather_cards([weather_chip("get_forecast", forecast.model_dump_json())])
    assert card.hours[0].icon == ""
