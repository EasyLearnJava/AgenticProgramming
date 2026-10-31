"""
nimbus/actor.py: the forecast on the lanes with auth (step 10), by Apify's Actor gochujang/open-meteo-weather-forecast,
which asks Open-Meteo itself, behind Apify's token. Its input comes from get_forecast's: one location, named by its
point, rounded as every request rounds it; the days; and daily or hourly, hourly for at most 3 days, as get_forecast
gives hours, and then with no days, since the Actor's hours carry no day's summary. Its items, one a day or one an
hour, in °C, are read into the same forecast get_forecast gives, in °F when asked, since the Actor has no such option.
An answer in any other shape, or not for the place and days asked, is a ContractError naming the field, never its value.
"""

from datetime import date, datetime, timedelta
from itertools import pairwise
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from nimbus.constants import MAX_HOURLY_DAYS
from nimbus.errors import ContractError
from nimbus.tools import Day, ForecastInput, ForecastOutput, Hour, round_point, summarize_forecast, to_local_now
from nimbus.weather import to_condition

# Items for the place asked: within about 1 km of the point sent, which the Actor echoes back.
SAME_PLACE_DEGREES: Final = 0.01
CELSIUS: Final = "°C"
FAHRENHEIT: Final = "°F"


class _ActorItem(BaseModel):
    """What every item carries: the place, as the Actor names and finds it."""

    model_config = ConfigDict(extra="ignore")

    location: str
    latitude: float
    longitude: float
    timezone: str


class _DailyItem(_ActorItem):
    """One day, in °C."""

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    weather_code: int | None
    temp_max_c: float | None
    temp_min_c: float | None
    precipitation_probability_pct: int | None
    sunrise: str | None
    sunset: str | None


class _HourlyItem(_ActorItem):
    """One hour, in °C."""

    datetime: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    weather_code: int | None
    temperature_c: float | None
    precipitation_probability_pct: int | None


def to_actor_input(params: ForecastInput) -> dict[str, Any]:
    """The Actor's input for a forecast: the point, named by itself; the days; daily, or hourly for at most 3 days."""
    latitude, longitude = round_point(params.latitude), round_point(params.longitude)
    days = min(params.days, MAX_HOURLY_DAYS) if params.include_hourly else params.days
    location = {"name": f"{latitude}, {longitude}", "latitude": latitude, "longitude": longitude}
    mode: Literal["daily", "hourly"] = "hourly" if params.include_hourly else "daily"
    return {"locations": [location], "forecastDays": days, "mode": mode}


def to_temperature(celsius: float | None, units: str) -> float | None:
    """A temperature in the units asked: as the Actor gave it in °C, or in °F, to a tenth."""
    if celsius is None or units == "metric":
        return celsius
    return round(celsius * 9 / 5 + 32, 1)


def _read[Item: _ActorItem](items: list[Any], model: type[Item]) -> list[Item]:
    """The items, each checked; none, or one of another shape, is a ContractError naming the field."""
    if not items:
        raise ContractError
    try:
        return [model.model_validate(item) for item in items]
    except ValidationError as error:
        raise ContractError from error


def _check_place(items: list[_DailyItem] | list[_HourlyItem], latitude: float, longitude: float) -> None:
    """Every item for the one place asked: the point sent, and one name and time zone throughout."""
    first = items[0]
    for item in items:
        near = (
            abs(item.latitude - latitude) <= SAME_PLACE_DEGREES
            and abs(item.longitude - longitude) <= SAME_PLACE_DEGREES
        )
        if not near or (item.location, item.timezone) != (first.location, first.timezone):
            raise ContractError


def _check_days(dates: list[str], forecast_days: int, *, once_each: bool) -> None:
    """The days asked, all there, one after another; in daily mode, each once."""
    days = list(dict.fromkeys(dates))
    if len(days) != forecast_days or (once_each and len(dates) != len(days)):
        raise ContractError
    for previous, current in pairwise(days):
        if date.fromisoformat(current) != date.fromisoformat(previous) + timedelta(days=1):
            raise ContractError


def to_forecast(items: list[Any], params: ForecastInput, now: datetime) -> ForecastOutput:
    """The Actor's items as the forecast get_forecast gives: its days, or, in hourly mode, its hours alone."""
    actor_input = to_actor_input(params)
    location = actor_input["locations"][0]
    unit = FAHRENHEIT if params.units == "imperial" else CELSIUS
    place: _ActorItem
    if actor_input["mode"] == "daily":
        daily = _read(items, _DailyItem)
        _check_place(daily, location["latitude"], location["longitude"])
        _check_days([item.date for item in daily], actor_input["forecastDays"], once_each=True)
        days = [
            Day(
                date=item.date,
                weekday=date.fromisoformat(item.date).strftime("%A"),
                condition=to_condition(item.weather_code),
                temperature_min=to_temperature(item.temp_min_c, params.units),
                temperature_max=to_temperature(item.temp_max_c, params.units),
                rain_chance_percent=item.precipitation_probability_pct,
                sunrise=item.sunrise,
                sunset=item.sunset,
            )
            for item in daily
        ]
        place, hours = daily[0], None
    else:
        hourly = _read(items, _HourlyItem)
        _check_place(hourly, location["latitude"], location["longitude"])
        _check_days([item.datetime[:10] for item in hourly], actor_input["forecastDays"], once_each=False)
        days = []
        hours = [
            Hour(
                time=item.datetime,
                condition=to_condition(item.weather_code),
                temperature=to_temperature(item.temperature_c, params.units),
                rain_chance_percent=item.precipitation_probability_pct,
            )
            for item in hourly
        ]
        place = hourly[0]
    return ForecastOutput(
        latitude=location["latitude"],
        longitude=location["longitude"],
        time_zone=place.timezone,
        local_now=to_local_now(now, place.timezone),
        temperature_unit=unit,
        days=days,
        hours=hours,
    )


def summarize_actor_forecast(output: ForecastOutput) -> str:
    """A forecast in a line: get_forecast's for days; for hours alone, "24 hours · 20 to 27 °C · rain up to 17%"."""
    if output.days or not output.hours:
        return summarize_forecast(output)
    temperatures = [hour.temperature for hour in output.hours if hour.temperature is not None]
    rain = [hour.rain_chance_percent for hour in output.hours if hour.rain_chance_percent is not None]
    span = f"{len(output.hours)} hours"
    low_high = (
        f"{round(min(temperatures))} to {round(max(temperatures))} {output.temperature_unit}" if temperatures else ""
    )
    rain_part = f"rain up to {max(rain)}%" if rain else ""
    return " · ".join(part for part in (span, low_high, rain_part) if part)
