"""Cache-only completeness and display freshness checks; ordinary weather rendering remains tolerant."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from nimbus.chips import ToolChip
from nimbus.open_meteo import WireRequest
from nimbus.request_trace import CacheRejection
from nimbus.semantic_cache.evidence import cached_cards, complete_hours, to_entry
from nimbus.semantic_cache.models import CacheEntry
from nimbus.semantic_cache.policy import cache_policy
from nimbus.tools import Day, ForecastInput, ForecastOutput, Hour, ToolCallRecord
from tests.unit.test_semantic_cache_service import entry as sample_entry


def hourly_forecast(count: int) -> ForecastOutput:
    """Generate full local hourly coverage independently of the admission loop."""
    start = datetime(2026, 11, 9)
    return ForecastOutput(
        latitude=32.78,
        longitude=-96.81,
        time_zone="America/Chicago",
        local_now="2026-11-09T12:00",
        temperature_unit="°F",
        days=[],
        hours=[
            Hour(
                time=(start + timedelta(hours=index)).isoformat(timespec="minutes"),
                condition="Clear sky",
                temperature=70,
                rain_chance_percent=0,
            )
            for index in range(count)
        ],
    )


@pytest.mark.parametrize("count", [0, 1, 24, 47, 48])
def test_each_requested_hour_is_required_before_answer_reuse(count: int) -> None:
    """A schema-valid fragment cannot claim to be the complete two-day hourly tool result."""
    asked = ForecastInput(latitude=32.78, longitude=-96.81, days=2, include_hourly=True, units="imperial")
    assert complete_hours(hourly_forecast(count), asked) is (count == 48)


@pytest.mark.parametrize("temperature", [None, float("nan"), float("inf")])
def test_missing_or_nonfinite_hour_is_not_complete(temperature: float | None) -> None:
    """One invalid required temperature is enough to prevent storing the answer."""
    asked = ForecastInput(latitude=32.78, longitude=-96.81, days=2, include_hourly=True, units="imperial")
    forecast = hourly_forecast(48)
    assert forecast.hours is not None
    forecast.hours[20].temperature = temperature
    assert not complete_hours(forecast, asked)


def test_daily_only_answers_do_not_require_hourly_data() -> None:
    """Only data requested by the actual tool call is mandatory."""
    asked = ForecastInput(latitude=32.78, longitude=-96.81, days=2, include_hourly=False, units="imperial")
    assert complete_hours(hourly_forecast(0), asked)


def admitted(
    now: float,
    remaining: float,
    *,
    browser_zone: str = "America/Chicago",
    destination_zone: str = "America/Chicago",
    forecast_day_offset: int = 0,
    timing: str = "",
    current_unit: str = "°F",
    current_shift: float = 0.0,
) -> CacheEntry | CacheRejection:
    """Build complete evidence whose provider-cache lifetime is nearly over."""
    evidence = sample_entry().evidence
    place = evidence.places.candidates[0]
    if destination_zone == "Asia/Kolkata":
        place.name, place.region, place.country, place.country_code = "Visakhapatnam", "Andhra Pradesh", "India", "IN"
        place.latitude, place.longitude = 17.6868, 83.2185
    place.time_zone = destination_zone
    local = datetime.fromtimestamp(now, ZoneInfo(destination_zone)) + timedelta(days=forecast_day_offset)
    evidence.current.latitude, evidence.current.longitude = place.latitude, place.longitude
    evidence.current.latitude += current_shift
    evidence.current.time_zone = destination_zone
    evidence.current.temperature_unit = current_unit
    evidence.current.observed_at = datetime.fromtimestamp(now, ZoneInfo(destination_zone)).isoformat(timespec="minutes")
    forecast = hourly_forecast(48).model_copy(
        update={
            "latitude": place.latitude,
            "longitude": place.longitude,
            "time_zone": destination_zone,
            "local_now": local.isoformat(timespec="minutes"),
            "days": [
                Day(
                    date=(local.date() + timedelta(days=i)).isoformat(),
                    weekday="Monday",
                    condition="Clear sky",
                    temperature_min=50,
                    temperature_max=70,
                    rain_chance_percent=0,
                    sunrise=None,
                    sunset=None,
                )
                for i in range(2)
            ],
        }
    )
    record = ToolCallRecord(
        "rest-no-auth",
        WireRequest(method="GET", url="https://api.open-meteo.com", headers={}),
        1,
        "Weather",
        True,
        fetched_at=now - 599,
        expires_at=now + remaining,
    )
    geocode = ToolCallRecord(
        "rest-no-auth",
        record.request,
        1,
        "Place",
        True,
        fetched_at=now - 86400,
        expires_at=now + 86400,
    )
    chips = [
        ToolChip(0, "geocode_location", {"query": place.name}, "done", geocode, evidence.places.model_dump_json()),
        ToolChip(1, "get_current_weather", {}, "done", record, evidence.current.model_dump_json()),
        ToolChip(
            2,
            "get_forecast",
            {
                "latitude": place.latitude,
                "longitude": place.longitude,
                "days": 2,
                "include_hourly": False,
                "units": "imperial",
            },
            "done",
            record,
            forecast.model_dump_json(),
        ),
    ]
    question = f"{place.name} weather{timing}"
    policy = cache_policy(question, datetime.fromtimestamp(now, UTC), "en-US", browser_zone)
    assert policy is not None
    return to_entry(question, f"{place.name} has clear weather.", chips, "a" * 64, "b" * 64, policy, now)


@pytest.mark.parametrize(
    ("timestamp", "browser_zone", "destination_zone"),
    [
        ("2026-11-09T20:00:00+00:00", "America/Chicago", "Asia/Kolkata"),
        ("2026-11-10T02:00:00+00:00", "Asia/Kolkata", "America/Chicago"),
    ],
)
def test_forecast_uses_destination_day_when_browser_date_differs(
    timestamp: str, browser_zone: str, destination_zone: str
) -> None:
    """Both a destination ahead and behind the browser can store its complete local forecast."""
    now = datetime.fromisoformat(timestamp).timestamp()
    saved = admitted(now, 600, browser_zone=browser_zone, destination_zone=destination_zone)
    assert isinstance(saved, CacheEntry)
    assert saved.evidence.forecast is not None
    assert saved.policy.day != saved.evidence.forecast.days[0].date
    assert saved.expires_at == now + 120


@pytest.mark.parametrize("offset", [-1, 1])
def test_forecast_must_start_on_current_destination_day(offset: int) -> None:
    """A stale or future local forecast cannot pass merely because it contains the browser date."""
    now = datetime(2026, 11, 9, 20, tzinfo=UTC).timestamp()
    assert admitted(now, 600, destination_zone="Asia/Kolkata", forecast_day_offset=offset) == "forecast_day"


@pytest.mark.parametrize(
    ("timestamp", "browser_zone", "destination_zone", "eligible"),
    [
        ("2026-11-09T20:00:00+00:00", "America/Chicago", "Asia/Kolkata", False),
        ("2026-11-10T02:00:00+00:00", "Asia/Kolkata", "America/Chicago", True),
    ],
)
def test_explicit_today_still_requires_browser_date_coverage(
    timestamp: str, browser_zone: str, destination_zone: str, eligible: bool
) -> None:
    """Explicit today follows the prompt's visitor date, even when the destination date differs."""
    now = datetime.fromisoformat(timestamp).timestamp()
    saved = admitted(now, 600, browser_zone=browser_zone, destination_zone=destination_zone, timing=" today")
    assert isinstance(saved, CacheEntry) if eligible else saved == "forecast_day"


