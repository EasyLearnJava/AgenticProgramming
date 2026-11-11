"""Quote first, approve the combined price, then book: only the surprise-trip sandbox uses this policy."""

import asyncio
import time
from decimal import Decimal
from typing import Any

import structlog
from fastapi import HTTPException

from nimbus.booking_demo.provider import DemoProviderError
from nimbus.config import Settings
from nimbus.retrieval_gate import RetrievalGate
from nimbus.surprise_trip import provider
from nimbus.surprise_trip.state import Product, Receipts, SurpriseState

QUOTE_SECONDS = 300
QUOTE_PHASES = ("flight_search", "flight_verify", "flight_prebook", "hotel_search", "hotel_prebook")
BOOK_PHASES = ("flight_book", "hotel_book")
LABELS = {
    "flight_search": "Search DFW to Las Vegas for all travelers",
    "flight_verify": "Verify flight itinerary and fare",
    "flight_prebook": "Validate full-party flight quote",
    "hotel_search": "Search hotels near Grand Canyon South Rim",
    "hotel_prebook": "Validate all rooms, nights and mandatory fees",
    "flight_refresh": "Recheck the approved flight quote",
    "hotel_refresh": "Recheck hotel price and combined total",
    "flight_book": "Submit approved sandbox flight booking",
    "hotel_book": "Submit approved sandbox hotel booking",
}


def _quote_failure(product: Product, reason: str) -> None:
    """Display a fixed diagnostic, never the sandbox's raw error body or an unverified price."""
    product.status = "unavailable"
    product.price = ""
    product.price_cents = None
    product.prepared = {}
    product.prebook_id = ""
    product.message = {
        "no_match": "No matching sandbox quote was found for these dates and travelers.",
        "timeout": "The sandbox request timed out. This does not mean there are no available options.",
        "rate_limited": "The sandbox is limiting requests. Wait a minute before requesting a new quote.",
        "invalid_response": "The sandbox returned inconsistent quote data that could not be validated.",
        "not_found": "This sandbox quote is no longer available. Request a new quote.",
    }.get(reason, "The sandbox could not complete this request. Availability could not be checked.")
    product.message += " Nothing was booked."


def _offer(product: Product, value: dict[str, Any]) -> None:
    """Copy normalized provider fields; unpriced search data never becomes an approvable total."""
    product.offer = value
    product.status = "ready"
    product.title = str(value.get("title", product.title))[:240]
    product.price = str(value.get("price", ""))[:40]
    product.currency = str(value.get("currency", "USD"))
    product.details = [str(item)[:400] for item in value.get("details", [])[:12]]


def _prepared(product: Product, value: dict[str, Any]) -> None:
    """Only validated whole-party USD cents can participate in the $800 comparison."""
    cents = value.get("price_cents")
    if type(cents) is not int or not 0 < cents < 100_000_000 or value.get("currency") != "USD":
        raise DemoProviderError("invalid_response")
    identifier = value.get("prebook_id")
    if not isinstance(identifier, str) or not identifier:
        raise DemoProviderError("invalid_response")
    if product.prebook_id and product.prebook_id != identifier:
        # A refresh is never permission to create a new reservation attempt.
        raise DemoProviderError("invalid_response")
    product.prepared = value
    product.prebook_id = identifier
    product.price_cents = cents
    product.price = f"{Decimal(cents) / 100:.2f}"
    product.currency = "USD"
    product.status = "ready"
    product.details = [str(item)[:400] for item in value.get("details", product.details)[:12]]


def _booked(product: Product, value: dict[str, Any]) -> None:
    """Keep the complete approved budget, including hotel fees; payment acceptance is not ticket confirmation."""
    status = value.get("status")
    product.status = status if status in {"confirmed", "pending", "failed", "unknown"} else "unknown"
    product.booking_id = str(value.get("booking_id", product.booking_id))[:160]
    product.reference = str(value.get("reference", product.reference))[:160]
    product.message = {
        "confirmed": "Confirmed in the sandbox. No usable ticket or real hotel reservation was issued.",
        "pending": "Accepted by the sandbox; final confirmation is still pending.",
        "failed": "The provider did not confirm this simulated booking.",
        "unknown": "The result is uncertain. Refresh this attempt; do not create a replacement booking.",
    }[product.status]


