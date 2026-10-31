"""
tests/unit/test_open_meteo.py: the calls to Open-Meteo, answered with its recorded answers (tests/fixtures/open_meteo/,
from 29 and 30 October 2026) through httpx2's MockTransport: each request as it goes out, the answers in our names,
the second try, each failure as one of ours, and the one line each request writes, which never holds its query string.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from structlog.testing import capture_logs

from nimbus.cache import WeatherCache, to_cache_key
from nimbus.errors import ContractError, UpstreamRateLimitedError, UpstreamTimeoutError, UpstreamUnavailableError
from nimbus.open_meteo import OpenMeteoClient, Place, UpstreamAnswer
from tests.fakes import FakeCacheStore

FIXTURES = Path(__file__).parent.parent / "fixtures" / "open_meteo"
DAILY = "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset"
TRY_SECONDS = 0.05


def fixture(name: str) -> Any:
    """One of Open-Meteo's recorded answers."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def ok(name: str) -> httpx2.Response:
    """Open-Meteo's 200, with a recorded answer."""
    return httpx2.Response(200, json=fixture(name))


async def slow(_request: httpx2.Request) -> httpx2.Response:
    """An answer that comes after the try's time is up."""
    await asyncio.sleep(TRY_SECONDS * 4)
    return ok("geocode-paris")


Answer = httpx2.Response | Exception | Callable[[httpx2.Request], Awaitable[httpx2.Response]]


class OpenMeteoStub:
    """Answers each request with the next answer it was given, and keeps each request and each wait between tries."""

    def __init__(self, *answers: Answer) -> None:
        """The answers, in order."""
        self.answers = list(answers)
        self.requests: list[httpx2.Request] = []
        self.waits: list[float] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """The next answer: a response, an error raised, or one that takes its time."""
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, httpx2.Response):
            return answer
        return await answer(request)

    async def sleep(self, seconds: float) -> None:
        """Keeps the wait between two tries, without waiting."""
        self.waits.append(seconds)


def call[T](stub: OpenMeteoStub, run: Callable[[OpenMeteoClient], Awaitable[T]]) -> T:
    """Runs one call with a client whose HTTP goes to the stub."""

    async def go() -> T:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(stub)) as http:
            return await run(OpenMeteoClient(http, try_seconds=TRY_SECONDS, sleep=stub.sleep))

    return asyncio.run(go())


def test_a_search_asks_for_the_name_in_english_and_gives_the_places_in_our_names() -> None:
    stub = OpenMeteoStub(ok("geocode-paris"))
    answer = call(stub, lambda client: client.search_places("Paris", 5, None))
    assert str(stub.requests[0].url) == (
        "https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json"
    )
    assert answer.data[0] == Place(
        name="Paris",
        region="Île-de-France Region",
        country="France",
        country_code="FR",
        latitude=48.85341,
        longitude=2.3488,
        time_zone="Europe/Paris",
        population=2138551,
    )
    assert answer.request.to_text() == f"GET {stub.requests[0].url}\naccept: application/json"


def test_a_search_in_one_country_names_it_in_capitals() -> None:
    stub = OpenMeteoStub(ok("geocode-springfield"))
    call(stub, lambda client: client.search_places("Springfield", 3, "us"))
    assert str(stub.requests[0].url).endswith("name=Springfield&count=3&language=en&format=json&countryCode=US")


def test_a_name_no_place_has_gives_no_places() -> None:
    answer = call(OpenMeteoStub(ok("geocode-hogwarts")), lambda client: client.search_places("Hogwarts", 5, None))
    assert answer.data == []