@pytest.mark.parametrize("timestamp", ["2026-11-09T18:29:59+00:00", "2026-11-10T05:59:59+00:00"])
def test_cross_zone_answers_expire_at_either_calendar_midnight(timestamp: str) -> None:
    """Reusing across time zones never extends a result beyond the destination or browser day."""
    now = datetime.fromisoformat(timestamp).timestamp()
    saved = admitted(now, 600, destination_zone="Asia/Kolkata")
    assert isinstance(saved, CacheEntry)
    assert saved.expires_at == now + 1


def test_answer_never_gains_extra_time_when_weather_cache_has_one_second_left() -> None:
    """Ten-minute-old provider data must not acquire a new two-minute answer-cache lifetime."""
    now = datetime(2026, 11, 9, 18, tzinfo=UTC).timestamp()
    saved = admitted(now, 1)
    assert isinstance(saved, CacheEntry)
    assert saved.expires_at == now + 1
    assert saved.evidence_fetched_at == now - 599  # Not the one-day-old geocoding timestamp.
    assert admitted(now, 0) == "freshness"


def test_answer_expires_at_the_destination_midnight_even_with_fresh_provider_data() -> None:
    """Today/Tomorrow cannot silently change meaning while an answer stays cached."""
    now = datetime(2026, 11, 10, 5, 59, 59, tzinfo=UTC).timestamp()
    saved = admitted(now, 600)
    assert isinstance(saved, CacheEntry)
    assert saved.expires_at == now + 1


def test_cached_forecast_preserves_check_time_but_filters_hours_using_current_time() -> None:
    """A cache hit is not a new forecast check, and an hour already past is not upcoming."""
    now = datetime(2026, 11, 9, 18, tzinfo=UTC).timestamp()
    saved = admitted(now, 600)
    assert isinstance(saved, CacheEntry)
    card = cached_cards(saved, now + 3600)[0]
    assert "12:00 PM" in card.forecast_label
    assert card.hours[0].label == "1 PM"


@pytest.mark.parametrize(("unit", "shift", "rejection"), [("°C", 0.0, "units"), ("°F", 0.01, "point")])
def test_a_rejected_answer_names_the_check_that_failed(unit: str, shift: float, rejection: str) -> None:
    """°C weather for a °F visitor, or weather 1 km from the place found, is never kept, and says which it was."""
    now = datetime(2026, 11, 9, 20, tzinfo=UTC).timestamp()
    assert isinstance(admitted(now, 600, destination_zone="Asia/Kolkata"), CacheEntry)
    assert admitted(now, 600, destination_zone="Asia/Kolkata", current_unit=unit, current_shift=shift) == rejection
