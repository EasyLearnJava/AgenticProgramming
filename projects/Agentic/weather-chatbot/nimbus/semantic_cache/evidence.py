"""Admit only complete weather evidence and preserve its original lifetime when reusing an answer."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from nimbus.chips import ToolChip
from nimbus.constants import MAX_HOURLY_DAYS
from nimbus.open_meteo import WireRequest
from nimbus.semantic_cache.models import TTL_SECONDS, CacheEntry, CachePolicy, WeatherEvidence
from nimbus.semantic_cache.policy import canonical_city, digest, normalized
from nimbus.tools import CurrentWeatherOutput, ForecastInput, ForecastOutput, GeocodeOutput, ToolCallRecord, round_point
from nimbus.weather_cards import WeatherCard, to_weather_cards


def complete_hours(forecast: ForecastOutput, asked: ForecastInput) -> bool:
    """Require each requested local hour and a finite temperature; uncertain DST coverage safely bypasses reuse."""
    if not asked.include_hourly:
        return True
    start = datetime.fromisoformat(forecast.local_now).replace(hour=0, minute=0, second=0, microsecond=0)
    expected = {
        (start + timedelta(hours=index)).isoformat(timespec="minutes")
        for index in range(min(asked.days, MAX_HOURLY_DAYS) * 24)
    }
    available = {
        hour.time for hour in forecast.hours or () if hour.temperature is not None and math.isfinite(hour.temperature)
    }
    return expected <= available


def to_entry(
    question: str, answer: str, chips: Sequence[ToolChip], scope: str, context: str, policy: CachePolicy, now: float
) -> CacheEntry | None:
    """Reject partial, ambiguous, inconsistent or stale evidence rather than caching a plausible-looking answer."""
    # ① An eligible answer may contain only successful ordinary weather calls, each exactly once.
    if not answer.strip() or len(answer) > 12000 or not chips or len({c.name for c in chips}) != len(chips):
        return None
    allowed = {"geocode_location", "get_current_weather", "get_forecast"}
    if any(c.name not in allowed or c.status != "done" or not c.output or not c.weather_record for c in chips):
        return None
    by_name = {c.name: c for c in chips}
    if not {"geocode_location", "get_current_weather"} <= by_name.keys():
        return None
    if policy.intent != "current" and "get_forecast" not in by_name:
        return None
    try:
        places = GeocodeOutput.model_validate_json(by_name["geocode_location"].output or "")
        current = CurrentWeatherOutput.model_validate_json(by_name["get_current_weather"].output or "")
        forecast = (
            ForecastOutput.model_validate_json(by_name["get_forecast"].output or "")
            if "get_forecast" in by_name
            else None
        )
        if places.is_ambiguous or not places.candidates:
            return None
        place = places.candidates[0]
        parts = [part.strip() for part in policy.place.split(",")]
        qualifiers = {normalized(v) for v in (place.region, place.country, place.country_code) if v}
        if canonical_city(place.name) != parts[0] or any(part not in qualifiers for part in parts[1:]):
            return None
        units = "°F" if policy.units == "imperial" else "°C"
        weather_results: list[CurrentWeatherOutput | ForecastOutput] = [current]
        if forecast:
            weather_results.append(forecast)
        for result in weather_results:
            if (
                not -90 <= result.latitude <= 90
                or not -180 <= result.longitude <= 180
                or (round_point(result.latitude), round_point(result.longitude))
                != (round_point(place.latitude), round_point(place.longitude))
                or result.time_zone != place.time_zone
                or result.temperature_unit != units
            ):
                return None
        if current.temperature is None or not math.isfinite(current.temperature):
            return None
        if forecast:
            asked = ForecastInput.model_validate(by_name["get_forecast"].args)
            first_day = datetime.fromisoformat(forecast.local_now).date()
            # Forecast dates belong to the destination, which can be a day ahead of or behind the browser.
            destination_day = datetime.fromtimestamp(now, ZoneInfo(current.time_zone)).date()
            if first_day != destination_day:
                return None
            # The system prompt defines an explicit "today" as the visitor's calendar date.
            if policy.intent == "today" and policy.day not in {day.date for day in forecast.days}:
                return None
            expected_dates = {(first_day + timedelta(days=index)).isoformat() for index in range(asked.days)}
            if not expected_dates <= {day.date for day in forecast.days}:
                return None
            if not complete_hours(forecast, asked):
                return None
            if any(
                value is None or not math.isfinite(value)
                for day in forecast.days
                for value in (day.temperature_min, day.temperature_max)
            ):
                return None
        # ② Unknown freshness is never renewed. Every provider result retains its absolute expiry.
        records = [c.weather_record for c in chips]
        if any(r is None or r.lane != "rest-no-auth" or r.fetched_at is None or r.expires_at is None for r in records):
            return None
        fetched = [r.fetched_at for r in records if r and r.fetched_at is not None]
        expiries = [r.expires_at for r in records if r and r.expires_at is not None]
        if any(not math.isfinite(v) for v in [*fetched, *expiries]) or max(fetched) > now:
            return None
        # Both the visitor and destination day are part of the answer's meaning.
        for zone_name in {policy.time_zone, current.time_zone}:
            local = datetime.fromtimestamp(now, ZoneInfo(zone_name))
            midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), local.tzinfo)
            expiries.append(midnight.timestamp())
        expires = min(now + TTL_SECONDS, *expiries)
        if expires <= now:
            return None
        return CacheEntry(
            scope=scope,
            context=context,
            exact=digest(normalized(question)),
            policy=policy,
            label=f"{place.name} · {policy.intent} · {units}",
            answer=answer,
            evidence=WeatherEvidence(places=places, current=current, forecast=forecast),
            created_at=now,
            expires_at=expires,
            evidence_fetched_at=min(
                r.fetched_at
                for c in chips
                if c.name != "geocode_location" and (r := c.weather_record) is not None and r.fetched_at is not None
            ),
        )
    except (ValueError, KeyError):
        return None


def cached_cards(entry: CacheEntry, now: float) -> tuple[WeatherCard, ...]:
    """Re-render typed evidence without replaying old tool calls, IDs, timings or LangSmith spans."""
    evidence = entry.evidence
    record = ToolCallRecord(
        "rest-no-auth",
        WireRequest(method="GET", url="https://api.open-meteo.com", headers={}),
        0,
        "Cached evidence",
        True,
    )
    outputs = [("geocode_location", evidence.places), ("get_current_weather", evidence.current)]
    if evidence.forecast:
        outputs.append(("get_forecast", evidence.forecast))
    return to_weather_cards(
        [ToolChip(i, name, {}, "done", record, output.model_dump_json()) for i, (name, output) in enumerate(outputs)],
        as_of=datetime.fromtimestamp(now, UTC),
    )