def test_a_forecast_asks_for_the_days_and_hours_at_the_point_rounded_to_about_1_km() -> None:
    stub = OpenMeteoStub(ok("forecast-paris"))
    answer = call(
        stub, lambda client: client.get_forecast(48.85341, 2.3488, days=2, include_hourly=True, units="metric")
    )
    assert str(stub.requests[0].url) == (
        f"https://api.open-meteo.com/v1/forecast?latitude=48.85&longitude=2.35&daily={DAILY}"
        "&hourly=temperature_2m,precipitation_probability,weather_code&timezone=auto&forecast_days=2"
    )
    forecast = answer.data
    assert (forecast.time_zone, forecast.temperature_unit) == ("Europe/Paris", "°C")
    first = forecast.days[0]
    assert (first.date, first.weather_code, first.temperature_min, first.temperature_max) == (
        "2026-10-29",
        45,
        5.6,
        15.6,
    )
    assert (first.rain_chance_percent, first.sunrise, first.sunset) == (0, "2026-10-29T07:32", "2026-10-29T17:35")
    assert forecast.hours is not None
    assert len(forecast.hours) == 48
    assert (forecast.hours[1].time, forecast.hours[1].temperature, forecast.hours[1].weather_code) == (
        "2026-10-29T01:00",
        8.8,
        45,
    )


def test_an_imperial_forecast_asks_open_meteo_for_fahrenheit_mph_and_inches() -> None:
    stub = OpenMeteoStub(ok("forecast-dallas-imperial"))
    answer = call(
        stub, lambda client: client.get_forecast(32.78306, -96.80667, days=2, include_hourly=False, units="imperial")
    )
    assert str(stub.requests[0].url) == (
        f"https://api.open-meteo.com/v1/forecast?latitude=32.78&longitude=-96.81&daily={DAILY}&timezone=auto"
        "&forecast_days=2&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
    )
    assert (answer.data.temperature_unit, answer.data.days[0].temperature_max, answer.data.hours) == ("°F", 80.3, None)


def test_an_hourly_forecast_keeps_the_first_3_days_hours_only() -> None:
    # A long forecast's every hour would flood the model: 16 days are 384 hours.
    body = fixture("forecast-paris")
    hourly = body["hourly"]
    body["hourly"] = {name: values * 3 for name, values in hourly.items()}
    answer = call(
        OpenMeteoStub(httpx2.Response(200, json=body)),
        lambda client: client.get_forecast(48.85, 2.35, days=6, include_hourly=True, units="metric"),
    )
    assert answer.data.hours is not None
    assert len(answer.data.hours) == 72


def test_the_weather_now_asks_for_the_point_and_says_day_or_night() -> None:
    stub = OpenMeteoStub(ok("current-tokyo"))
    answer = call(stub, lambda client: client.get_current_weather(35.6895, 139.69171, units="metric"))
    assert str(stub.requests[0].url) == (
        "https://api.open-meteo.com/v1/forecast?latitude=35.69&longitude=139.69"
        "&current=temperature_2m,apparent_temperature,is_day,weather_code,wind_speed_10m&timezone=auto"
    )
    now = answer.data
    assert (now.time_zone, now.observed_at, now.temperature, now.feels_like) == (
        "Asia/Tokyo",
        "2026-10-30T04:00",
        12.0,
        11.3,
    )
    assert (now.is_day, now.weather_code, now.wind_speed, now.wind_speed_unit) == (False, 2, 2.2, "km/h")


def test_the_air_now_asks_for_the_point_and_gives_both_indexes() -> None:
    stub = OpenMeteoStub(ok("air-delhi"))
    answer = call(stub, lambda client: client.get_air_quality(28.6139, 77.209))
    assert str(stub.requests[0].url) == (
        "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=28.61&longitude=77.21"
        "&current=pm2_5,pm10,european_aqi,us_aqi&timezone=auto"
    )
    air = answer.data
    assert (air.time_zone, air.observed_at, air.pm2_5, air.pm10, air.european_aqi, air.us_aqi) == (
        "Asia/Kolkata",
        "2026-10-30T00:30",
        23.2,
        25.8,
        45,
        131,
    )


def search(stub: OpenMeteoStub) -> object:
    """The Paris search, through the stub."""
    return call(stub, lambda client: client.search_places("Paris", 5, None))


