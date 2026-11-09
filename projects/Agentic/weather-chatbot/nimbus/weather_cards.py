"""Weather presentation built from successful tool evidence, independently of the model's prose."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ValidationError

from nimbus.chips import ToolChip
from nimbus.tools import CurrentWeatherOutput, ForecastOutput, GeocodeOutput, round_point


@dataclass(frozen=True)
class WeatherDay:
    """One forecast day, with explicit dates and absent values preserved."""

    date: str
    label: str
    date_label: str
    condition: str
    icon: str
    low: float | None
    high: float | None
    rain: int | None
    sunrise: str | None
    sunset: str | None


@dataclass(frozen=True)
class WeatherHour:
    """An upcoming hourly sample, labelled in the forecast's local time."""

    label: str
    date_label: str
    temperature: float | None
    rain: int | None
    condition: str
    icon: str


@dataclass(frozen=True)
class WeatherCard:
    """Compatible current conditions and forecast evidence for one coordinate pair and unit system."""

    location: str
    coordinates: str
    time_zone: str
    temperature_unit: str
    current: CurrentWeatherOutput | None
    current_icon: str
    observed_label: str
    days: tuple[WeatherDay, ...]
    hours: tuple[WeatherHour, ...]
    forecast_label: str
    cached: bool
    source: str


@dataclass
class _WeatherGroup:
    """The latest successful result of each kind; older results cannot overwrite its provenance."""

    current: CurrentWeatherOutput | None = None
    forecast: ForecastOutput | None = None
    current_chip: ToolChip | None = None
    forecast_chip: ToolChip | None = None


def _read[T: BaseModel](chip: ToolChip, model: type[T]) -> T | None:
    """Validate normalized tool JSON; malformed or unfinished evidence has no visual enhancement."""
    if chip.status != "done" or chip.output is None:
        return None
    try:
        return model.model_validate_json(chip.output)
    except (ValidationError, ValueError):
        return None


def _number(value: float | None) -> float | None:
    """Keep zero and negative values, while non-finite provider values remain unavailable."""
    return value if value is not None and math.isfinite(value) else None


def _rain(value: int | None) -> int | None:
    """A probability is a percentage, including zero, never an amount of rainfall."""
    return value if value is not None and 0 <= value <= 100 else None


def _local(value: str | None, zone: str) -> datetime | None:
    """Read provider local ISO times; an explicit offset is converted to the destination's zone."""
    if value is None:
        return None
    try:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is not None:
            moment = moment.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
        return moment
    except (ValueError, OverflowError, ZoneInfoNotFoundError):
        return None


def _clock(moment: datetime, *, hourly: bool = False) -> str:
    """An accessible local clock label without a leading zero."""
    return moment.strftime("%I %p" if hourly else "%I:%M %p").lstrip("0")


def _stamp(value: str, zone: str) -> str:
    """An explicit date and time, never an inferred observation or forecast issue time."""
    moment = _local(value, zone)
    return f"{moment:%b} {moment.day}, {moment.year} · {_clock(moment)}" if moment else "Time unavailable"


def _icon(condition: str, *, is_day: bool = True) -> str:
    """A decorative condition category; the original condition text always accompanies it."""
    lowered = condition.lower()
    if lowered.startswith("unknown"):
        return "unknown"
    if lowered == "partly cloudy":
        return "partly" if is_day else "cloud"
    for fragment, icon in (
        ("thunderstorm", "storm"),
        ("snow", "snow"),
        ("rain", "rain"),
        ("drizzle", "rain"),
        ("fog", "fog"),
        ("overcast", "cloud"),
    ):
        if fragment in lowered:
            return icon
    if lowered in {"clear sky", "mainly clear"}:
        return "clear" if is_day else "night"
    return "unknown"


def _days(forecast: ForecastOutput) -> tuple[WeatherDay, ...]:
    """Keep every valid requested day, using the destination day for Today and Tomorrow."""
    now = _local(forecast.local_now, forecast.time_zone)
    days = []
    for day in forecast.days:
        moment = _local(day.date, forecast.time_zone)
        if moment is None:
            continue
        label = moment.strftime("%a")
        if now is not None:
            if moment.date() == now.date():
                label = "Today"
            elif (moment.date() - now.date()).days == 1:
                label = "Tomorrow"
        sunrise = _local(day.sunrise, forecast.time_zone)
        sunset = _local(day.sunset, forecast.time_zone)
        days.append(
            WeatherDay(
                date=day.date,
                label=label,
                date_label=f"{moment:%b} {moment.day}",
                condition=day.condition,
                icon=_icon(day.condition),
                low=_number(day.temperature_min),
                high=_number(day.temperature_max),
                rain=_rain(day.rain_chance_percent),
                sunrise=_clock(sunrise) if sunrise else None,
                sunset=_clock(sunset) if sunset else None,
            )
        )
    return tuple(days)


