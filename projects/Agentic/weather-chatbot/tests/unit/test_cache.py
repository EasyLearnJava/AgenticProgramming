"""
tests/unit/test_cache.py: the cache of Open-Meteo's answers (step 7): its keys, our namespace and a hash that names no
place; a read or a write that fails, or is slow, a miss with one warning; Vercel's Runtime Cache, taking our keys as
they are; and the vercel package's telemetry, off.
"""

import asyncio
import hashlib
import os
import time

import pytest
from structlog.testing import capture_logs
from vercel.cache import AsyncRuntimeCache
from vercel.internal.telemetry.tracker import get_client

from nimbus.cache import WeatherCache, make_weather_cache, to_cache_key
from tests.fakes import FakeCacheStore

ADDRESS = "https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=5&language=en&format=json"


def run_on(cache: WeatherCache, operation: str) -> object:
    """A read of the address, or a write of an empty answer for 10 minutes."""
    if operation == "get":
        return asyncio.run(cache.get(ADDRESS))
    return asyncio.run(cache.set(ADDRESS, {"results": []}, 600))


def test_a_key_is_our_namespace_then_the_address_s_sha_256_which_names_no_place() -> None:
    key = to_cache_key(ADDRESS)
    assert key == "nimbus-weather:" + hashlib.sha256(ADDRESS.encode()).hexdigest()
    assert "Paris" not in key
    assert to_cache_key(ADDRESS + "&countryCode=FR") != key


def test_an_answer_kept_is_read_back_under_its_key_with_its_time() -> None:
    store = FakeCacheStore()
    cache = WeatherCache(store)
    run_on(cache, "set")
    assert run_on(cache, "get") == {"results": []}
    assert store.ttls == {to_cache_key(ADDRESS): 600}


def test_nothing_kept_is_a_miss() -> None:
    assert run_on(WeatherCache(FakeCacheStore()), "get") is None


@pytest.mark.parametrize("operation", ["get", "set"])
def test_a_cache_that_fails_is_a_miss_with_one_warning(operation: str) -> None:
    store = FakeCacheStore()
    store.error = ConnectionError("the cache is down")
    with capture_logs() as lines:
        assert run_on(WeatherCache(store), operation) is None
    assert lines == [
        {"event": "cache.failed", "log_level": "warning", "operation": operation, "errorClass": "ConnectionError"}
    ]


@pytest.mark.parametrize("operation", ["get", "set"])
def test_a_cache_slower_than_its_time_is_given_up_as_a_miss(operation: str) -> None:
    store = FakeCacheStore()
    store.delay = 2
    started = time.perf_counter()
    with capture_logs() as lines:
        assert run_on(WeatherCache(store, timeout_seconds=0.05), operation) is None
    assert time.perf_counter() - started < 1
    assert [line["errorClass"] for line in lines] == ["TimeoutError"]


def test_vercel_s_runtime_cache_takes_our_keys_as_they_are() -> None:
    # Off Vercel, the package keeps values in this process's memory, which another of its caches reads by the same key.
    async def keep_then_read() -> object:
        await make_weather_cache().set(ADDRESS, {"results": []}, 600)
        return await AsyncRuntimeCache(key_hash_function=str).get(to_cache_key(ADDRESS))

    assert asyncio.run(keep_then_read()) == {"results": []}


def test_the_vercel_package_s_telemetry_is_off() -> None:
    # It's turned off before the package is imported (issue 58): else it sends usage events when the process ends.
    assert os.environ["VERCEL_TELEMETRY_DISABLED"] == "1"
    client = get_client()
    assert client is None or not client._enabled
