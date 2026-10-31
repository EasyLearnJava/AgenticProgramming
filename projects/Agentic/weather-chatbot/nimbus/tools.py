"""
nimbus/tools.py: the four weather tools, each written once, as a WeatherTool: its name and description for the model,
its input (a Pydantic model, which the model's call must fit), and how it runs with Open-Meteo, giving what the model
reads and its chip's one-line summary. to_langchain_tool() makes one a LangChain tool for REST · no auth: the model
reads the weather; the page also gets the request that fetched it and its time, as the tool message's artifact.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Annotated, Any, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from nimbus.constants import (
    DEFAULT_PLACE_COUNT,
    LANE_ID,
    MAX_FORECAST_DAYS,
    MAX_HOURLY_DAYS,
    MAX_PLACE_COUNT,
    MAX_QUERY_CHARS,
    TOOL_TIMEOUT_SECONDS,
)
from nimbus.errors import UpstreamError, UpstreamTimeoutError
from nimbus.open_meteo import OpenMeteoClient, Place, WireRequest
from nimbus.utils import to_ms
from nimbus.weather import is_ambiguous_place, to_condition

log = structlog.get_logger()

LOCAL_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M"


def _utc_now() -> datetime:
    """The time now, in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class ToolContext:
    """What a tool runs with: the Open-Meteo client, and a clock (the tests pass their own)."""

    open_meteo: OpenMeteoClient
    now: Callable[[], datetime] = field(default=_utc_now)


@dataclass(frozen=True)
class ToolRun:
    """One run of a tool: what the model reads, the request behind it, and the one-line summary for its chip."""

    output: BaseModel
    request: WireRequest
    summary: str


@dataclass(frozen=True)
class WeatherTool:
    """One weather tool: its name and description for the model, its input, and how it runs."""

    name: str
    description: str
    input_model: type[BaseModel]
    run: Callable[[Any, ToolContext], Awaitable[ToolRun]]


# ① The inputs: what the model's call must fit. Each field's description is what the model reads about it.


def _without_additional_properties(schema: dict[str, Any]) -> None:
    """
    Leaves additionalProperties out of the schema the model sees: Gemini's function declarations don't have it, and
    langchain-google-genai would log a warning for each tool at every call to the model. The input is still checked.
    """
    schema.pop("additionalProperties", None)


class _ToolInput(BaseModel):
    """A tool's input: a field the tool doesn't have is refused."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_without_additional_properties)


class GeocodeInput(_ToolInput):
    """geocode_location's input."""

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_CHARS)] = Field(
        description="The place's name. Put a region or country after a comma to narrow it: 'Springfield, MA'."
    )
    count: int = Field(
        default=DEFAULT_PLACE_COUNT,
        ge=1,
        le=MAX_PLACE_COUNT,
        description=f"How many places to return, 1 to {MAX_PLACE_COUNT}; {DEFAULT_PLACE_COUNT} if left out.",
    )
    country_code: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z]{2}$",
        description="An ISO 3166-1 alpha-2 country code, such as 'US', to search that country only.",
    )


class PointInput(_ToolInput):
    """A point on the globe, in degrees: the input the other three tools share."""

    latitude: float = Field(ge=-90, le=90, description="The point's latitude, in degrees.")
    longitude: float = Field(ge=-180, le=180, description="The point's longitude, in degrees.")


class CurrentWeatherInput(PointInput):
    """get_current_weather's input."""

    units: Literal["metric", "imperial"] = Field(description="metric: °C, km/h. imperial: °F, mph.")


class AirQualityInput(PointInput):
    """get_air_quality's input."""


class ForecastInput(PointInput):
    """get_forecast's input."""

    days: int = Field(
        ge=1,
        le=MAX_FORECAST_DAYS,
        description=f"How many days, counting today in that place: 1 to {MAX_FORECAST_DAYS}.",
    )
    include_hourly: bool = Field(
        description=(
            f"Also give each hour of the first {MAX_HOURLY_DAYS} days: for a part of a day, such as an afternoon."
        )
    )
    units: Literal["metric", "imperial"] = Field(description="metric: °C, km/h, mm. imperial: °F, mph, inches.")


# ② The outputs: what the model reads, in plain names, the weather codes in words.


class GeocodeOutput(BaseModel):
    """The places found, and whether the name may mean more than one."""

    candidates: list[Place]
    is_ambiguous: bool


class CurrentWeatherOutput(BaseModel):
    """The weather now at a point."""

    latitude: float
    longitude: float
    time_zone: str
    observed_at: str
    condition: str
    is_day: bool
    temperature: float | None
    feels_like: float | None
    temperature_unit: str
    wind_speed: float | None
    wind_speed_unit: str


class Day(BaseModel):
    """One day of a forecast."""

    date: str
    weekday: str
    condition: str
    temperature_min: float | None
    temperature_max: float | None
    rain_chance_percent: int | None
    sunrise: str | None
    sunset: str | None


