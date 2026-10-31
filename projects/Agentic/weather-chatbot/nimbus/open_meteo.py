"""
nimbus/open_meteo.py: the calls to Open-Meteo's three APIs (geocoding, forecast, air quality), through httpx2: each
point rounded to about 1 km, times in the place's own zone, 3 s a try and one more try after a short random wait
(tenacity), a 429 tried again only when it asks for a short wait. Open-Meteo's own names (admin1, temperature_2m) stay
in this file: its answers are checked and renamed to ours here, once. Each request that goes out writes one
upstream.http line, with its host and path, never its query string, which names the place.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final, Literal
from urllib.parse import urlencode, urlsplit

import httpx2
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt

from nimbus.constants import (
    COORDINATE_DECIMALS,
    MAX_HOURLY_DAYS,
    OPEN_METEO_AIR_QUALITY_URL,
    OPEN_METEO_ATTEMPTS,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_TRY_SECONDS,
    RETRY_AFTER_MAX_SECONDS,
    RETRY_WAIT_MAX_SECONDS,
)
from nimbus.errors import (
    ContractError,
    UpstreamError,
    UpstreamRateLimitedError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from nimbus.utils import to_ms

log = structlog.get_logger()

type Units = Literal["metric", "imperial"]

HOURS_PER_DAY: Final = 24
HTTP_OK: Final = 200
HTTP_TOO_MANY_REQUESTS: Final = 429
HTTP_SERVER_ERROR: Final = 500
DAILY_FIELDS: Final = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
HOURLY_FIELDS: Final = "temperature_2m,precipitation_probability,weather_code"
CURRENT_FIELDS: Final = "temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m"
AIR_QUALITY_FIELDS: Final = "pm2_5,pm10,european_aqi,us_aqi"
IMPERIAL_PARAMS: Final = {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"}


class WireRequest(BaseModel):
    """A request as it went out, for a tool call's chip: its method, its address and its headers."""

    model_config = ConfigDict(frozen=True)

    method: str
    url: str
    headers: dict[str, str]

    @property
    def host(self) -> str:
        """The host it went to: "api.open-meteo.com"."""
        return urlsplit(self.url).netloc

    @property
    def path(self) -> str:
        """Its path, without the query string: "/v1/forecast"."""
        return urlsplit(self.url).path

    def to_text(self) -> str:
        """The request as it was written: its first line, then a line for each header."""
        return "\n".join([f"{self.method} {self.url}", *(f"{name}: {value}" for name, value in self.headers.items())])


# ① What Open-Meteo answers, checked, in our names. A field we don't read is left out.


class Place(BaseModel):
    """A place the geocoding found: Open-Meteo's admin1 is our region, its timezone our time_zone."""

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    name: str
    region: str | None = Field(default=None, validation_alias="admin1")
    country: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float
    time_zone: str | None = Field(default=None, validation_alias="timezone")
    population: int | None = None


class _GeocodingAnswer(BaseModel):
    """The geocoding's answer: no results at all when no place has the name."""

    results: list[Place] = Field(default_factory=list)


class _DailyUnits(BaseModel):
    """The units of a forecast's days: its temperatures' unit, °C or °F."""

    temperature_2m_max: str


class _Daily(BaseModel):
    """A forecast's days, as Open-Meteo gives them: a list for each field, a value for each day."""

    time: list[str]
    weather_code: list[int | None]
    temperature_2m_max: list[float | None]
    temperature_2m_min: list[float | None]
    precipitation_probability_max: list[int | None]
    sunrise: list[str | None]
    sunset: list[str | None]


class _Hourly(BaseModel):
    """A forecast's hours, as Open-Meteo gives them."""

    time: list[str]
    temperature_2m: list[float | None]
    precipitation_probability: list[int | None]
    weather_code: list[int | None]


class _ForecastAnswer(BaseModel):
    """A forecast, as Open-Meteo gives it."""

    timezone: str
    daily_units: _DailyUnits
    daily: _Daily
    hourly: _Hourly | None = None


