"""Conservative cache guards. Embeddings rank candidates; independent dimensions authorize reuse."""

import hashlib
import json
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from nimbus.memory.context import MemoryContext
from nimbus.prompts import to_system_prompt
from nimbus.scope_guard import SCOPE_POLICY_VERSION
from nimbus.semantic_cache.models import VERSION, CachePolicy
from nimbus.utils import to_unit_system

# Longer/complex requests remain with the agent. This ASCII bound also fits MiniLM's 256-token context.
MAX_CHARS = 240
UNSAFE = re.compile(
    r"\b(?:and|or|but|not|tomorrow|yesterday|next|week|weekend|night|tonight|hour|hourly|afternoon|morning|"
    r"rain|snow|wind|temperature|alerts?|warnings?|safe|danger|hike|hiking|pack|parks?|zion|yosemite|"
    r"trip|travel|plan|flight|hotel|remember|forget|prefer|ignore|instructions?|system|instead|there|"
    r"same|previous|compare|versus|vs|my|home|work|address|latitude|longitude|"
    r"use|using|always|answer|respond|reply|speak|write|format)\b"
)
PLACE_UNITS = re.compile(r"\b(?:celsius|fahrenheit|metric|imperial|units)\b")
PATTERNS = (
    r"(?:the )?(?:weather|wether|forecast)(?: like)? (?:in|for|at) (?P<place>.+?)(?: look like| like)?",
    r"(?P<place>.+?)(?:'s)? (?:weather|wether|forecast)",
)
CITY_ALIASES = {"vizag": "visakhapatnam"}


def normalized(text: str) -> str:
    """Normalize only casing and whitespace; preserve qualifiers and dates."""
    return " ".join(text.casefold().split())


def canonical_city(name: str) -> str:
    """Resolve approved exact city aliases without guessing spellings or removing location qualifiers."""
    name = normalized(name)
    return CITY_ALIASES.get(name, name)


def compatible_history(earlier: CachePolicy | None, current: CachePolicy) -> bool:
    """Allow explicit city changes while retaining earlier time, unit and same-city qualifier constraints."""
    if earlier is None:
        return False
    if earlier.place != current.place and ("," in earlier.place or "," in current.place):
        return False
    return earlier.model_copy(update={"place": current.place}) == current


def digest(value: object) -> str:
    """A stable fingerprint rather than a logged or indexed copy of private context."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def embedding_text(question: str) -> str:
    """Remove polite weather-question framing, preserving all place/date/unit content before embedding."""
    text = normalized(question).strip(" ?.!")
    text = re.sub(r"^(?:please )?(?:can you |could you )?(?:tell me |show me |give me )?", "", text)
    text = re.sub(r"^(?:what is |what's |how is |how's |what does )", "", text)
    text = re.sub(r" (?:look like|like)$", "", text)
    # This spelling is explicitly admitted by the weather guard; it cannot alter a destination name.
    text = re.sub(r"\bwether\b", "weather", text)
    for alias, city in CITY_ALIASES.items():
        text = re.sub(rf"\b{re.escape(alias)}\b", city, text)
    return text


def cache_policy(
    question: str, now: datetime, locale: str, time_zone: str, preferred_units: str = ""
) -> CachePolicy | None:
    """Accept explicit, single-place English overviews; unfamiliar wording safely uses the agent."""
    # ① Refuse constraints before removing polite language. No lossy truncation or nearest-city guessing.
    if len(question) > MAX_CHARS or not question.isascii() or not locale.lower().startswith("en"):
        return None
    text = normalized(question).strip(" ?.!")
    if UNSAFE.search(text) or re.search(r"[\d;:<>/\\]", text):
        return None
    text = re.sub(r"^(?:please )?(?:can you |could you )?(?:tell me |show me |give me )?", "", text)
    text = re.sub(r"^(?:what is |what's |how is |how's |what does )", "", text)
    text = re.sub(r"^(?:the )?weather like in ", "weather in ", text)
    units = preferred_units or to_unit_system(locale)
    unit_match = re.search(r" (?:in )?(celsius|fahrenheit|metric|imperial)$", text)
    if unit_match:
        units = "metric" if unit_match[1] in {"celsius", "metric"} else "imperial"
        text = text[: unit_match.start()]
    intent = "overview"
    timing = re.search(r" (today|now|right now)$", text)
    if timing:
        intent = "today" if timing[1] == "today" else "current"
        text = text[: timing.start()]
    for pattern in PATTERNS:
        match = re.fullmatch(pattern, text)
        if match:
            place = match["place"].strip()
            if PLACE_UNITS.search(place):
                return None
            if re.fullmatch(r"[a-z][a-z ,.'-]{1,79}", place) and len(place.split()) <= 6:
                city, *qualifiers = [part.strip() for part in place.split(",")]
                place = ", ".join((canonical_city(city), *qualifiers))
                return CachePolicy(
                    place=place,
                    intent=intent,
                    units=units,
                    locale=locale,
                    time_zone=time_zone,
                    day=now.astimezone(ZoneInfo(time_zone)).date().isoformat(),
                )
    return None


def context_fingerprint(memory: MemoryContext, model: str, features: tuple[bool, ...], build: str = "") -> str:
    """Invalidate on model/features/schema or any preference revision/mode change without storing values."""
    prompt_contract = to_system_prompt(
        datetime(2000, 1, 1, tzinfo=UTC),
        "en-US",
        "UTC",
        parks_enabled=features[0],
        travel_tools=tuple(
            name for name, enabled in zip(("search_flights", "search_hotels"), features[1:], strict=True) if enabled
        ),
    )
    return digest(
        {
            "version": VERSION,
            "scope_policy": SCOPE_POLICY_VERSION,
            "prompt": digest(prompt_contract),
            "build": build,
            "model": model,
            "features": features,
            "memory_mode": memory.identity.mode if memory.identity else "none",
            "memory_status": memory.snapshot.status,
            "memory_revision": memory.snapshot.revision,
            "preferences": memory.preferences.model_dump(),
        }
    )
