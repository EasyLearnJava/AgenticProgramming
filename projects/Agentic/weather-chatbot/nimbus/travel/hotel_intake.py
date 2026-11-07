"""Clarify an explicitly undated hotel search before the model can invent a stay."""

import re

from nimbus.travel.planner_intake import WEATHER_ASK, normalize_trip_text
from nimbus.travel.weekend_dates import ISO_DATE, NAMED_DATE, SATURDAY, THANKSGIVING, WEEKEND

HOTEL_REQUEST = re.compile(
    r"(?:^|[.?!;]\s*)(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?"
    r"(?:find|search for|look for|show(?: me| us)?|compare|book)\s+"
    r"(?:(?:me|us|a|an|the|some|available|affordable|cheap)\s+){0,3}(?:hotels?|lodging|accommodation)\b",
    re.I,
)
UNKNOWN_DATES = re.compile(
    r"\b(?:haven't|have not|hasn't|has not)\s+(?:yet\s+)?(?:picked|chosen|selected|set|confirmed|decided on)\s+"
    r"(?:(?:our|my|the|exact|travel|hotel|stay)\s+){0,3}dates?\b"
    r"|\bdates?\s+(?:(?:are|is|still)\s+)*(?:tbd|undecided|unknown|not set)\b|\bno (?:fixed )?dates yet\b",
    re.I,
)
OTHER_SEARCH = re.compile(r"\b(?:flights?|airfare|airports?|geocod\w*|guidance|trails?|packing|itinerary)\b", re.I)


def hotel_dates_reply(question: str) -> str | None:
    """Ask for stay dates when a hotel-only request explicitly says the visitor has not chosen them."""
    text = normalize_trip_text(question)
    if not HOTEL_REQUEST.search(text) or not UNKNOWN_DATES.search(text):
        return None
    # A concrete choice in the same message supersedes the earlier uncertainty. Mixed requests use regular chat.
    if WEATHER_ASK.search(text) or OTHER_SEARCH.search(text):
        return None
    if any(period.search(text) for period in (ISO_DATE, NAMED_DATE, WEEKEND, SATURDAY, THANKSGIVING)):
        return None
    if re.search(r"\b(?:tonight|tomorrow|today|next week)\b", text, re.I):
        return None
    return "What are your check-in and check-out dates? I can use those dates to look for available hotels."