@pytest.mark.parametrize(
    "first",
    [httpx2.Response(503), httpx2.ConnectError("refused"), slow],
    ids=["a 503", "no connection", "too slow"],
)
def test_a_failed_try_gets_one_more_after_a_short_random_wait(first: Answer) -> None:
    stub = OpenMeteoStub(first, ok("geocode-paris"))
    with capture_logs() as lines:
        search(stub)
    assert len(stub.requests) == 2
    assert len(stub.waits) == 1
    assert 0 <= stub.waits[0] <= 0.5
    [line] = [line for line in lines if line["event"] == "upstream.http"]
    assert (line["log_level"], line["status"], line["attempts"]) == ("warning", "ok", 2)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ((httpx2.Response(503), httpx2.Response(500)), UpstreamUnavailableError),
        ((httpx2.ConnectError("refused"), httpx2.ConnectError("refused")), UpstreamUnavailableError),
        ((slow, slow), UpstreamTimeoutError),
    ],
    ids=["two 5xx", "no connection twice", "too slow twice"],
)
def test_two_failed_tries_fail_as_one_of_ours(answers: tuple[Answer, Answer], expected: type[Exception]) -> None:
    stub = OpenMeteoStub(*answers)
    with capture_logs() as lines, pytest.raises(expected):
        search(stub)
    assert len(stub.requests) == 2
    [line] = [line for line in lines if line["event"] == "upstream.http"]
    assert (line["status"], line["attempts"], line["errorClass"]) == ("failed", 2, expected.__name__)


def test_a_429_that_asks_for_a_short_wait_is_tried_again_after_it() -> None:
    stub = OpenMeteoStub(httpx2.Response(429, headers={"retry-after": "1"}), ok("geocode-paris"))
    search(stub)
    assert (len(stub.requests), stub.waits) == (2, [1.0])


@pytest.mark.parametrize(
    "retry_after",
    # A long wait; none; a date; and a byte httpx2 reads as "²", a digit to isdigit() that float() refuses (issue 54).
    [b"5", None, b"Fri, 30 Oct 2026 20:00:00 GMT", b"\xb2"],
)
def test_a_429_that_asks_for_a_long_wait_or_none_isn_t_tried_again(retry_after: bytes | None) -> None:
    headers = [] if retry_after is None else [(b"retry-after", retry_after)]
    stub = OpenMeteoStub(httpx2.Response(429, headers=headers))
    with pytest.raises(UpstreamRateLimitedError):
        search(stub)
    assert len(stub.requests) == 1


@pytest.mark.parametrize(
    "answer",
    [
        httpx2.Response(400, json=fixture("error-17-days")),
        httpx2.Response(200, text="<html>not JSON</html>"),
        httpx2.Response(200, json={"results": [{"name": "Paris"}]}),
    ],
    ids=["a 400", "not JSON", "fields missing"],
)
def test_an_answer_we_can_t_read_fails_at_once(answer: httpx2.Response) -> None:
    stub = OpenMeteoStub(answer)
    with pytest.raises(ContractError):
        search(stub)
    assert len(stub.requests) == 1


def test_each_request_writes_one_line_with_its_host_and_path_never_its_query() -> None:
    with capture_logs() as lines:
        search(OpenMeteoStub(ok("geocode-paris")))
    [line] = [line for line in lines if line["event"] == "upstream.http"]
    assert (line["upstream"], line["host"], line["path"]) == (
        "open-meteo",
        "geocoding-api.open-meteo.com",
        "/v1/search",
    )
    assert (line["status"], line["httpStatus"], line["attempts"], line["log_level"]) == ("ok", 200, 1, "info")
    assert isinstance(line["ms"], int)
    assert "Paris" not in json.dumps(line)


# The cache (step 7). Noon in Paris, an hour ahead of UTC, unless a test says otherwise.
NOON_IN_PARIS = 1793444400.0
GEOCODE_ADDRESS = "https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json"


def call_with_cache[T](
    stub: OpenMeteoStub,
    store: FakeCacheStore,
    run: Callable[[OpenMeteoClient], Awaitable[T]],
    now: float = NOON_IN_PARIS,
) -> T:
    """Runs one call with a client whose HTTP goes to the stub, and whose cache is the store."""

    async def go() -> T:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(stub)) as http:
            client = OpenMeteoClient(
                http, cache=WeatherCache(store), try_seconds=TRY_SECONDS, sleep=stub.sleep, clock=lambda: now
            )
            return await run(client)

    return asyncio.run(go())


