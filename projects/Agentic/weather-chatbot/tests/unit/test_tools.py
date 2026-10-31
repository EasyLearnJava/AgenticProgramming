"""
tests/unit/test_tools.py: the four weather tools, on Open-Meteo's recorded answers: what each gives the model, its
chip's one-line summary, the inputs the model may give, the schema the model sees, and each one as a LangChain tool on
REST · no auth: the weather for the model, the request and its time for the page, and a failure as our own sentence.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError
from structlog.testing import capture_logs

from nimbus.errors import WEATHER_UNREACHABLE
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import (
    GEOCODE_LOCATION,
    GET_AIR_QUALITY,
    GET_CURRENT_WEATHER,
    GET_FORECAST,
    WEATHER_TOOLS,
    ToolCallRecord,
    ToolContext,
    ToolRun,
    WeatherTool,
    to_langchain_tool,
)
from tests.fakes import OpenMeteoRecordings

# 19:57 UTC on 29 October 2026: 20:57 in Paris, an hour ahead since its clocks went back.
NOW = datetime(2026, 10, 29, 19, 57, tzinfo=UTC)
PARIS = {"latitude": 48.85341, "longitude": 2.3488}


def run(tool: WeatherTool, args: dict[str, Any]) -> ToolRun:
    """One run of a tool, its input checked as the model's call would be, against the recorded answers."""

    async def go() -> ToolRun:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(OpenMeteoRecordings())) as http:
            context = ToolContext(OpenMeteoClient(http), now=lambda: NOW)
            return await tool.run(tool.input_model.model_validate(args), context)

    return asyncio.run(go())


def output(tool_run: ToolRun) -> Any:
    """What the model reads of a run: its output's JSON."""
    return json.loads(tool_run.output.model_dump_json())


def test_geocoding_gives_the_places_and_whether_the_name_is_ambiguous() -> None:
    paris = run(GEOCODE_LOCATION, {"query": "Paris"})
    first = output(paris)["candidates"][0]
    assert (first["name"], first["region"], first["country_code"], first["time_zone"]) == (
        "Paris",
        "Île-de-France Region",
        "FR",
        "Europe/Paris",
    )
    assert output(paris)["is_ambiguous"] is False
    assert paris.summary == "Paris, Île-de-France Region, FR · 48.85, 2.35"
    assert run(GEOCODE_LOCATION, {"query": "Springfield"}).summary == "5 places, ambiguous"
    nowhere = run(GEOCODE_LOCATION, {"query": "Hogwarts"})
    assert (output(nowhere), nowhere.summary) == ({"candidates": [], "is_ambiguous": False}, "No place found")


def test_a_forecast_gives_each_day_in_words_with_its_weekday_and_the_time_there_now() -> None:
    forecast = run(GET_FORECAST, {**PARIS, "days": 2, "include_hourly": False, "units": "metric"})
    data = output(forecast)
    assert (data["latitude"], data["longitude"], data["time_zone"], data["local_now"]) == (
        48.85,
        2.35,
        "Europe/Paris",
        "2026-10-29T20:57",
    )
    assert data["days"][0] == {
        "date": "2026-10-29",
        "weekday": "Thursday",
        "condition": "Fog",
        "temperature_min": 5.6,
        "temperature_max": 15.6,
        "rain_chance_percent": 0,
        "sunrise": "2026-10-29T07:32",
        "sunset": "2026-10-29T17:35",
    }
    assert (data["temperature_unit"], data["hours"]) == ("°C", None)
    assert forecast.summary == "2 days · 6 to 16 °C · rain up to 0%"


def test_an_hourly_forecast_gives_each_hour_in_words() -> None:
    forecast = run(GET_FORECAST, {**PARIS, "days": 2, "include_hourly": True, "units": "metric"})
    assert output(forecast)["hours"][0] == {
        "time": "2026-10-29T00:00",
        "condition": "Mainly clear",
        "temperature": 9.6,
        "rain_chance_percent": 0,
    }
    assert forecast.summary.startswith("2 days, hourly · ")


def test_the_weather_now_gives_its_condition_in_words() -> None:
    now = run(GET_CURRENT_WEATHER, {"latitude": 35.6895, "longitude": 139.69171, "units": "metric"})
    data = output(now)
    assert (data["condition"], data["is_day"], data["temperature"], data["feels_like"]) == (
        "Partly cloudy",
        False,
        12.0,
        11.3,
    )
    assert (data["wind_speed"], data["wind_speed_unit"], data["observed_at"]) == (2.2, "km/h", "2026-10-30T04:00")
    assert now.summary == "12 °C, partly cloudy"


