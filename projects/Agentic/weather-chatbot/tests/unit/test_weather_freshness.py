"""Absolute provider freshness is preserved through cache hits and the REST tool artifacts."""

import asyncio
from typing import Any

import httpx2
import pytest
from langchain_core.messages import ToolMessage

from nimbus.cache import to_cache_key
from nimbus.open_meteo import OpenMeteoClient
from nimbus.tools import ToolCallRecord, ToolContext, make_tools
from tests.fakes import FakeCacheStore
from tests.unit.test_open_meteo import NOON_IN_PARIS, OpenMeteoStub, call_with_cache, fixture, ok


def test_a_cache_hit_keeps_its_original_deadline_even_one_second_before_expiry() -> None:
    """A 599-second-old current observation cannot acquire another 600 seconds on a read."""
    store, stub = FakeCacheStore(), OpenMeteoStub(ok("current-tokyo"), ok("current-tokyo"))
    first = call_with_cache(stub, store, lambda client: client.get_current_weather(35.69, 139.69, units="metric"))
    again = call_with_cache(
        stub,
        store,
        lambda client: client.get_current_weather(35.69, 139.69, units="metric"),
        now=NOON_IN_PARIS + 599,
    )
    assert len(stub.requests) == 1
    assert again.from_cache
    assert (again.fetched_at, again.expires_at) == (first.fetched_at, first.expires_at)
    assert again.expires_at == NOON_IN_PARIS + 600
    expired = call_with_cache(
        stub,
        store,
        lambda client: client.get_current_weather(35.69, 139.69, units="metric"),
        now=NOON_IN_PARIS + 600,
    )
    assert len(stub.requests) == 2
    assert not expired.from_cache
    assert expired.fetched_at == NOON_IN_PARIS + 600


@pytest.mark.parametrize(
    "corruption",
    [
        {"fetched_at": float("nan")},
        {"expires_at": float("inf")},
        {"fetched_at": True},
        {"expires_at": "1793445000"},
        {"fetched_at": NOON_IN_PARIS + 1},
        {"expires_at": NOON_IN_PARIS},
        {"expires_at": NOON_IN_PARIS + 601},
        {"fetched_at": NOON_IN_PARIS + 600},
        {"version": 2},
        {"body": {}},
    ],
)
def test_corrupted_or_expired_envelopes_refetch(corruption: dict[str, Any]) -> None:
    """An invalid payload or deadline is never accepted as fresh provider evidence."""
    store, stub = FakeCacheStore(), OpenMeteoStub(ok("current-tokyo"), ok("current-tokyo"))
    first = call_with_cache(stub, store, lambda client: client.get_current_weather(35.69, 139.69, units="metric"))
    key = to_cache_key(first.request.url)
    entry = store.items[key]
    assert isinstance(entry, dict)
    store.items[key] = {**entry, **corruption}
    again = call_with_cache(stub, store, lambda client: client.get_current_weather(35.69, 139.69, units="metric"))
    assert len(stub.requests) == 2
    assert not again.from_cache
    assert (again.fetched_at, again.expires_at) == (NOON_IN_PARIS, NOON_IN_PARIS + 600)


def test_legacy_raw_provider_json_refetches_before_acquiring_freshness() -> None:
    """Old cache entries without their original clock cannot be promoted into reusable LLM evidence."""
    store, stub = FakeCacheStore(), OpenMeteoStub(ok("current-tokyo"), ok("current-tokyo"))
    first = call_with_cache(stub, store, lambda client: client.get_current_weather(35.69, 139.69, units="metric"))
    store.items[to_cache_key(first.request.url)] = fixture("current-tokyo")
    again = call_with_cache(stub, store, lambda client: client.get_current_weather(35.69, 139.69, units="metric"))
    assert len(stub.requests) == 2
    assert not again.from_cache
    assert again.fetched_at == NOON_IN_PARIS


def test_forecast_freshness_ends_at_midnight_including_fractional_seconds() -> None:
    """A forecast requested a fraction of a second before midnight cannot survive into tomorrow."""
    now = NOON_IN_PARIS + 12 * 60 * 60 - 0.25
    answer = call_with_cache(
        OpenMeteoStub(ok("forecast-paris")),
        FakeCacheStore(),
        lambda client: client.get_forecast(48.85, 2.35, days=2, include_hourly=False, units="metric"),
        now=now,
    )
    assert answer.fetched_at == now
    assert answer.expires_at == NOON_IN_PARIS + 12 * 60 * 60


def test_rest_tool_artifacts_retain_freshness_without_exposing_it_to_the_model() -> None:
    """Freshness reaches successful tool evidence even when the provider data cache is disabled."""

    async def run() -> ToolMessage:
        stub = OpenMeteoStub(ok("current-tokyo"))
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(stub)) as http:
            client = OpenMeteoClient(http, clock=lambda: NOON_IN_PARIS)
            tool = next(tool for tool in make_tools(ToolContext(client)) if tool.name == "get_current_weather")
            result = await tool.ainvoke(
                {
                    "type": "tool_call",
                    "id": "freshness-check",
                    "name": "get_current_weather",
                    "args": {"latitude": 35.69, "longitude": 139.69, "units": "metric"},
                }
            )
            assert isinstance(result, ToolMessage)
            return result

    message = asyncio.run(run())
    assert isinstance(message.artifact, ToolCallRecord)
    assert (message.artifact.fetched_at, message.artifact.expires_at) == (NOON_IN_PARIS, NOON_IN_PARIS + 600)
    assert "fetched_at" not in str(message.content)
    assert "expires_at" not in str(message.content)
