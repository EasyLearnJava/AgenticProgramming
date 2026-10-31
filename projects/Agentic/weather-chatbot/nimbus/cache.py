"""
nimbus/cache.py: where Open-Meteo's answers are kept (step 7): Vercel's Runtime Cache, through the vercel package. On
Hobby, all of a team's projects share one cache, so each key is our namespace, then the SHA-256 of the request's
address: never the address itself, which can name a place, nor the package's own hash, of 32 bits, which two addresses
can share. A read or a write that fails, or takes more than 1 s, is a miss: the answer is fetched as if nothing were
kept. On Vercel, the store is built here, as the package builds it, but with an on_error that raises, so the cache's
own errors reach our warning, with the request's id, rather than a plain line of the package's (issue 60). Off
Vercel, the package keeps the answers in this process's memory, and says so once.
"""

import asyncio
import hashlib
import json
from typing import Protocol

import structlog
from vercel.cache import AsyncRuntimeCache
from vercel.cache.cache_build import AsyncBuildCache

from nimbus.config import Settings
from nimbus.constants import CACHE_NAMESPACE, CACHE_TIMEOUT_SECONDS

log = structlog.get_logger()


class CacheStore(Protocol):
    """What the cache needs of a store: Vercel's Runtime Cache, or the tests' own."""

    async def get(self, key: str) -> object:
        """The value kept under the key, or None."""

    async def set(self, key: str, value: object, options: dict[str, object] | None = None) -> object:
        """Keeps the value, as JSON, under the key, for options' "ttl" seconds."""


def to_cache_key(address: str) -> str:
    """A request's address as a key: our namespace, then the address's SHA-256, which names no place."""
    return f"{CACHE_NAMESPACE}:{hashlib.sha256(address.encode()).hexdigest()}"


def _as_given(key: str) -> str:
    """A key as to_cache_key() made it: the package hashes each key itself, unless it's given this."""
    return key


class WeatherCache:
    """Open-Meteo's answers, kept by their request's address; a read or a write that fails, or is slow, is a miss."""

    def __init__(self, store: CacheStore, *, timeout_seconds: float = CACHE_TIMEOUT_SECONDS) -> None:
        """The store, and how long a read or a write may take (the tests pass their own)."""
        self.store = store
        self._timeout_seconds = timeout_seconds

    async def get(self, address: str) -> object | None:
        """The answer kept for the address; None if there's none, or if the cache was slow or failed: a warning."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self.store.get(to_cache_key(address))
        except Exception as error:
            log.warning("cache.failed", operation="get", errorClass=type(error).__name__)
            return None

    async def set(self, address: str, answer: object, seconds: int) -> None:
        """Keeps the answer for the address for so many seconds; a cache that's slow or fails is a warning, no more."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self.store.set(to_cache_key(address), answer, {"ttl": seconds})
        except Exception as error:
            log.warning("cache.failed", operation="set", errorClass=type(error).__name__)


def _raise(error: Exception) -> None:
    """The store's on_error: the cache's own error goes on, to our cache.failed warning, never to a print (issue 60)."""
    raise error


def make_weather_cache(settings: Settings) -> WeatherCache:
    """
    The cache on Vercel's Runtime Cache, which takes our keys as they are. Where Vercel gives the function its cache's
    address and headers, the store is built from them, as the package would, with an on_error that raises; elsewhere,
    or with headers that aren't a JSON object, the package's own.
    """
    endpoint, headers = settings.runtime_cache_endpoint, settings.runtime_cache_headers
    if endpoint is not None and headers is not None:
        try:
            parsed = json.loads(headers.get_secret_value())
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return WeatherCache(AsyncBuildCache(endpoint=endpoint, headers=parsed, on_error=_raise))
    return WeatherCache(AsyncRuntimeCache(key_hash_function=_as_given))