class DayData(BaseModel):
    """One day of a forecast, in the place's own time."""

    date: str
    weather_code: int | None
    temperature_min: float | None
    temperature_max: float | None
    rain_chance_percent: int | None
    sunrise: str | None
    sunset: str | None


class HourData(BaseModel):
    """One hour of a forecast, in the place's own time."""

    time: str
    temperature: float | None
    rain_chance_percent: int | None
    weather_code: int | None


class ForecastData(BaseModel):
    """A forecast: the place's time zone, the temperatures' unit, its days, and its hours, if they were asked for."""

    time_zone: str
    temperature_unit: str
    days: list[DayData]
    hours: list[HourData] | None


class _CurrentUnits(BaseModel):
    """The units of the weather now."""

    temperature_2m: str
    wind_speed_10m: str


class _Current(BaseModel):
    """The weather now, as Open-Meteo gives it: is_day is 1 or 0."""

    time: str
    temperature_2m: float | None
    apparent_temperature: float | None
    is_day: int
    weather_code: int | None
    wind_speed_10m: float | None


class _CurrentAnswer(BaseModel):
    """The weather now, with its units and the place's time zone."""

    timezone: str
    current_units: _CurrentUnits
    current: _Current


class CurrentData(BaseModel):
    """The weather now at a point, in our names."""

    time_zone: str
    observed_at: str
    temperature: float | None
    feels_like: float | None
    temperature_unit: str
    is_day: bool
    weather_code: int | None
    wind_speed: float | None
    wind_speed_unit: str


class _AirNow(BaseModel):
    """The air now, as Open-Meteo gives it."""

    time: str
    pm2_5: float | None
    pm10: float | None
    european_aqi: int | None
    us_aqi: int | None


class _AirQualityAnswer(BaseModel):
    """The air now, with the place's time zone."""

    timezone: str
    current: _AirNow


class AirQualityData(BaseModel):
    """The air now at a point, in our names: PM2.5 and PM10 in μg/m³, and the European and US indexes."""

    time_zone: str
    observed_at: str
    pm2_5: float | None
    pm10: float | None
    european_aqi: int | None
    us_aqi: int | None


def _at[T](values: list[T | None], index: int) -> T | None:
    """A value from one of Open-Meteo's lists, or None when the list is shorter."""
    return values[index] if index < len(values) else None


def _to_forecast(answer: _ForecastAnswer, include_hourly: bool) -> ForecastData:
    """
    A forecast in our names: its hours only when they were asked for, and then cut to the first 3 days', so a long one
    doesn't flood the model.
    """
    daily = answer.daily
    days = [
        DayData(
            date=date,
            weather_code=_at(daily.weather_code, index),
            temperature_min=_at(daily.temperature_2m_min, index),
            temperature_max=_at(daily.temperature_2m_max, index),
            rain_chance_percent=_at(daily.precipitation_probability_max, index),
            sunrise=_at(daily.sunrise, index),
            sunset=_at(daily.sunset, index),
        )
        for index, date in enumerate(daily.time)
    ]
    hours = None
    if include_hourly and answer.hourly is not None:
        hourly = answer.hourly
        hours = [
            HourData(
                time=moment,
                temperature=_at(hourly.temperature_2m, index),
                rain_chance_percent=_at(hourly.precipitation_probability, index),
                weather_code=_at(hourly.weather_code, index),
            )
            for index, moment in enumerate(hourly.time[: MAX_HOURLY_DAYS * HOURS_PER_DAY])
        ]
    return ForecastData(
        time_zone=answer.timezone, temperature_unit=answer.daily_units.temperature_2m_max, days=days, hours=hours
    )