@pytest.mark.parametrize(
    ("name", "run", "seconds"),
    [
        ("geocode-paris", lambda client: client.search_places("Paris", 5, None), 30 * 24 * 60 * 60),
        (
            "forecast-paris",
            lambda client: client.get_forecast(48.85, 2.35, days=2, include_hourly=False, units="metric"),
            30 * 60,
        ),
        ("current-tokyo", lambda client: client.get_current_weather(35.69, 139.69, units="metric"), 10 * 60),
        ("air-delhi", lambda client: client.get_air_quality(28.65, 77.23), 30 * 60),
    ],
    ids=["a-place-30-days", "a-forecast-30-minutes", "the-weather-now-10-minutes", "the-air-30-minutes"],
)
def test_each_answer_is_kept_under_its_address_hash_for_its_own_time(
    name: str, run: Callable[[OpenMeteoClient], Awaitable[UpstreamAnswer[Any]]], seconds: int
) -> None:
    stub, store = OpenMeteoStub(ok(name)), FakeCacheStore()
    answer = call_with_cache(stub, store, run)
    key = to_cache_key(str(stub.requests[0].url))
    assert answer.from_cache is False
    assert store.items == {key: fixture(name)}
    assert store.ttls == {key: seconds}


def test_an_answer_kept_is_given_again_with_no_request_and_says_so() -> None:
    stub, store = OpenMeteoStub(ok("geocode-paris")), FakeCacheStore()
    first = call_with_cache(stub, store, lambda client: client.search_places("Paris", 5, None))
    with capture_logs() as lines:
        again = call_with_cache(stub, store, lambda client: client.search_places("Paris", 5, None))
    assert len(stub.requests) == 1
    assert (again.data, again.request, again.from_cache) == (first.data, first.request, True)
    [line] = lines
    assert {key: line[key] for key in ("event", "log_level", "host", "path", "status")} == {
        "event": "upstream.cache",
        "log_level": "info",
        "host": "geocoding-api.open-meteo.com",
        "path": "/v1/search",
        "status": "hit",
    }
    assert isinstance(line["ms"], int)


def test_a_forecast_is_kept_no_later_than_its_place_s_midnight() -> None:
    # 23:50 in Paris: its forecast's first day ends in 10 minutes, and so does its time in the cache.
    stub, store = OpenMeteoStub(ok("forecast-paris")), FakeCacheStore()
    ten_to_midnight_in_paris = NOON_IN_PARIS + 11 * 60 * 60 + 50 * 60
    call_with_cache(
        stub,
        store,
        lambda client: client.get_forecast(48.85, 2.35, days=2, include_hourly=False, units="metric"),
        now=ten_to_midnight_in_paris,
    )
    assert list(store.ttls.values()) == [10 * 60]


def test_an_answer_kept_that_no_longer_reads_is_fetched_again_and_kept_in_its_place() -> None:
    stub, store = OpenMeteoStub(ok("geocode-paris")), FakeCacheStore()
    store.items[to_cache_key(GEOCODE_ADDRESS)] = {"results": "not a list"}
    with capture_logs() as lines:
        answer = call_with_cache(stub, store, lambda client: client.search_places("Paris", 5, None))
    assert (len(stub.requests), answer.from_cache) == (1, False)
    assert store.items == {to_cache_key(GEOCODE_ADDRESS): fixture("geocode-paris")}
    assert [(line["event"], line["log_level"], line.get("status")) for line in lines] == [
        ("upstream.cache", "warning", "unreadable"),
        ("upstream.http", "info", "ok"),
    ]


@pytest.mark.parametrize(
    "answers",
    [(httpx2.Response(503), httpx2.Response(503)), (httpx2.Response(200, json={"results": "not a list"}),)],
    ids=["open-meteo-failed", "its-answer-did-not-read"],
)
def test_an_answer_that_failed_is_never_kept(answers: tuple[httpx2.Response, ...]) -> None:
    store = FakeCacheStore()
    with pytest.raises((UpstreamUnavailableError, ContractError)):
        call_with_cache(OpenMeteoStub(*answers), store, lambda client: client.search_places("Paris", 5, None))
    assert store.items == {}


def test_a_cache_that_fails_never_fails_the_answer() -> None:
    stub, store = OpenMeteoStub(ok("geocode-paris")), FakeCacheStore()
    store.error = ConnectionError("the cache is down")
    answer = call_with_cache(stub, store, lambda client: client.search_places("Paris", 5, None))
    assert (answer.data[0].name, answer.from_cache) == ("Paris", False)
