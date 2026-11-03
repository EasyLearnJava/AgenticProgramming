"""Bound public playground work per app instance; the deployed edge rule additionally covers /api/ across instances."""

import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import HTTPException


class RetrievalGate:
    """A bounded, expiring request counter and concurrency cap that retain no questions or results."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """Start with no recent callers or active requests."""
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}
        self._active = 0
        self._lock = threading.Lock()

    @asynccontextmanager
    async def reserve(self, caller: str) -> AsyncIterator[None]:
        """Permit twelve requests per minute and two in flight, with at most 1,024 short-lived caller entries."""
        with self._lock:
            now = self._clock()
            for key in list(self._requests):
                recent = self._requests[key]
                while recent and recent[0] <= now - 60:
                    recent.popleft()
                if not recent:
                    del self._requests[key]
            if self._active >= 2 or (caller not in self._requests and len(self._requests) >= 1024):
                raise HTTPException(429, "Retrieval is busy. Please try again shortly.", headers={"retry-after": "5"})
            recent = self._requests.setdefault(caller, deque())
            if len(recent) >= 12:
                raise HTTPException(
                    429, "Too many retrieval requests. Please wait a minute.", headers={"retry-after": "60"}
                )
            recent.append(now)
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
