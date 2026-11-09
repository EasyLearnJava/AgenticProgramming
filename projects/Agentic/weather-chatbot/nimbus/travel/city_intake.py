"""Clarify a general city trip in chat before searching for weather or travel offers."""

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nimbus.constants import MAX_FORECAST_DAYS
from nimbus.memory.models import PreferenceProfile
from nimbus.park_tools import KnowledgeService
from nimbus.travel.airports import AIRPORT_ZONES, normalize_origin
from nimbus.travel.planner_intake import (
    AIRPORT_ROUTE,
    DECLINES_DRIVING,
    DECLINES_PLAN,
    DRIVING,
    OPT_OUT,
    PARK_MENTION,
    WEATHER_ASK,
    analyze_trip,
    normalize_trip_text,
)
from nimbus.travel.weekend_dates import ISO_DATE, MONTH_NAMES, NAMED_DATE, SATURDAY, THANKSGIVING, WEEKEND, visit_dates

# Match requests addressed to Nimbus. A trip mentioned as background for another question stays in ordinary chat.
CITY_REQUEST = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would) you (?:please )?)?(?:help (?:me|us) (?:to )?)?"
    r"(?:(?:plan|organi[sz]e)\s+(?:(?:a|an|the|my|our)\s+)?(?:(?:solo|family|weekend|road|driving)\s+)?"
    r"(?:trip|visit|vacation|getaway)\s+(?:to|in)|"
    r"(?:build|create|make|give me|plan)\s+(?:an?|my|our)\s+itinerary\s+for)\s+(?P<destination>.+)$",
    re.I,
)
DETAIL_START = re.compile(
    r"(?:\s+|,\s*)(?=(?:from|on|for|with|starting|leaving|departing|arriving|returning|this|next|in|over|"
    r"flying|driving|no|skip|without|avoid|tomorrow|today|thanksgiving|" + "|".join(MONTH_NAMES) + r")\b|\d)",
    re.I,
)
# Spaces and a comma allow city/region qualifiers. Limit the label to a place-shaped phrase before echoing it.
PLACE_WORD = r"[^\W\d_]+(?:[.'-][^\W\d_]+)*\.?"
PLACE = re.compile(rf"{PLACE_WORD}(?:(?:,\s*| ){PLACE_WORD}){{0,7}}")
OTHER_TASK = re.compile(
    r"\b(?:find|book|show|check|compare|search|recommend|flights?|hotels?|itinerary|restaurants?|museums?|"
    r"activities|attractions?|sightseeing)\b",
    re.I,
)
SHORT_RANGE = re.compile(
    r"\b(?P<month>" + "|".join(MONTH_NAMES) + r")\.?\s+(?P<start>\d{1,2})\s*"
    r"(?:[-\u2013\u2014]|to|through)\s*(?P<end>\d{1,2})(?![-\d])(?:,?\s+(?P<year>\d{4}))?\b",
    re.I,
)
DATE_GLUE = re.compile(r"\b(?:from|on|to|through|until|and)\b|[\s,.\-\u2013\u2014]+", re.I)


def _trip_text(text: str) -> str:
    """Expand short same-month ranges into the two dates understood by the shared calendar."""
    return SHORT_RANGE.sub(
        r"\g<month> \g<start> \g<year> to \g<month> \g<end> \g<year>", normalize_trip_text(text)
    ).strip(" .!?")


def _dates_only(text: str) -> bool:
    """Only a bare calendar reply continues intake; an actual lookup or a change of topic stays in chat."""
    remainder = text
    for period in (ISO_DATE, NAMED_DATE, THANKSGIVING, SATURDAY, WEEKEND):
        remainder = period.sub("", remainder)
    return remainder != text and not DATE_GLUE.sub("", remainder)