def _hour_icon(condition: str, moment: datetime, forecast: ForecastOutput) -> str:
    """Use actual daylight boundaries; omit a sun or moon when their timing is unavailable."""
    for day in forecast.days:
        if day.date != moment.date().isoformat():
            continue
        sunrise = _local(day.sunrise, forecast.time_zone)
        sunset = _local(day.sunset, forecast.time_zone)
        if sunrise is not None and sunset is not None and sunrise < sunset:
            return _icon(condition, is_day=sunrise <= moment < sunset)
    icon = _icon(condition)
    return "" if icon in {"clear", "partly"} else icon


def _hours(forecast: ForecastOutput, as_of: datetime | None = None) -> tuple[WeatherHour, ...]:
    """Show up to six available upcoming samples, never relabel past hours as upcoming."""
    now = (
        as_of.astimezone(ZoneInfo(forecast.time_zone)).replace(tzinfo=None)
        if as_of is not None
        else _local(forecast.local_now, forecast.time_zone)
    )
    if now is None:
        return ()
    samples = []
    for hour in forecast.hours or ():
        moment = _local(hour.time, forecast.time_zone)
        if moment is not None and moment >= now:
            samples.append((moment, hour))
    samples.sort(key=lambda sample: sample[0])
    return tuple(
        WeatherHour(
            label=_clock(moment, hourly=True),
            date_label=f"{moment:%b} {moment.day}",
            temperature=_number(hour.temperature),
            rain=_rain(hour.rain_chance_percent),
            condition=hour.condition,
            icon=_hour_icon(hour.condition, moment, forecast),
        )
        for moment, hour in samples[:6]
    )


def _place_names(chips: Sequence[ToolChip]) -> dict[tuple[float, float], str]:
    """Name only matching coordinate pairs, never the last requested or first returned city."""
    places: dict[tuple[float, float], set[str]] = {}
    for chip in chips:
        if chip.name != "geocode_location" or (result := _read(chip, GeocodeOutput)) is None:
            continue
        for place in result.candidates:
            key = round_point(place.latitude), round_point(place.longitude)
            label = ", ".join(part for part in (place.name, place.region, place.country_code) if part)
            places.setdefault(key, set()).add(label)
    return {key: next(iter(names)) for key, names in places.items() if len(names) == 1}


def _card(group: _WeatherGroup, names: dict[tuple[float, float], str], as_of: datetime | None = None) -> WeatherCard:
    """Format one evidence group, retaining source and cache information for its displayed results."""
    result = group.current or group.forecast
    assert result is not None  # noqa: S101 - populated only after a validated weather result
    coordinates = f"{result.latitude:.2f}, {result.longitude:.2f}"
    place_key = round_point(result.latitude), round_point(result.longitude)
    current, forecast = group.current, group.forecast
    if current:
        current = current.model_copy(
            update={
                "temperature": _number(current.temperature),
                "feels_like": _number(current.feels_like),
                "wind_speed": _number(current.wind_speed),
            }
        )
    chips = [chip for chip in (group.current_chip, group.forecast_chip) if chip]
    records = [chip.weather_record for chip in chips]
    open_meteo = all(
        record is not None
        and (
            record.request.host == "api.open-meteo.com"
            or (record.upstream_request is not None and record.upstream_request.host == "api.open-meteo.com")
        )
        for record in records
    )
    return WeatherCard(
        location=names.get(place_key, f"Weather at {coordinates}"),
        coordinates=coordinates,
        time_zone=result.time_zone,
        temperature_unit=result.temperature_unit,
        current=current,
        current_icon=_icon(current.condition, is_day=current.is_day) if current else "unknown",
        observed_label=_stamp(current.observed_at, current.time_zone) if current else "",
        days=_days(forecast) if forecast else (),
        hours=_hours(forecast, as_of) if forecast else (),
        forecast_label=_stamp(forecast.local_now, forecast.time_zone) if forecast else "",
        cached=any(record is not None and record.from_cache for record in records),
        source="Open-Meteo" if open_meteo else "Weather tools",
    )


def to_weather_cards(chips: Sequence[ToolChip], *, as_of: datetime | None = None) -> tuple[WeatherCard, ...]:
    """Build cards only from validated successful weather tools, grouped by place, zone and returned units."""
    groups: dict[tuple[float, float, str, str], _WeatherGroup] = {}
    # ① The card follows the tool evidence, never numbers or place names extracted from generated prose.
    for chip in chips:
        result: CurrentWeatherOutput | ForecastOutput | None = None
        if chip.name == "get_current_weather":
            result = _read(chip, CurrentWeatherOutput)
        elif chip.name == "get_forecast":
            result = _read(chip, ForecastOutput)
        if result is None or not (-90 <= result.latitude <= 90 and -180 <= result.longitude <= 180):
            continue
        key = round_point(result.latitude), round_point(result.longitude), result.time_zone, result.temperature_unit
        group = groups.setdefault(key, _WeatherGroup())
        if isinstance(result, CurrentWeatherOutput):
            group.current, group.current_chip = result, chip
        else:
            group.forecast, group.forecast_chip = result, chip
    # ② Matching geocoded names are optional. Coordinates remain explicit when a reliable label is unavailable.
    names = _place_names(chips)
    return tuple(_card(group, names, as_of) for group in groups.values())
