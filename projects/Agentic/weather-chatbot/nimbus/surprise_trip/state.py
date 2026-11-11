"""Separate, browser-bound receipts and inputs for the explicitly confirmed surprise-trip sandbox."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nimbus.booking_demo.state import Product as DemoProduct
from nimbus.booking_demo.state import browser_scope as browser_scope
from nimbus.config import Settings

COOKIE = "nimbus-surprise-trip"
LIFETIME = 6 * 60 * 60
MAX_TOKEN = 96_000
BUDGET_CENTS = 80_000
CHICAGO = ZoneInfo("America/Chicago")


def matches(question: str) -> bool:
    """Only this complete phrase enables the surprise workflow; a standalone yes is never a global command."""
    return question.strip().casefold() == "book a surprise trip"


def date_context() -> dict[str, str]:
    """Give the intake form the same origin-local date boundaries enforced by the server."""
    today = datetime.now(UTC).astimezone(CHICAGO).date()
    return {"today": today.isoformat(), "max_date": (today + timedelta(days=330)).isoformat()}


class TripInput(BaseModel):
    """A small sandbox planner: dates and adult count, with a deterministic two-adults-per-room allocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    checkin: date
    checkout: date
    adults: int = Field(ge=1, le=6)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        """Reject past, reversed, excessive or very distant stays before calling the provider."""
        today = datetime.now(UTC).astimezone(CHICAGO).date()
        if not today <= self.checkin <= today + timedelta(days=330):
            raise ValueError("Choose an arrival within the next 330 days")
        if not 1 <= (self.checkout - self.checkin).days <= 14:
            raise ValueError("Choose a stay of 1 to 14 nights")
        if self.checkout > today + timedelta(days=330):
            raise ValueError("Choose a return within the next 330 days")
        return self

    @property
    def rooms(self) -> int:
        """Use at most two adults per room; the form and quote disclose this allocation."""
        return (self.adults + 1) // 2


class Product(DemoProduct):
    """Keep price evidence and submission state in this workflow, not in the original Zion demo."""

    prepared: dict[str, Any] = Field(default_factory=dict, repr=False)
    price_cents: int | None = None
    submitted: bool = False

    def public(self) -> dict[str, Any]:
        """Only display fields and numeric fee totals leave the provider-handle envelope."""
        result = self.model_dump(exclude={"offer", "prebook_id", "prepared"})
        for name in ("booking_price_cents", "pay_at_property_cents"):
            value = self.prepared.get(name)
            if type(value) is int and value >= 0:
                result[name] = value
        return result


class SurpriseState(BaseModel):
    """A quote and its explicit approval, scoped to a single browser and immutable input selection."""

    model_config = ConfigDict(extra="forbid")
    id: str
    owner: str
    expires: int
    checkin: str
    checkout: str
    adults: int
    phase: str = "flight_search"
    version: int = 0
    quote_expires: int = 0
    approved_cents: int | None = None
    flight: Product = Field(default_factory=lambda: Product(title="DFW ↔ LAS · round trip"))
    hotel: Product = Field(default_factory=lambda: Product(title="Grand Canyon South Rim · Tusayan area"))
    events: list[dict[str, str]] = Field(default_factory=list)
    message: str = ""

    @property
    def rooms(self) -> int:
        """The number of rooms is derived from the selected party, never trusted from the browser."""
        return (self.adults + 1) // 2

    @property
    def hotel_reference(self) -> str:
        """The unique reference survives timeout recovery and never overlaps the Zion demo."""
        return f"nimbus-surprise-{self.id}"

    @property
    def total_cents(self) -> int | None:
        """An incomplete or mixed-currency quote cannot silently fall below the approval threshold."""
        amounts = [self.flight.price_cents, self.hotel.price_cents]
        if any(product.currency != "USD" for product in (self.flight, self.hotel)):
            return None
        if any(type(value) is not int or value <= 0 for value in amounts):
            return None
        return sum(value for value in amounts if value is not None)

    def view(self, *, volatile: bool) -> dict[str, Any]:
        """Expose the complete party/stay price and its confirmation state without raw provider data."""
        total = self.total_cents
        return {
            "id": self.id,
            "phase": self.phase,
            "checkin": self.checkin,
            "checkout": self.checkout,
            "adults": self.adults,
            "rooms": self.rooms,
            "budget_cents": BUDGET_CENTS,
            "total_cents": total,
            "over_budget": total is not None and total > BUDGET_CENTS,
            "approved_cents": self.approved_cents,
            "quote_expires": self.quote_expires,
            "flight": self.flight.public(),
            "hotel": self.hotel.public(),
            "events": self.events[-20:],
            "message": self.message,
            "volatile": volatile,
        }


def new_state(owner: str, selection: TripInput) -> SurpriseState:
    """Create a new unapproved quote; no price, prebook or approval is inherited from another request."""
    return SurpriseState(
        id=secrets.token_hex(16),
        owner=owner,
        expires=int(time.time()) + LIFETIME,
        checkin=selection.checkin.isoformat(),
        checkout=selection.checkout.isoformat(),
        adults=selection.adults,
    )


class Receipts:
    """Authenticate form seeds and quote state with a separate HMAC purpose and browser cookie."""

    def __init__(self, settings: Settings) -> None:
        configured = settings.booking_demo_secret or settings.memory_cookie_secret
        self.volatile = configured is None
        source = configured.get_secret_value().encode() if configured else secrets.token_bytes(32)
        self.key = hmac.digest(source, b"nimbus.surprise-trip.receipts.v1", "sha256")

    def _encode(self, payload: dict[str, Any]) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
        token = f"{body}.{hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()}"
        if len(token) > MAX_TOKEN:
            raise ValueError("Surprise-trip receipt is too large")
        return token

    def _decode(self, token: str, owner: str, kind: str) -> dict[str, Any]:
        if len(token) > MAX_TOKEN or token.count(".") != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{43}", owner):
            raise ValueError("Invalid surprise-trip receipt")
        body, signature = token.split(".")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", body) or not re.fullmatch(r"[a-f0-9]{64}", signature):
            raise ValueError("Invalid surprise-trip receipt")
        expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Expired surprise-trip receipt")
        try:
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        except (ValueError, TypeError, RecursionError) as error:
            raise ValueError("Invalid surprise-trip receipt") from error
        if not isinstance(payload, dict) or payload.get("kind") != kind or payload.get("owner") != owner:
            raise ValueError("Invalid surprise-trip receipt")
        if type(payload.get("expires")) is not int or payload["expires"] <= time.time():
            raise ValueError("Expired surprise-trip receipt")
        return payload

    def form(self, owner: str) -> str:
        """The intake seed authorizes a quote only; it can never authorize a booking."""
        return self._encode({"kind": "form", "owner": owner, "expires": int(time.time()) + LIFETIME})

    def check_form(self, token: str, owner: str) -> None:
        """Accept only an authentic form seed from this browser and this feature."""
        self._decode(token, owner, "form")

    def encode(self, state: SurpriseState) -> str:
        """Bind the selected inputs, prices, phase and explicit approval into the signed receipt."""
        return self._encode(
            {
                "kind": "state",
                "owner": state.owner,
                "expires": state.expires,
                "state": state.model_dump(),
            }
        )

    def decode(self, token: str, owner: str) -> SurpriseState:
        """Never trust a browser-supplied phase, total or confirmation without its signature."""
        payload = self._decode(token, owner, "state")
        state = SurpriseState.model_validate(payload.get("state"))
        if state.owner != owner or state.expires != payload["expires"]:
            raise ValueError("Invalid surprise-trip receipt")
        return state