class SurpriseWorkflow:
    """Independent state, receipts, rate gate and explicit approval. No ordinary chat/planner rules are changed."""

    def __init__(self, settings: Settings) -> None:
        self.receipts = Receipts(settings)
        self.gate = RetrievalGate()
        self.latest: dict[str, SurpriseState] = {}
        self.busy: set[str] = set()

    def prune(self) -> None:
        now = time.time()
        for key in list(self.latest):
            if self.latest[key].expires <= now:
                del self.latest[key]
        while len(self.latest) > 128:
            del self.latest[next(iter(self.latest))]

    def remember(self, state: SurpriseState) -> dict[str, Any]:
        if state.phase in {"failed", "cancelled", "expired", "done"}:
            for product in (state.flight, state.hotel):
                if product.status == "idle":
                    product.status = "skipped"
                    product.message = "This search was not started before the workflow stopped. Nothing was booked."
        self.latest[state.id] = state.model_copy(deep=True)
        self.prune()
        return {"token": self.receipts.encode(state), "view": state.view(volatile=self.receipts.volatile)}

    def _await_confirmation(self, state: SurpriseState, *, changed: bool = False) -> None:
        """A quote, even below $800, never grants authority to book either product."""
        if state.total_cents is None or any(
            product.status != "ready" or not product.prebook_id for product in (state.flight, state.hotel)
        ):
            raise DemoProviderError("invalid_response")
        state.approved_cents = None
        state.quote_expires = int(time.time()) + QUOTE_SECONDS
        state.phase = "awaiting_confirmation"
        amount = Decimal(state.total_cents) / 100
        prefix = "The quoted total changed. " if changed else ""
        warning = "This exceeds your $800 budget. " if state.total_cents > 80_000 else ""
        state.message = f"{prefix}{warning}Flight + hotel total: ${amount:.2f}. Say Yes to book both in the sandbox."

    def _finish_quote(self, state: SurpriseState) -> None:
        """An independently successful quote stays visible but never authorizes a partial booking."""
        if all(product.status == "ready" and product.prebook_id for product in (state.flight, state.hotel)):
            self._await_confirmation(state)
            return
        state.phase = "failed"
        state.approved_cents = None
        state.message = (
            "Both searches have finished, but a complete flight and hotel quote is not available. "
            "Any available result is shown below. Neither booking was submitted. "
            "Request a new quote before confirming both bookings."
        )

    def _continue_hotel_quote(self, state: SurpriseState) -> None:
        """A flight failure cannot cancel hotel quoting, including receipts from the previous sequential flow."""
        if state.hotel.status == "idle":
            state.phase = "hotel_search"
        elif state.hotel.status == "ready" and not state.hotel.prebook_id:
            state.phase = "hotel_prebook"
        else:
            self._finish_quote(state)

    async def _search_product(self, state: SurpriseState, *, flight: bool) -> None:
        """One bounded search with its own result; an exception does not cancel the other product's search."""
        product = state.flight if flight else state.hotel
        phase = "flight_search" if flight else "hotel_search"
        product.phase = phase
        search = provider.search_flight if flight else provider.search_hotel
        started = time.monotonic()
        reason = ""
        try:
            _offer(product, await search(state.checkin, state.checkout, state.adults))
        except Exception as error:
            reason = error.reason if isinstance(error, DemoProviderError) else "invalid_response"
            _quote_failure(product, reason)
            structlog.get_logger().warning(
                "surprise_trip.step",
                step=phase,
                outcome=product.status,
                reason=reason,
                errorClass=type(error).__name__,
                ms=round((time.monotonic() - started) * 1000),
            )
        else:
            structlog.get_logger().info(
                "surprise_trip.step",
                step=phase,
                outcome=product.status,
                ms=round((time.monotonic() - started) * 1000),
            )
        state.events.append(
            {"label": LABELS[phase], "status": product.status, "reason": reason, "message": product.message}
        )

    async def act(self, state: SurpriseState, action: str) -> SurpriseState:
        """The server enforces all transitions; a forged action or an advance cannot substitute for consent."""
        if action == "confirm":
            if state.phase != "awaiting_confirmation" or state.total_cents is None:
                raise HTTPException(409, "Review a complete flight and hotel quote before confirming.")
            if state.quote_expires <= time.time():
                state.phase = "expired"
                state.approved_cents = None
                state.message = "This quote expired. Search again and review the new total before booking."
            else:
                state.approved_cents = state.total_cents
                state.phase = "flight_refresh"
                state.message = (
                    "You approved both sandbox bookings. Rechecking the same quoted rates before submission."
                )
            state.version += 1
            return state
        if action == "cancel":
            if state.phase in BOOK_PHASES or state.flight.submitted or state.hotel.submitted:
                raise HTTPException(
                    409, "A booking may have been submitted. Refresh its status; this does not cancel it."
                )
            state.phase = "cancelled"
            state.approved_cents = None
            state.message = "Cancelled before booking. Neither flight nor hotel was booked."
            state.version += 1
            return state
        if action == "recover":
            return await self._recover(state)
        if action != "advance":
            raise HTTPException(400, "Unknown surprise-trip action")
        if state.phase in {"awaiting_confirmation", "done", "failed", "cancelled", "expired"}:
            return state
        if state.phase == "search":
            await asyncio.gather(self._search_product(state, flight=True), self._search_product(state, flight=False))
            if state.flight.status == "ready":
                state.phase = "flight_verify"
            else:
                self._continue_hotel_quote(state)
            state.version += 1
            return state
        if state.phase not in {*QUOTE_PHASES, "flight_refresh", "hotel_refresh", *BOOK_PHASES}:
            raise HTTPException(409, "This surprise-trip step is unavailable.")
        if state.phase in {"flight_refresh", "hotel_refresh", *BOOK_PHASES}:
            if state.approved_cents is None:
                raise HTTPException(409, "Say Yes to the displayed total before either booking is submitted.")
            if state.quote_expires <= time.time():
                state.phase = "failed" if state.flight.submitted or state.hotel.submitted else "expired"
                state.message = (
                    "The approved quote expired. No further booking was submitted. Refresh any existing attempt."
                )
                state.version += 1
                return state
        if state.phase in BOOK_PHASES and state.total_cents != state.approved_cents:
            raise HTTPException(409, "The total no longer matches your approval. No booking was submitted.")

        phase = state.phase
        product = state.flight if phase.startswith("flight_") else state.hotel
        product.phase = phase
        started = time.monotonic()
        try:
            await self._perform(state, phase)
        except Exception as error:
            if not isinstance(error, DemoProviderError) and phase not in QUOTE_PHASES:
                raise
            reason = error.reason if isinstance(error, DemoProviderError) else "invalid_response"
            if phase in QUOTE_PHASES:
                _quote_failure(product, reason)
                if phase.startswith("flight_"):
                    self._continue_hotel_quote(state)
                else:
                    self._finish_quote(state)
            else:
                product.status = "unknown" if phase in BOOK_PHASES else "unavailable"
                product.message = (
                    "The booking outcome is unknown. Use Refresh status, not a new booking."
                    if phase in BOOK_PHASES
                    else "The approved quote could not be rechecked. Neither booking was submitted."
                )
                state.phase = "failed"
                state.message = (
                    "The workflow stopped. Check each booking card; the pair is not an all-or-nothing transaction."
                    if state.flight.submitted or state.hotel.submitted
                    else "The complete trip could not be quoted, so neither flight nor hotel was booked."
                )
            structlog.get_logger().warning(
                "surprise_trip.step",
                step=phase,
                outcome=product.status,
                reason=reason,
                errorClass=type(error).__name__,
                ms=round((time.monotonic() - started) * 1000),
            )
        else:
            structlog.get_logger().info(
                "surprise_trip.step",
                step=phase,
                outcome=product.status,
                ms=round((time.monotonic() - started) * 1000),
            )
        state.events.append({"label": LABELS[phase], "status": product.status, "message": product.message})
        state.version += 1
        return state

    async def _perform(self, state: SurpriseState, phase: str) -> None:
        """Only this fixed itinerary, synthetic party and confirmed prebooks reach Nuitée."""
        dates = (state.checkin, state.checkout, state.adults)
        if phase == "flight_search":
            _offer(state.flight, await provider.search_flight(*dates))
            state.phase = "flight_verify"
        elif phase == "flight_verify":
            _offer(state.flight, await provider.verify_flight(state.flight.offer, *dates))
            state.phase = "flight_prebook"
        elif phase == "flight_prebook":
            _prepared(state.flight, await provider.prebook_flight(state.flight.offer, state.adults))
            self._continue_hotel_quote(state)
        elif phase == "hotel_search":
            _offer(state.hotel, await provider.search_hotel(*dates))
            state.phase = "hotel_prebook"
        elif phase == "hotel_prebook":
            _prepared(state.hotel, await provider.prebook_hotel(state.hotel.offer, state.adults))
            self._finish_quote(state)
        elif phase == "flight_refresh":
            _prepared(state.flight, await provider.refresh_flight(state.flight.prepared, *dates))
            state.phase = "hotel_refresh"
        elif phase == "hotel_refresh":
            _prepared(state.hotel, await provider.refresh_hotel(state.hotel.prepared, *dates))
            if state.total_cents != state.approved_cents:
                self._await_confirmation(state, changed=True)
            else:
                state.phase = "flight_book"
        elif phase == "flight_book":
            state.flight.submitted = True
            _booked(state.flight, await provider.book_flight(state.flight.prebook_id))
            if state.flight.status in {"confirmed", "pending"}:
                state.phase = "hotel_book"
            else:
                state.phase = "failed"
                state.message = "The flight is not confirmed or accepted. The hotel has not been submitted."
        elif phase == "hotel_book":
            state.hotel.submitted = True
            _booked(state.hotel, await provider.book_hotel(state.hotel.prebook_id, state.hotel_reference, state.adults))
            state.phase = "done"
            state.message = "Sandbox booking attempts finished. Each card shows its own confirmation status."

    async def _recover(self, state: SurpriseState) -> SurpriseState:
        """Refresh only original attempts. Even an interrupted confirmation cannot implicitly book anything."""
        if state.approved_cents is None:
            state.message = "No booking was authorized. Resume the quote or review it and say Yes."
            state.version += 1
            return state
        for kind, product in (("flight", state.flight), ("hotel", state.hotel)):
            if not product.submitted and state.phase != f"{kind}_book":
                continue
            if not product.prebook_id:
                continue
            product.submitted = True
            try:
                if kind == "hotel":
                    result = await provider.recover_hotel(state.hotel_reference)
                elif product.booking_id:
                    result = await provider.retrieve_flight(product.booking_id)
                else:
                    result = await provider.recover_flight(product.prebook_id)
                _booked(product, result)
            except DemoProviderError:
                if product.status not in {"confirmed", "pending", "failed"}:
                    product.status = "unknown"
                product.message = "No updated confirmation was returned. This refresh did not submit a booking."
        if state.hotel.submitted:
            state.phase = "done"
        elif state.flight.submitted:
            state.phase = "hotel_book" if state.flight.status in {"confirmed", "pending"} else "failed"
        state.message = (
            "Existing attempt status checked. Pending or unknown is not confirmed; no new booking was submitted."
        )
        state.events.append({"label": "Refresh existing booking status", "status": "checked"})
        state.version += 1
        return state