def city_trip_reply(
    question: str,
    travel_tools: tuple[str, ...],
    now: datetime,
    time_zone: str,
    prior_questions: Sequence[str] = (),
    knowledge: KnowledgeService | None = None,
    *,
    preferences: PreferenceProfile | None = None,
) -> str | None:
    """Give a bounded intake response; leave specific searches and park requests to their usual routes."""
    text = _trip_text(question)
    # ① Recover only consecutive user-provided trip details. Assistant text cannot open or redirect a city intake.
    current_dates = ""
    preceding_dates = ""
    if prior_questions and _dates_only(text):
        current_dates = text
        for earlier in reversed(prior_questions):
            text = _trip_text(earlier)
            if not _dates_only(text):
                break
            if not preceding_dates:
                preceding_dates = text
    match = CITY_REQUEST.fullmatch(text)
    if not match or DECLINES_PLAN.search(text) or PARK_MENTION.search(text):
        return None
    if current_dates and knowledge and analyze_trip(text, knowledge, "", now, time_zone):
        # Trail aliases such as "the Narrows" belong to the park flow even without the word "park".
        return None
    # ② Honor specific tasks and opt-outs separately: "find hotels" requests a search; "skip hotels" does not.
    rest = match["destination"]
    positive = OPT_OUT.sub(" ", rest)
    if WEATHER_ASK.search(positive) or OTHER_TASK.search(positive):
        return None
    label = DETAIL_START.split(rest, maxsplit=1)[0].strip(", ")
    if not PLACE.fullmatch(label) or re.search(r"\b(?:or|and|there|here|somewhere|park|trail)\b", label, re.I):
        return None
    place = label.title() if label.islower() else label
    # A stored airport supplies a default only where flights are an available, wanted option.
    excluded = " ".join(OPT_OUT.findall(text)).lower()
    driving = DRIVING.search(text) and not DECLINES_DRIVING.search(text)
    flights = "search_flights" in travel_tools and "fl" not in excluded and not driving
    hotels = "search_hotels" in travel_tools and "hotel" not in excluded and "lodging" not in excluded
    routes = list(AIRPORT_ROUTE.finditer(text))
    origin = normalize_origin(routes[0][1]) if len(routes) == 1 else ""
    saved_origin = preferences.origin if preferences and flights and not routes else ""
    date_zone = AIRPORT_ZONES.get(origin or saved_origin, time_zone)
    # ③ Retain the arrival when the visitor supplies a departure in a later turn.
    dates = visit_dates(current_dates or text, now, date_zone)
    if current_dates and dates.arrival_only:
        earlier_arrival = visit_dates(preceding_dates or text, now, date_zone).arrival_only
        if earlier_arrival:
            dates = visit_dates(f"{earlier_arrival} to {dates.arrival_only}", now, date_zone)
    if dates.interval:
        when = f"Your travel dates are {dates.interval[0]} to {dates.interval[1]}."
    elif dates.arrival_only:
        when = f"You arrive on {dates.arrival_only}. When will you leave?"
    elif dates.options:
        choices = " or ".join(f"{start} to {end}" for start, end in dates.options)
        when = f"Do these dates work for you: {choices}?"
    else:
        when = f"What dates will you be in {place}?"
    # ④ Offer only enabled, wanted services. Origin is relevant only if the visitor chooses flights.
    last_forecast = (now.astimezone(ZoneInfo(date_zone)).date() + timedelta(days=MAX_FORECAST_DAYS - 1)).isoformat()
    start = dates.interval[0] if dates.interval else dates.arrival_only
    beyond_forecast = bool(start and start > last_forecast)
    services = [] if beyond_forecast else ["the forecast"]
    if flights:
        services.append("flights")
    if hotels:
        services.append("hotels")
    if not flights and not hotels:
        if current_dates and (dates.interval or dates.arrival_only) and not beyond_forecast:
            return None
        help_text = "Would you like the forecast for those dates?" if dates.interval else "I can check the forecast."
        if beyond_forecast:
            help_text = f"Check back closer to departure for the forecast. It covers up to {MAX_FORECAST_DAYS} days."
    else:
        if len(services) == 1:
            help_text = f"Would you like me to search for {services[0]}?"
        else:
            choices = ", ".join(services[:-1]) + " or " + services[-1]
            help_text = f"Which would you like me to check: {choices}?"
        if beyond_forecast:
            help_text += f" The forecast covers up to {MAX_FORECAST_DAYS} days, so check back closer to departure."
    if saved_origin:
        help_text += (
            f" Using your saved departure airport: {saved_origin}."
            " Tell me a different departure city or airport for this trip if needed."
        )
    elif flights and not routes:
        help_text += " For flights, include your departure city or airport."
    return f"**Your trip to {place}**\n\n{when}\n\n{help_text}"
