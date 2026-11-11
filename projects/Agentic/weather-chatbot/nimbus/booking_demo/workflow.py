"""One sandbox operation per request, independent of Gemini, Kiwi, trivago and park planning."""

import time
from typing import Any

import structlog

from nimbus.booking_demo import provider
from nimbus.booking_demo.state import DemoState, Product, Receipts
from nimbus.config import Settings
from nimbus.retrieval_gate import RetrievalGate

PHASES = (
    "flight_search",
    "flight_verify",
    "flight_prebook",
    "flight_book",
    "hotel_search",
    "hotel_prebook",
    "hotel_book",
    "done",
)
LABELS = {
    "flight_search": "Search DFW to SGU flights",
    "flight_verify": "Verify Friday / Sunday-evening itinerary",
    "flight_prebook": "Prepare synthetic flight passenger",
    "flight_book": "Submit simulated flight booking",
    "hotel_search": "Search Springdale hotels near Zion",
    "hotel_prebook": "Verify sandbox hotel rate",
    "hotel_book": "Submit simulated hotel booking",
    "recover": "Refresh booking status",
}


def offer_fields(product: Product, offer: dict[str, Any]) -> None:
    """Copy provider-normalized display fields; the offer itself stays only in the authenticated receipt."""
    product.offer = offer
    product.status = "ready"
    for name in ("title", "price", "currency"):
        if offer.get(name) is not None:
            setattr(product, name, str(offer[name])[:240])
    if isinstance(offer.get("details"), list):
        product.details = [str(item)[:320] for item in offer["details"][:8]]


def booking_fields(product: Product, result: dict[str, Any]) -> None:
    """Provider acceptance or payment success never implies a confirmed reservation."""
    status = result.get("status")
    product.status = status if status in {"confirmed", "pending", "failed", "unknown"} else "unknown"
    for name in ("booking_id", "reference", "price", "currency"):
        if result.get(name) is not None:
            setattr(product, name, str(result[name])[:160])
    product.message = {
        "confirmed": "Confirmed in the shared sandbox. This is not a usable travel reservation.",
        "pending": "The provider accepted the demo booking and is still confirming it. No ticket is confirmed.",
        "failed": "The provider did not confirm this simulated reservation.",
        "unknown": "The booking outcome is unknown. Refresh status; do not create another booking to retry it.",
    }[product.status]


class DemoWorkflow:
    """Signed browser receipts survive requests; bounded local memoization prevents repeated clicks on a worker."""

    def __init__(self, settings: Settings) -> None:
        """Keep this demo's gate, receipts and short-lived state separate from every production workflow."""
        self.receipts = Receipts(settings)
        self.gate = RetrievalGate()
        self.latest: dict[str, DemoState] = {}
        self.busy: set[str] = set()

    def prune(self) -> None:
        """Keep only a small set of active demo receipts on this worker; never use it as durable booking storage."""
        now = time.time()
        for key in list(self.latest):
            if self.latest[key].expires <= now:
                del self.latest[key]
        while len(self.latest) > 128:
            del self.latest[next(iter(self.latest))]

    def remember(self, state: DemoState) -> dict[str, Any]:
        """Return an authenticated continuation and a public view, with no raw API response."""
        self.latest[state.id] = state.model_copy(deep=True)
        self.prune()
        return {"token": self.receipts.encode(state), "view": state.view(volatile=self.receipts.volatile)}

    async def advance(self, state: DemoState) -> DemoState:
        """Advance a single fixed operation. Failures of either product do not discard the other product."""
        phase = state.next_phase
        if phase == "done":
            return state
        if phase not in PHASES:
            raise ValueError("Unknown demo operation")
        product = state.flight if phase.startswith("flight_") else state.hotel
        product.phase = phase
        started = time.monotonic()
        try:
            await self._perform(state, phase, product)
        except provider.DemoProviderError as error:
            uncertain = phase in {"flight_book", "hotel_book"}
            product.status = "unknown" if uncertain else "unavailable"
            if uncertain:
                product.message = "Confirmation was not received. Refresh status to check the existing attempt."
            elif error.reason == "no_match":
                product.message = (
                    "No matching DFW to SGU round trip returning to Dallas on Sunday after 6 PM was found. "
                    "No different airport or date was booked."
                    if phase.startswith("flight_")
                    else "No available Springdale hotel was found for these dates. No other location was booked."
                )
            else:
                product.message = "The shared sandbox could not complete this step. No confirmed booking was returned."
            # The provider's text, payload, passenger, offer and references never enter logs.
            structlog.get_logger().warning("booking_demo.step", step=phase, outcome=product.status, reason=error.reason)
            state.next_phase = "hotel_search" if phase.startswith("flight_") else "done"
        else:
            state.next_phase = PHASES[PHASES.index(phase) + 1]
            structlog.get_logger().info(
                "booking_demo.step",
                step=phase,
                outcome=product.status,
                ms=round((time.monotonic() - started) * 1000),
            )
        state.events.append({"label": LABELS[phase], "status": product.status})
        state.version += 1
        return state

    async def _perform(self, state: DemoState, phase: str, product: Product) -> None:
        """No arbitrary tools, arguments, passenger details, routes or payment methods enter this workflow."""
        if phase == "flight_search":
            offer_fields(product, await provider.search_flight(state.checkin, state.checkout))
        elif phase == "flight_verify":
            offer_fields(product, await provider.verify_flight(product.offer, state.checkin, state.checkout))
        elif phase == "flight_prebook":
            prepared = await provider.prebook_flight(product.offer)
            product.prebook_id = prepared["prebook_id"]
            product.price = str(prepared["price"])
            product.currency = prepared["currency"]
            product.details = prepared["details"]
            product.status = "ready"
        elif phase == "flight_book":
            booking_fields(product, await provider.book_flight(product.prebook_id))
        elif phase == "hotel_search":
            offer_fields(product, await provider.search_hotel(state.checkin, state.checkout))
        elif phase == "hotel_prebook":
            prepared = await provider.prebook_hotel(product.offer)
            product.prebook_id = prepared["prebook_id"]
            if prepared.get("price") is not None:
                product.price = str(prepared["price"])
            product.status = "ready"
        elif phase == "hotel_book":
            # A deterministic reference protects the same receipt even across Vercel workers.
            booking_fields(product, await provider.book_hotel(product.prebook_id, state.hotel_reference))

    async def recover(self, state: DemoState) -> DemoState:
        """Resolve pending or uncertain attempts. Never search again, create a new prebook, or rebook a hotel."""
        for kind, product in (("flight", state.flight), ("hotel", state.hotel)):
            may_have_submitted = state.next_phase == f"{kind}_book"
            if product.status not in {"pending", "unknown"} and not may_have_submitted:
                continue
            if not product.prebook_id:
                continue
            try:
                if kind == "hotel":
                    result = await provider.recover_hotel(state.hotel_reference)
                elif product.booking_id:
                    result = await provider.retrieve_flight(product.booking_id)
                else:
                    # The flight API guarantees one booking per prebook. This never creates a new prebook.
                    result = await provider.recover_flight(product.prebook_id)
                booking_fields(product, result)
            except provider.DemoProviderError:
                if product.status != "pending":
                    product.status = "unknown"
                product.message = "The provider has not returned a final confirmation. Refresh later; do not rebook."
            if may_have_submitted:
                state.next_phase = "hotel_search" if kind == "flight" else "done"
        state.version += 1
        state.events.append({"label": LABELS["recover"], "status": "checked"})
        structlog.get_logger().info(
            "booking_demo.refreshed",
            flightStatus=state.flight.status,
            hotelStatus=state.hotel.status,
        )
        return state