class Hour(BaseModel):
    """One hour of a forecast."""

    time: str
    condition: str
    temperature: float | None
    rain_chance_percent: int | None


class ForecastOutput(BaseModel):
    """A point's forecast, with the time there now."""

    latitude: float
    longitude: float
    time_zone: str
    local_now: str
    temperature_unit: str
    days: list[Day]
    hours: list[Hour] | None


class AirQualityOutput(BaseModel):
    """The air now at a point."""

    latitude: float
    longitude: float
    time_zone: str
    observed_at: str
    pm2_5: float | None
    pm10: float | None
    european_aqi: int | None
    us_aqi: int | None


# ③ How each tool runs, and its chip's summary.


def _to_local_now(now: datetime, time_zone: str) -> str:
    """The time now in a place's zone, to the minute: "2026-10-29T20:57"; in UTC when the zone isn't known."""
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return now.astimezone(zone).strftime(LOCAL_TIME_FORMAT)


def _round_point(value: float) -> float:
    """A latitude or longitude as the request sent it: 2 decimals, about 1 km."""
    return round(value, 2)


def _to_place_line(place: Place) -> str:
    """A place, in a few words: "Paris, Île-de-France Region, FR · 48.85, 2.35"."""
    name = ", ".join(part for part in (place.name, place.region, place.country_code) if part)
    return f"{name} · {_round_point(place.latitude)}, {_round_point(place.longitude)}"


async def _geocode(params: GeocodeInput, context: ToolContext) -> ToolRun:
    """The places with the name, and whether it's ambiguous."""
    answer = await context.open_meteo.search_places(params.query, params.count, params.country_code)
    output = GeocodeOutput(candidates=answer.data, is_ambiguous=is_ambiguous_place(answer.data))
    if not output.candidates:
        summary = "No place found"
    elif output.is_ambiguous:
        summary = f"{len(output.candidates)} places, ambiguous"
    else:
        summary = _to_place_line(output.candidates[0])
    return ToolRun(output, answer.request, summary)


async def _current_weather(params: CurrentWeatherInput, context: ToolContext) -> ToolRun:
    """The weather now, its code in words."""
    answer = await context.open_meteo.get_current_weather(params.latitude, params.longitude, units=params.units)
    now = answer.data
    output = CurrentWeatherOutput(
        latitude=_round_point(params.latitude),
        longitude=_round_point(params.longitude),
        time_zone=now.time_zone,
        observed_at=now.observed_at,
        condition=to_condition(now.weather_code),
        is_day=now.is_day,
        temperature=now.temperature,
        feels_like=now.feels_like,
        temperature_unit=now.temperature_unit,
        wind_speed=now.wind_speed,
        wind_speed_unit=now.wind_speed_unit,
    )
    if output.temperature is None:
        summary = output.condition
    else:
        summary = f"{round(output.temperature)} {output.temperature_unit}, {output.condition.lower()}"
    return ToolRun(output, answer.request, summary)


async def _forecast(params: ForecastInput, context: ToolContext) -> ToolRun:
    """The forecast, each day with its weekday and its code in words, and the time there now."""
    answer = await context.open_meteo.get_forecast(
        params.latitude, params.longitude, days=params.days, include_hourly=params.include_hourly, units=params.units
    )
    data = answer.data
    days = [
        Day(
            date=day.date,
            weekday=date.fromisoformat(day.date).strftime("%A"),
            condition=to_condition(day.weather_code),
            temperature_min=day.temperature_min,
            temperature_max=day.temperature_max,
            rain_chance_percent=day.rain_chance_percent,
            sunrise=day.sunrise,
            sunset=day.sunset,
        )
        for day in data.days
    ]
    hours = None
    if data.hours is not None:
        hours = [
            Hour(
                time=hour.time,
                condition=to_condition(hour.weather_code),
                temperature=hour.temperature,
                rain_chance_percent=hour.rain_chance_percent,
            )
            for hour in data.hours
        ]
    output = ForecastOutput(
        latitude=_round_point(params.latitude),
        longitude=_round_point(params.longitude),
        time_zone=data.time_zone,
        local_now=_to_local_now(context.now(), data.time_zone),
        temperature_unit=data.temperature_unit,
        days=days,
        hours=hours,
    )
    return ToolRun(output, answer.request, _summarize_forecast(output))


def _summarize_forecast(output: ForecastOutput) -> str:
    """A forecast in a line: "2 days, hourly · 6 to 16 °C · rain up to 40%"."""
    count = len(output.days)
    span = f"{count} {'day' if count == 1 else 'days'}{', hourly' if output.hours is not None else ''}"
    lows = [day.temperature_min for day in output.days if day.temperature_min is not None]
    highs = [day.temperature_max for day in output.days if day.temperature_max is not None]
    rain = [day.rain_chance_percent for day in output.days if day.rain_chance_percent is not None]
    temperatures = f"{round(min(lows))} to {round(max(highs))} {output.temperature_unit}" if lows and highs else ""
    rain_part = f"rain up to {max(rain)}%" if rain else ""
    return " · ".join(part for part in (span, temperatures, rain_part) if part)


