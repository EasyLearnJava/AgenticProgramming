"""Recognize explicit park planning requests and prefill facts the visitor can confirm before a search."""

import re
from typing import Final

from nimbus.nps_alerts import PARKS
from nimbus.park_tools import KnowledgeService

TRIP_WORDS: Final = re.compile(
    r"\b(?:itinerary|trip plan(?:ner)?|plan\b.{0,45}\b(?:visit|trip|vacation|journey)|"
    r"(?:plan|organize)\s+(?:my|our|a|an|the)\s+.{0,35}\b(?:stay|getaway)|"
    r"(?:plan|organize)\s+(?:my|our|a|an)\b.{0,50}\btrip)\b",
    re.I,
)
ISO_DATE: Final = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
COUNT_WORDS: Final = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
PARTY: Final = re.compile(rf"\b([1-9]|{'|'.join(COUNT_WORDS)})\s+(adult|room)s?\b", re.I)
AIRPORT_PAIR: Final = re.compile(r"\b(?i:from|fly|flying)\s+([A-Z]{3})\s+(?i:to|into)\s+([A-Z]{3})\b")
PARK_MENTION: Final = re.compile(
    r"\b(?:national parks?|" + "|".join(re.escape(p[0]) for p in PARKS.values()) + r")\b", re.I
)
# Bound negation to the same short clause. A statement about a different activity must not veto a request.
NEGATIVE_PREFIX: Final = r"\b(?:no|not|never|without|avoid|skip|\w+n't)\b(?:\s+(?!(?:and|but)\b)[\w']+){0,6}\s+"
DECLINES_PLAN: Final = re.compile(NEGATIVE_PREFIX + r"(?:plan(?:ner|ning)?|itinerary|organi[sz]e)\b", re.I)
DECLINES_DRIVING: Final = re.compile(NEGATIVE_PREFIX + r"(?:driv(?:e|ing)|road trip|already there)\b", re.I)
DECLINES_FLIGHT: Final = re.compile(NEGATIVE_PREFIX + r"(?:fly(?:ing)?|flights?)\b", re.I)
DRIVING: Final = re.compile(r"\b(?:driving|road trip|no flights?|already there)\b", re.I)
# Remove request grammar and explicit transport details before the existing location resolver.
# Unknown words, including geographic qualifiers and other destinations, must reach it intact.
REQUEST_WORDS: Final = re.compile(
    r"\b(?:give me|help me|could you|what should (?:i|we) wear|build|create|make|organize|our|itinerary|"
    r"planner|getaway|vacation|journey|road trip)\b",
    re.I,
)
MODE_STATEMENT: Final = re.compile(
    r"\b(?:(?:i(?:'m| am)|we(?:'re| are))\s+(?:not\s+)?(?:driving|flying|already there)|no flights?)\b"
    r"|[,;.]\s*(?:driving|already there)\s*[.!?]?$",
    re.I,
)
FOLLOW_UP: Final = re.compile(
    r"(?:(?:ok(?:ay)?|yes|now|please)[,\s]+)*(?:(?:can|could|would) you |help me )?"
    r"(?:plan (?:for )?(?:a|the|my|our|that) (?:trip|visit)(?: (?:there|to (?:the|that) park))?|"
    r"(?:build|create|make|give me) (?:an?|the) itinerary(?: for (?:it|that park))?)"
    r"(?: please)?[?!. ]*",
    re.I,
)


def planner_intake(
    question: str, knowledge: KnowledgeService | None, previous_user_text: str = ""
) -> dict[str, str] | None:
    """Offer editable trip intake for a park request, retaining only recognized structured fields."""
    # ① Ambiguous parks and an unsupported qualified name require an explicit selection.
    normalized = " ".join(question.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split())
    if not TRIP_WORDS.search(normalized) or DECLINES_PLAN.search(normalized):
        return None
    place_context = previous_user_text if previous_user_text and FOLLOW_UP.fullmatch(normalized) else normalized
    place = AIRPORT_PAIR.sub(" ", place_context)
    for pattern in (ISO_DATE, PARTY, MODE_STATEMENT, REQUEST_WORDS):
        place = pattern.sub(" ", place)
    # The resolver limits input to 500 characters. Never drop a qualifier by passing an overlong location.
    resolved = knowledge.resolve(place) if knowledge is not None and len(place) <= 500 else {}
    destination = resolved.get("destination") if resolved.get("status") == "resolved" else None
    if not destination and not PARK_MENTION.search(place_context):
        return None
    fields: dict[str, str] = {}
    if destination and destination["park_id"] in PARKS:
        fields["park"] = destination["park_id"]
    # ② Prefill concrete dates and traveler counts only. The visitor reviews every field before submitting.
    dates = ISO_DATE.findall(normalized)
    if len(dates) == 2:
        fields.update(arrival=dates[0], departure=dates[1])
    for count, field in PARTY.findall(normalized.casefold()):
        fields[f"{field}s"] = count if count.isdigit() else str(COUNT_WORDS.index(count) + 1)
    driving = DRIVING.search(normalized) and not DECLINES_DRIVING.search(normalized)
    pair = None if DECLINES_FLIGHT.search(normalized) else AIRPORT_PAIR.search(normalized)
    if driving and pair is None:
        fields["transport"] = "drive"
    # Only explicit IATA-shaped tokens are prefilled; never choose a gateway on the visitor's behalf.
    elif pair and not driving:
        fields.update(origin=pair[1], gateway=pair[2], transport="fly")
    return fields
