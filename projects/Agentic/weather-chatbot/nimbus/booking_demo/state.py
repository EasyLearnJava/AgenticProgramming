"""Browser-bound receipts for the isolated, synthetic Nuitée booking demonstration."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from nimbus.config import Settings

COOKIE = "nimbus-booking-demo"
LIFETIME = 6 * 60 * 60
MAX_TOKEN = 96_000
CHICAGO = ZoneInfo("America/Chicago")
PROMPT = re.compile(
    r"(?:please )?book (?:a |my )?trip to zion(?: national park)? this week\s?end"
    r"(?: from dfw)?[.!?]*",
    re.IGNORECASE,
)


def matches(question: str) -> bool:
    """Only this explicit demo instruction bypasses the existing planner and model."""
    return PROMPT.fullmatch(" ".join(question.strip().split())) is not None


class Product(BaseModel):
    """Small display fields, plus private provider handles held inside the signed receipt."""

    model_config = ConfigDict(extra="forbid")
    phase: str = ""
    status: str = "idle"
    title: str = ""
    details: list[str] = Field(default_factory=list)
    price: str = ""
    currency: str = "USD"
    reference: str = ""
    booking_id: str = ""
    message: str = ""
    offer: dict[str, Any] = Field(default_factory=dict, repr=False)
    prebook_id: str = Field(default="", repr=False)

    def public(self) -> dict[str, Any]:
        """Never send raw provider offers or prebook handles as display data."""
        return self.model_dump(exclude={"offer", "prebook_id"})


class DemoState(BaseModel):
    """An expiring demo transaction; every start creates its own hotel deduplication reference."""

    model_config = ConfigDict(extra="forbid")
    id: str
    owner: str
    expires: int
    checkin: str
    checkout: str
    # Receipts created before the route change omitted this field. They may be viewed, never booked again.
    flight_destination: str = "SGU"
    next_phase: str = "flight_search"
    version: int = 0
    flight: Product = Field(default_factory=lambda: Product(title="DFW ↔ LAX · round trip"))
    hotel: Product = Field(default_factory=lambda: Product(title="Hotel near Zion · Springdale, Utah"))
    events: list[dict[str, str]] = Field(default_factory=list)

    @property
    def hotel_reference(self) -> str:
        """Keep retries associated with exactly the same synthetic reservation."""
        return f"nimbus-demo-{self.id}"

    def view(self, *, volatile: bool) -> dict[str, Any]:
        """The UI can show only this allowlisted projection, never a provider response."""
        return {
            "id": self.id,
            "checkin": self.checkin,
            "checkout": self.checkout,
            "flight_destination": self.flight_destination,
            "complete": self.next_phase == "done",
            "next_phase": self.next_phase,
            "flight": self.flight.public(),
            "hotel": self.hotel.public(),
            "events": self.events[-16:],
            "volatile": volatile,
        }


def browser_scope(cookie: str | None) -> str:
    """Use a separate anonymous browser cookie, never a Mem0 identity or user preference."""
    return cookie if cookie and re.fullmatch(r"[A-Za-z0-9_-]{43}", cookie) else secrets.token_urlsafe(32)


def new_state(owner: str, *, now: datetime | None = None) -> DemoState:
    """Use DFW's calendar: the coming Friday through Sunday, never Thursday or a past Friday."""
    local = (now or datetime.now(UTC)).astimezone(CHICAGO)
    friday = local.date() + timedelta(days=(4 - local.weekday()) % 7)
    return DemoState(
        id=secrets.token_hex(16),
        owner=owner,
        expires=int(time.time()) + LIFETIME,
        checkin=friday.isoformat(),
        checkout=(friday + timedelta(days=2)).isoformat(),
        flight_destination="LAX",
    )


class Receipts:
    """Authenticate state without a database. The existing signing secret is domain-separated, never sent out."""

    def __init__(self, settings: Settings) -> None:
        """A standalone secret is optional; the existing browser-signing secret also supports Vercel instances."""
        configured = settings.booking_demo_secret or settings.memory_cookie_secret
        self.volatile = configured is None
        source = configured.get_secret_value().encode() if configured else secrets.token_bytes(32)
        self.key = hmac.digest(source, b"nimbus.booking-demo.receipts.v1", "sha256")

    def encode(self, state: DemoState) -> str:
        """Sign only our bounded state; these receipts are not provider credentials or production keys."""
        body = base64.urlsafe_b64encode(state.model_dump_json().encode()).decode().rstrip("=")
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        token = f"{body}.{signature}"
        if len(token) > MAX_TOKEN:
            raise ValueError("Demo receipt is too large")
        return token

    def decode(self, token: str, owner: str) -> DemoState:
        """Authenticate before parsing; replay is confined to one browser, one demo and its original dates."""
        if len(token) > MAX_TOKEN or token.count(".") != 1:
            raise ValueError("Invalid demo receipt")
        body, signature = token.split(".")
        if not re.fullmatch(r"[a-f0-9]{64}", signature) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", owner):
            raise ValueError("Invalid demo receipt")
        expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Expired demo receipt")
        try:
            data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            state = DemoState.model_validate(data)
        except (ValueError, TypeError, RecursionError) as error:
            raise ValueError("Invalid demo receipt") from error
        if not hmac.compare_digest(state.owner, owner) or state.expires <= time.time():
            raise ValueError("Expired demo receipt")
        return state