async def _air_quality(params: AirQualityInput, context: ToolContext) -> ToolRun:
    """The air now: both indexes, and PM2.5 and PM10."""
    answer = await context.open_meteo.get_air_quality(params.latitude, params.longitude)
    air = answer.data
    output = AirQualityOutput(
        latitude=_round_point(params.latitude),
        longitude=_round_point(params.longitude),
        **air.model_dump(),
    )
    us = "unknown" if output.us_aqi is None else output.us_aqi
    european = "unknown" if output.european_aqi is None else output.european_aqi
    return ToolRun(output, answer.request, f"US AQI {us} · European AQI {european}")


GEOCODE_LOCATION: Final = WeatherTool(
    name="geocode_location",
    description=(
        "Finds places by name. Returns the candidates (name, region, country, coordinates, time zone, population) and "
        "is_ambiguous: true when the name could mean more than one place. An empty list means no place has that name."
    ),
    input_model=GeocodeInput,
    run=_geocode,
)
GET_CURRENT_WEATHER: Final = WeatherTool(
    name="get_current_weather",
    description=(
        "Gives the weather now at a point: temperature, feels-like temperature, wind, the condition, day or night, "
        "and when it was observed, in the place's local time."
    ),
    input_model=CurrentWeatherInput,
    run=_current_weather,
)
GET_FORECAST: Final = WeatherTool(
    name="get_forecast",
    description=(
        "Gives the forecast for a point, per day (condition, lowest and highest temperature, the highest chance of "
        "rain, sunrise, sunset) and, if asked, per hour. Each day and hour has its date; local_now is the time there "
        "now; times are local."
    ),
    input_model=ForecastInput,
    run=_forecast,
)
GET_AIR_QUALITY: Final = WeatherTool(
    name="get_air_quality",
    description=(
        "Gives the air quality now at a point: PM2.5 and PM10 in μg/m³, the European AQI and the US AQI, and when it "
        "was observed, in the place's local time."
    ),
    input_model=AirQualityInput,
    run=_air_quality,
)
WEATHER_TOOLS: Final = (GEOCODE_LOCATION, GET_CURRENT_WEATHER, GET_FORECAST, GET_AIR_QUALITY)


# ④ A tool on REST · no auth: a LangChain tool that runs it inside the chat's own function.


@dataclass(frozen=True)
class ToolCallRecord:
    """What the page gets of a tool call besides what the model read: the lane, the request, its time and summary."""

    lane: str
    request: WireRequest
    ms: int
    summary: str


def to_langchain_tool(tool: WeatherTool, context: ToolContext) -> StructuredTool:
    """
    One of our tools as a LangChain tool on REST · no auth. The model reads the weather (the tool message's content);
    the page also gets the request and the time (its artifact). Open-Meteo's failure, or a call past its 8 s, reaches
    the model and the chip as our own sentence, a tool error the model can answer with; each call writes one tool.call
    line.
    """

    async def call(**kwargs: Any) -> tuple[str, ToolCallRecord]:
        """Runs the tool, timed: the output's JSON, and the call's record."""
        # LangChain passes only the fields the model gave: checked again here, so the defaults are filled in.
        params = tool.input_model.model_validate(kwargs)
        started = time.perf_counter()
        try:
            async with asyncio.timeout(TOOL_TIMEOUT_SECONDS):
                tool_run = await tool.run(params, context)
        except (UpstreamError, TimeoutError) as error:
            # A call past its own time limit, its tries included, failed as Open-Meteo's slowness does.
            failure = error if isinstance(error, UpstreamError) else UpstreamTimeoutError()
            ms = to_ms(time.perf_counter() - started)
            failed = {"status": "failed", "ms": ms, "errorClass": type(failure).__name__}
            log.info("tool.call", tool=tool.name, lane=LANE_ID, **failed)
            raise ToolException(failure.user_message) from error
        ms = to_ms(time.perf_counter() - started)
        log.info("tool.call", tool=tool.name, lane=LANE_ID, status="ok", ms=ms)
        return tool_run.output.model_dump_json(), ToolCallRecord(LANE_ID, tool_run.request, ms, tool_run.summary)

    return StructuredTool.from_function(
        coroutine=call,
        name=tool.name,
        description=tool.description,
        args_schema=tool.input_model,
        response_format="content_and_artifact",
        handle_tool_error=True,
    )


def make_tools(context: ToolContext) -> list[StructuredTool]:
    """The four weather tools, as LangChain tools on REST · no auth, all with the same context."""
    return [to_langchain_tool(tool, context) for tool in WEATHER_TOOLS]
