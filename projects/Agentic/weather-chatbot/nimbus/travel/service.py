"""Per-answer travel request budgets and result sharing. Only aggregate metadata leaves through observability."""

import asyncio
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from threading import BoundedSemaphore
from typing import Final

import structlog
from pydantic import ValidationError

from nimbus.travel.models import TRAVEL_TIMEOUT_SECONDS, FlightSearch, HotelSearch, Provider, TravelReport, TravelStatus
from nimbus.utils import to_ms

# Distinct searches allowed per provider in a single answer, shared by the planner and individual tools.
SEARCHES_PER_TURN: Final = 2
type FlightLookup = Callable[[FlightSearch], Awaitable[TravelReport]]
type HotelLookup = Callable[[HotelSearch], Awaitable[TravelReport]]


class TravelService:
    """Inject provider adapters once per app instance; each answer gets a fresh, private TravelTurn."""

    def __init__(
        self,
        *,
        flights: FlightLookup | None = None,
        hotels: HotelLookup | None = None,
        concurrency: int = 2,
        timeout: float = TRAVEL_TIMEOUT_SECONDS,
    ) -> None:
        """Open no connections until a validated search is actually requested."""
        if concurrency < 1 or timeout <= 0:
            raise ValueError("positive concurrency and timeout required")
        self.flights = flights
        self.hotels = hotels
        self.timeout = timeout
        self.slots: dict[Provider, BoundedSemaphore] = {
            "kiwi": BoundedSemaphore(concurrency),
            "trivago": BoundedSemaphore(concurrency),
        }

    def new_turn(self, deadline: float, *, today: date | None = None, currency: str = "USD") -> "TravelTurn":
        """
        Bind all searches to this answer's absolute loop deadline, the visitor's local calendar date, and the currency
        a search takes when it names none.
        """
        return TravelTurn(self, deadline, today if today is not None else datetime.now(UTC).date(), currency)


class TravelTurn:
    """Hold only a single answer's requests and bounded offers, including concurrent duplicate searches."""

    def __init__(self, service: TravelService, deadline: float, today: date, currency: str = "USD") -> None:
        """Store the absolute deadline, the visitor's currency and the two independent provider budgets."""
        self._service = service
        self._deadline = deadline
        self.today = today
        self.currency = currency
        self._counts: Counter[Provider] = Counter()
        self._limited: set[Provider] = set()
        self._queries: dict[FlightSearch | HotelSearch, asyncio.Future[TravelReport]] = {}

    @property
    def flights_enabled(self) -> bool:
        """Whether this installation has enabled the flight adapter."""
        return self._service.flights is not None

    @property
    def hotels_enabled(self) -> bool:
        """Whether this installation has enabled the hotel adapter."""
        return self._service.hotels is not None

    async def search_flights(self, query: FlightSearch) -> TravelReport:
        """Fetch validated flight options for the requested dates and passengers."""
        query = self._in_currency(query)
        return await self._search("kiwi", query, query.departure_date, self._service.flights)

    async def search_hotels(self, query: HotelSearch) -> TravelReport:
        """Fetch validated accommodation options for the requested dates and guests."""
        query = self._in_currency(query)
        return await self._search("trivago", query, query.check_in, self._service.hotels)

    def _in_currency[Q: (FlightSearch, HotelSearch)](self, query: Q) -> Q:
        """A search that names no currency takes the visitor's: an en-GB visitor's prices come in pounds."""
        return query if "currency" in query.model_fields_set else query.model_copy(update={"currency": self.currency})

    def _refusal(self, provider: Provider, departure: date) -> TravelStatus | None:
        """Check the date, remaining answer time, upstream throttle and per-provider query budget."""
        if departure < self.today:
            return "invalid_input"
        if asyncio.get_running_loop().time() >= self._deadline:
            return "timeout"
        if provider in self._limited:
            return "rate_limited"
        if self._counts[provider] >= SEARCHES_PER_TURN:
            return "budget_exhausted"
        return None

    async def _search[Q: (FlightSearch, HotelSearch)](
        self,
        provider: Provider,
        query: Q,
        departure: date,
        lookup: Callable[[Q], Awaitable[TravelReport]] | None,
    ) -> TravelReport:
        """Share an existing result or claim a fresh slot without waiting behind unrelated traffic."""
        # ① A duplicate awaits its owner, whose work stays cancellable when the answer closes.
        started = time.perf_counter()
        shared = self._queries.get(query)
        if shared is not None:
            report = await asyncio.shield(shared)
        elif lookup is None:
            report = TravelReport(provider=provider, status="disabled")
        elif reason := self._refusal(provider, departure):
            report = TravelReport(provider=provider, status=reason)
        elif not self._service.slots[provider].acquire(blocking=False):
            report = TravelReport(provider=provider, status="busy")
        else:
            # ② No await occurs between the checks and claiming ownership. All callers share this event loop.
            self._counts[provider] += 1
            result: asyncio.Future[TravelReport] = asyncio.get_running_loop().create_future()
            self._queries[query] = result
            try:
                report = await self._fetch(provider, query, lookup)
                if report.status == "rate_limited":
                    self._limited.add(provider)
                result.set_result(report)
            finally:
                if not result.done():
                    result.cancel()
                    del self._queries[query]
                self._service.slots[provider].release()
        # ③ Arguments, responses, raw errors, source links and dates never enter any telemetry.
        structlog.get_logger().info(
            "travel.call",
            tool="search_flights" if provider == "kiwi" else "search_hotels",
            provider=provider,
            status=report.status,
            count=len(report.offers),
            ms=to_ms(time.perf_counter() - started),
            deduplicated=shared is not None,
        )
        return report

    async def _fetch[Q: (FlightSearch, HotelSearch)](
        self,
        provider: Provider,
        query: Q,
        lookup: Callable[[Q], Awaitable[TravelReport]],
    ) -> TravelReport:
        """Run and close the adapter under one deadline, propagating cancellation and isolating failures."""
        try:
            limit = min(self._deadline, asyncio.get_running_loop().time() + self._service.timeout)
            async with asyncio.timeout_at(limit):
                report = await lookup(query)
            if report.provider != provider:
                return TravelReport(provider=provider, status="invalid_response")
            return report.bounded()
        except TimeoutError:
            return TravelReport(provider=provider, status="timeout")
        except ValidationError:
            return TravelReport(provider=provider, status="invalid_response")
        except Exception:
            return TravelReport(provider=provider, status="unavailable")