def _to_current(answer: _CurrentAnswer) -> CurrentData:
    """The weather now in our names."""
    now = answer.current
    return CurrentData(
        time_zone=answer.timezone,
        observed_at=now.time,
        temperature=now.temperature_2m,
        feels_like=now.apparent_temperature,
        temperature_unit=answer.current_units.temperature_2m,
        is_day=now.is_day == 1,
        weather_code=now.weather_code,
        wind_speed=now.wind_speed_10m,
        wind_speed_unit=answer.current_units.wind_speed_10m,
    )


def _to_air_quality(answer: _AirQualityAnswer) -> AirQualityData:
    """The air now in our names."""
    air = answer.current
    return AirQualityData(
        time_zone=answer.timezone,
        observed_at=air.time,
        pm2_5=air.pm2_5,
        pm10=air.pm10,
        european_aqi=air.european_aqi,
        us_aqi=air.us_aqi,
    )


# ② The requests: a point rounded to 2 decimals, about 1 km, so no request names an exact address; times in the place's
# own zone (timezone=auto); imperial units by Open-Meteo's own conversion.


def _to_point(latitude: float, longitude: float) -> dict[str, str]:
    """A point's part of a query: its coordinates, rounded."""
    return {
        "latitude": str(round(latitude, COORDINATE_DECIMALS)),
        "longitude": str(round(longitude, COORDINATE_DECIMALS)),
    }


def _to_get_request(base_url: str, params: dict[str, str]) -> WireRequest:
    """A GET to one of Open-Meteo's APIs; commas stay as they are, as in Open-Meteo's own examples."""
    return WireRequest(
        method="GET", url=f"{base_url}?{urlencode(params, safe=',')}", headers={"accept": "application/json"}
    )


def _to_units(units: Units) -> dict[str, str]:
    """The units' part of a query: nothing for metric, Open-Meteo's default."""
    return dict(IMPERIAL_PARAMS) if units == "imperial" else {}


# ③ Each try, and when a failed one is worth another.


def _to_retry_after(value: str | None) -> float | None:
    """
    A 429's Retry-After, in seconds, when it gives them in ASCII digits; an HTTP date, or none, gives None. isdigit()
    alone would take "²", which float() refuses (issue 54).
    """
    if value is None or not (value.strip().isascii() and value.strip().isdecimal()):
        return None
    return float(value)


def _is_worth_retrying(error: BaseException) -> bool:
    """A timeout or a 5xx is worth one more try; so is a 429 that asks for a short wait."""
    if isinstance(error, UpstreamRateLimitedError):
        return error.retry_after_seconds is not None and error.retry_after_seconds <= RETRY_AFTER_MAX_SECONDS
    return isinstance(error, (UpstreamTimeoutError, UpstreamUnavailableError))


@dataclass(frozen=True)
class UpstreamAnswer[T]:
    """One answer from Open-Meteo, in our names, and the request that fetched it."""

    data: T
    request: WireRequest


