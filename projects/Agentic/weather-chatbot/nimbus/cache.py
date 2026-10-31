"""
nimbus/cache.py: where Open-Meteo's answers are kept (step 7): Vercel's Runtime Cache, through the vercel package. On
Hobby, all of a team's projects share one cache, so each key is our namespace, then the SHA-256 of the request's
address: never the address itself, which can name a place, nor the package's own hash, of 32 bits, which two addresses
can share. A read or a write that fails, or takes more than 1 s, is a miss: the answer is fetched as if nothing were
kept. On Vercel, the package's store catches the cache's own errors: it prints each in a plain line, and gives a miss
(issue 60). Off Vercel, the package keeps the answers in this process's memory, and says so once.
"""

import asyncio
import hashlib
import os
from typing import Protocol

import structlog

# The vercel package sends usage events, with the team's and the project's ids, to telemetry.vercel.com when the
# process ends, unless this is set before it's imported (issue 58): Nimbus sends nothing it doesn't need to.
os.environ.setdefault("VERCEL_TELEMETRY_DISABLED", "1")

from vercel.cache import AsyncRuntimeCache

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
        self._store = store
        self._timeout_seconds = timeout_seconds

    async def get(self, address: str) -> object | None:
        """The answer kept for the address; None if there's none, or if the cache was slow or failed: a warning."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._store.get(to_cache_key(address))
        except Exception as error:
            log.warning("cache.failed", operation="get", errorClass=type(error).__name__)
            return None

    async def set(self, address: str, answer: object, seconds: int) -> None:
        """Keeps the answer for the address for so many seconds; a cache that's slow or fails is a warning, no more."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._store.set(to_cache_key(address), answer, {"ttl": seconds})
        except Exception as error:
            log.warning("cache.failed", operation="set", errorClass=type(error).__name__)


def make_weather_cache() -> WeatherCache:
    """The cache on Vercel's Runtime Cache, which takes our keys as they are."""
    return WeatherCache(AsyncRuntimeCache(key_hash_function=_as_given))