def test_the_air_gives_both_indexes() -> None:
    air = run(GET_AIR_QUALITY, {"latitude": 28.6139, "longitude": 77.209})
    assert (output(air)["us_aqi"], output(air)["european_aqi"]) == (131, 45)
    assert air.summary == "US AQI 131 · European AQI 45"


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (GEOCODE_LOCATION, {"query": ""}),
        (GEOCODE_LOCATION, {"query": "   "}),
        (GEOCODE_LOCATION, {"query": "a" * 101}),
        (GEOCODE_LOCATION, {"query": "Paris", "count": 0}),
        (GEOCODE_LOCATION, {"query": "Paris", "count": 11}),
        (GEOCODE_LOCATION, {"query": "Paris", "country_code": "USA"}),
        (GEOCODE_LOCATION, {"query": "Paris", "language": "fr"}),
        (GET_FORECAST, {**PARIS, "days": 17, "include_hourly": False, "units": "metric"}),
        (GET_FORECAST, {**PARIS, "days": 0, "include_hourly": False, "units": "metric"}),
        (GET_FORECAST, {**PARIS, "days": 2, "include_hourly": False, "units": "kelvin"}),
        (GET_CURRENT_WEATHER, {"latitude": 91, "longitude": 0, "units": "metric"}),
        (GET_AIR_QUALITY, {"latitude": 0, "longitude": -181}),
    ],
)
def test_an_input_outside_a_tool_s_rules_is_refused(tool: WeatherTool, args: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        tool.input_model.model_validate(args)


def test_the_model_sees_four_tools_with_their_inputs_named_as_the_rules_name_them() -> None:
    schemas = {tool.name: tool.input_model.model_json_schema() for tool in WEATHER_TOOLS}
    assert {name: list(schema["properties"]) for name, schema in schemas.items()} == {
        "geocode_location": ["query", "count", "country_code"],
        "get_current_weather": ["latitude", "longitude", "units"],
        "get_forecast": ["latitude", "longitude", "days", "include_hourly", "units"],
        "get_air_quality": ["latitude", "longitude"],
    }
    assert schemas["get_forecast"]["required"] == ["latitude", "longitude", "days", "include_hourly", "units"]
    assert all(property_["description"] for schema in schemas.values() for property_ in schema["properties"].values())
    # Gemini's declarations have no additionalProperties; a field a tool doesn't have is refused all the same (above).
    assert all("additionalProperties" not in schema for schema in schemas.values())
    assert schemas["get_air_quality"]["description"] == "get_air_quality's input."


def invoke(recordings: OpenMeteoRecordings, args: dict[str, Any]) -> ToolMessage:
    """The geocoding as a LangChain tool, called as the agent calls it, with a tool call."""

    async def go() -> ToolMessage:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(recordings)) as http:
            tool = to_langchain_tool(GEOCODE_LOCATION, ToolContext(OpenMeteoClient(http, sleep=no_sleep)))
            call = {"type": "tool_call", "id": "call-0-0", "name": "geocode_location", "args": args}
            message = await tool.ainvoke(call)
            assert isinstance(message, ToolMessage)
            return message

    return asyncio.run(go())


async def no_sleep(_seconds: float) -> None:
    """No wait between two tries."""


def test_as_a_langchain_tool_the_model_reads_the_weather_and_the_page_gets_the_request() -> None:
    with capture_logs() as lines:
        message = invoke(OpenMeteoRecordings(), {"query": "Paris"})
    assert (message.tool_call_id, message.status) == ("call-0-0", "success")
    assert json.loads(str(message.content))["candidates"][0]["name"] == "Paris"
    record = message.artifact
    assert isinstance(record, ToolCallRecord)
    assert (record.lane, record.request.host, record.summary) == (
        "rest-no-auth",
        "geocoding-api.open-meteo.com",
        "Paris, Île-de-France Region, FR · 48.85, 2.35",
    )
    [line] = [line for line in lines if line["event"] == "tool.call"]
    assert (line["tool"], line["lane"], line["status"], line["ms"]) == (
        "geocode_location",
        "rest-no-auth",
        "ok",
        record.ms,
    )


def test_as_a_langchain_tool_a_failure_reaches_the_model_and_the_chip_as_our_sentence() -> None:
    with capture_logs() as lines:
        message = invoke(OpenMeteoRecordings(failing=frozenset({"/v1/search"})), {"query": "Paris"})
    assert (message.status, message.content, message.artifact) == ("error", WEATHER_UNREACHABLE, None)
    [line] = [line for line in lines if line["event"] == "tool.call"]
    assert (line["status"], line["errorClass"]) == ("failed", "UpstreamUnavailableError")


def test_a_place_name_with_spaces_around_it_is_searched_without_them() -> None:
    recordings = OpenMeteoRecordings()
    invoke(recordings, {"query": "  Paris  "})
    assert recordings.requests[0].url.params["name"] == "Paris"