class OpenMeteoClient:
    """Open-Meteo's three APIs, through an HTTP client that the caller opens and closes."""

    def __init__(
        self,
        http: httpx2.AsyncClient,
        *,
        try_seconds: float = OPEN_METEO_TRY_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """The HTTP client; how long a try may take, and how to wait between two (the tests pass their own)."""
        self._http = http
        self._try_seconds = try_seconds
        self._sleep = sleep

    async def search_places(self, query: str, count: int, country_code: str | None) -> UpstreamAnswer[list[Place]]:
        """The places with a name, in English, at most count of them, in one country if it's given."""
        params = {"name": query, "count": str(count), "language": "en", "format": "json"}
        if country_code is not None:
            params["countryCode"] = country_code.upper()
        request = _to_get_request(OPEN_METEO_GEOCODING_URL, params)
        answer = await self._get(request, _GeocodingAnswer)
        return UpstreamAnswer(answer.results, request)

    async def get_forecast(
        self, latitude: float, longitude: float, *, days: int, include_hourly: bool, units: Units
    ) -> UpstreamAnswer[ForecastData]:
        """A point's forecast: its days, and the first 3 days' hours if they're asked for."""
        params = {**_to_point(latitude, longitude), "daily": DAILY_FIELDS}
        if include_hourly:
            params["hourly"] = HOURLY_FIELDS
        params |= {"timezone": "auto", "forecast_days": str(days), **_to_units(units)}
        request = _to_get_request(OPEN_METEO_FORECAST_URL, params)
        return UpstreamAnswer(_to_forecast(await self._get(request, _ForecastAnswer), include_hourly), request)

    async def get_current_weather(
        self, latitude: float, longitude: float, *, units: Units
    ) -> UpstreamAnswer[CurrentData]:
        """The weather now at a point."""
        params = {**_to_point(latitude, longitude), "current": CURRENT_FIELDS, "timezone": "auto", **_to_units(units)}
        request = _to_get_request(OPEN_METEO_FORECAST_URL, params)
        return UpstreamAnswer(_to_current(await self._get(request, _CurrentAnswer)), request)

    async def get_air_quality(self, latitude: float, longitude: float) -> UpstreamAnswer[AirQualityData]:
        """The air now at a point."""
        params = {**_to_point(latitude, longitude), "current": AIR_QUALITY_FIELDS, "timezone": "auto"}
        request = _to_get_request(OPEN_METEO_AIR_QUALITY_URL, params)
        return UpstreamAnswer(_to_air_quality(await self._get(request, _AirQualityAnswer)), request)

    async def _get[M: BaseModel](self, request: WireRequest, schema: type[M]) -> M:
        """
        One GET: a try, and one more if the first was worth it; the answer checked against the schema; one line, when
        it's done, with the host, the path, the time and the tries. A retry is a warning. A stop isn't logged.
        """
        started = time.perf_counter()
        attempts = 0
        fields = {"upstream": "open-meteo", "host": request.host, "path": request.path}
        retrying = AsyncRetrying(
            stop=stop_after_attempt(OPEN_METEO_ATTEMPTS),
            retry=retry_if_exception(_is_worth_retrying),
            wait=_to_wait,
            sleep=self._sleep,
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    attempts += 1
                    body = await self._fetch_once(request)
        except UpstreamError as error:
            ms = to_ms(time.perf_counter() - started)
            log.info(
                "upstream.http", **fields, status="failed", ms=ms, attempts=attempts, errorClass=type(error).__name__
            )
            raise
        ms = to_ms(time.perf_counter() - started)
        write = log.warning if attempts > 1 else log.info
        write("upstream.http", **fields, status="ok", httpStatus=HTTP_OK, ms=ms, attempts=attempts)
        try:
            return schema.model_validate(body)
        except ValidationError as error:
            raise ContractError from error

    async def _fetch_once(self, request: WireRequest) -> Any:
        """One try, of at most 3 s: the answer's JSON, or one of our errors."""
        try:
            async with asyncio.timeout(self._try_seconds):
                response = await self._http.get(request.url, headers=request.headers)
                if response.status_code == HTTP_TOO_MANY_REQUESTS:
                    raise UpstreamRateLimitedError(_to_retry_after(response.headers.get("retry-after")))
                if response.status_code >= HTTP_SERVER_ERROR:
                    raise UpstreamUnavailableError
                if response.status_code != HTTP_OK:
                    raise ContractError
                return response.json()
        except (TimeoutError, httpx2.TimeoutException) as error:
            raise UpstreamTimeoutError from error
        except httpx2.HTTPError as error:
            raise UpstreamUnavailableError from error
        except ValueError as error:
            raise ContractError from error


def _to_wait(state: RetryCallState) -> float:
    """How long to wait before the second try: what a 429 asked for, else a random wait of at most half a second."""
    error = state.outcome.exception() if state.outcome is not None else None
    if isinstance(error, UpstreamRateLimitedError) and error.retry_after_seconds is not None:
        return error.retry_after_seconds
    # A random wait, so many copies of the app retrying at once don't all come back at the same moment: no secret.
    return random.uniform(0, RETRY_WAIT_MAX_SECONDS)  # noqa: S311
