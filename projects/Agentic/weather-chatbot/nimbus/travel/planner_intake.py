"""Recognize explicit park planning requests and prefill facts the visitor can confirm before a search."""

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final, Literal

from nimbus.nps_alerts import PARKS
from nimbus.park_tools import KnowledgeService
from nimbus.travel.airports import AIRPORT_ZONES, normalize_origin
from nimbus.travel.return_times import return_dates, return_preference
from nimbus.travel.weekend_dates import ISO_DATE, MONTH_NAMES, NAMED_DATE, SATURDAY, THANKSGIVING, DatePair, visit_dates

TRIP_WORDS: Final = re.compile(
    r"\b(?:itinerary|trip plan(?:ner)?|plan\b.{0,45}\b(?:visit|trip|vacation|journey)|"
    r"(?:plan|organize)\s+(?:my|our|a|an|the)\s+.{0,35}\b(?:stay|getaway)|"
    r"(?:plan|organize)\s+(?:my|our|a|an)\b.{0,50}\btrip)\b",
    re.I,
)
# A question about the weather that mentions a plan ("we plan a trip to Zion next week, will it rain?") wants the
# weather. Only an explicit request beside it ("plan a trip to Zion: will it rain?", "can you help me plan...")
# still opens the form.
WEATHER_ASK: Final = re.compile(
    r"\b(?:weather|forecasts?|rain(?:y|ing)?|snow(?:y|ing)?|storm(?:s|y)?|temperatures?|heat|cold|wear|pack|"
    r"alerts?|warnings?|closures?|notices?)\b",
    re.I,
)
EXPLICIT_PLAN: Final = re.compile(
    r"(?:^|[.!?;:]\s+)(?:please\s+)?(?:plan|organi[sz]e)\b"
    r"|\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:help\s+(?:me|us)\s+)?(?:to\s+)?(?:plan|organi[sz]e)\b"
    r"|\bhelp\s+(?:me|us)\s+(?:to\s+)?(?:plan|organi[sz]e)\b|\bplease\s+plan\b|\bitinerary\b|\btrip planner\b",
    re.I,
)
# When and with whom, removed before the resolver: "Plan a trip to Zion next weekend" names Zion. Places are kept:
# "Zion, Illinois" and "the North Rim" still reach the resolver whole.
MONTHS: Final = "january|february|march|april|may|june|july|august|september|october|november|december"
TRIP_DETAILS: Final = re.compile(
    r"\b(?:(?:this|next|coming|upcoming|following)\s+(?:week(?:end)?|month|summer|spring|fall|autumn|winter)|"
    r"tomorrow|today|tonight|"
    rf"(?:in|during|for|over)\s+(?:{MONTHS}|spring(?:\s+break)?|summer|fall|autumn|winter|the\s+holidays)|"
    r"for\s+(?:a|one|two|three|four|five|\d+)\s+(?:days?|nights?|weeks?)|\d+[- ]?(?:day|night)s?|family|"
    r"(?:with|for)\s+(?:my|our)\s+(?:kids|children|family|partner|wife|husband|friends)"
    r"(?:\s+aged?\s+\d+(?:\s*(?:,|and)\s*\d+)*)?)\b",
    re.I,
)
COUNT_WORDS: Final = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
PARTY: Final = re.compile(rf"\b([1-9]|{'|'.join(COUNT_WORDS)})\s+(adult|room)s?\b", re.I)
CHILDREN = re.compile(
    rf"\b(?:(?P<count>\d+|{'|'.join(COUNT_WORDS)})\s+)?(?:child(?:ren)?|kids?)\s+"
    r"age[ds]?\s+(?P<ages>\d+(?:\s*(?:,\s*(?:and\s+)?|and\s+)\d+)*)\b",
    re.I,
)
# Prefer the explicit origin wording. Don't turn an unqualified city such as Dallas into a particular airport.
_ROUTE_STOP = (
    r"to|into|from|in|for|on|at|with|this|next|the|returning|return|home|back|leaving|and|or|but|by|thanksgiving|"
    + "|".join(MONTH_NAMES)
)
_PLACE_WORD = rf"(?!(?:{_ROUTE_STOP})\b)[a-z][a-z'-]*"
_CITY = rf"{_PLACE_WORD}(?:\s+{_PLACE_WORD}){{0,3}}?"
_ORIGIN_END = rf"(?=$|[.,!?;:]|\s+(?:(?:{_ROUTE_STOP})\b|\d))"
AIRPORT_ROUTE = re.compile(
    rf"\b(?:from|fly(?:ing)?\s+from|fly(?:ing)?)\s+({_CITY})\b(?:\s+(?:to|into)\s+([a-z]{{3}})\b(?![a-z]))?{_ORIGIN_END}",
    re.I,
)
POLITE_PLAN = re.compile(
    r"^(?:(?:i|we)\s+(?:want|would like)\s+to|(?:i|we)'d like to|let's|"
    r"(?:please\s+)?help (?:me|us)(?:\s+to)?)\s+(?=(?:plan|organize)\b)",
    re.I,
)
PARK_MENTION: Final = re.compile(
    r"\b(?:national parks?|" + "|".join(re.escape(p[0]) for p in PARKS.values()) + r")\b", re.I
)
# Bound negation to the same short clause. A statement about a different activity must not veto a request.
NEGATIVE_PREFIX: Final = r"\b(?:no|not|never|without|avoid|skip|\w+n't)\b(?:\s+(?!(?:and|but)\b)[\w']+){0,6}\s+"
DECLINES_PLAN: Final = re.compile(NEGATIVE_PREFIX + r"(?:plan(?:ner|ning)?|itinerary|organi[sz]e)\b", re.I)
DECLINES_DRIVING: Final = re.compile(NEGATIVE_PREFIX + r"(?:driv(?:e|ing)|road trip|already there)\b", re.I)
DECLINES_FLIGHT: Final = re.compile(NEGATIVE_PREFIX + r"(?:fly(?:ing)?|flights?)\b", re.I)
DRIVING: Final = re.compile(r"\b(?:driving|road trip|already there)\b", re.I)
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
# Strip only the weather-question grammar. Any place qualifier after it still reaches the resolver.
WEATHER_PREFIX = re.compile(
    r"^(?:(?:what(?:'s| is)|how(?:'s| is)) (?:the )?(?:weather|forecast|temperature)(?: like)?|"
    r"(?:is|are) there (?:(?:a|an|any) )?(?:(?:flash[- ]flood|flood|heat|weather|storm|winter storm) )?"
    r"(?:warnings?|watches|advisories|alerts?|closures?))\s+(?:in|at|around|near|for)\s+",
    re.I,
)
GENERIC_PARK = re.compile(
    r"(?:please )?plan (?:a|an|the|my|our) (?:trip|visit) to (?:a |some |one of the )?national parks?", re.I
)
FOLLOW_UP: Final = re.compile(
    r"(?:(?:ok(?:ay)?|yes|now|please)[,\s]+)*(?:(?:can|could|would) you )?(?:help (?:me|us) )?"
    r"(?:plan (?:for )?(?:a|the|my|our|that) (?:trip|visit)(?: (?:there|to (?:the|that) park))?|"
    r"(?:build|create|make|give me) (?:an?|the) itinerary(?: for (?:it|that park))?)"
    r"(?: please)?[?!. ]*",
    re.I,
)

type TripKind = Literal["form", "briefing", "choose_park", "choose_weekend", "other_place"]


@dataclass(frozen=True)
class TripIntent:
    """Editable details and preferences from this question, separate from permission to request quotes."""

    kind: TripKind
    fields: dict[str, str]
    destination_id: str = ""
    skip_flights: bool = False
    skip_hotels: bool = False

    depart_window: str = ""
    return_window: str = ""
    origin_zone: str = ""
    weekend_options: tuple[DatePair, ...] = ()
    candidate_parks: tuple[str, ...] = ()


# Scoped opt-outs support both items of "no flights or hotels"; a flight opt-out alone says nothing about driving.
_SERVICE = r"(?:flights?|fly(?:ing)?|hotels?|lodging)"
OPT_OUT = re.compile(
    rf"\b(?:no|skip|without|avoid|(?:do not|don't|never)\s+(?:(?:search|look|book)(?:\s+(?:for|up))?\s+)?)"
    rf"\s*(?:any\s+)?({_SERVICE}(?:\s+(?:or|and)\s+{_SERVICE})?)\b",
    re.I,
)

WEEKEND_TIMES = re.compile(r"\b(?:friday|sunday)(?:\s+(?:morning|night|evening))?\b", re.I)
TRIP_FILLER = re.compile(r"\b(?:but|solo|driving|returning|coming back|going|leaving|departing)\b", re.I)
_CHECK = r"(?:weather(?:\s+(?:alerts?|warnings?))?|forecasts?|alerts?|warnings?|park notices?|conditions)"
GENERIC_CHECK = re.compile(
    rf"\b(?:check|include|show)(?:\s+(?:me|us|for))?\s+(?:(?:the|any)\s+)?"
    rf"{_CHECK}(?:\s+and\s+(?:(?:the|any)\s+)?{_CHECK})*(?:\s+first)?\b",
    re.I,
)
WEATHER_QUESTION = re.compile(
    r"\b(?:(?:will|could|might)\s+(?:there\s+be|it)|(?:is|are)\s+there)\s+(?:any\s+)?"
    r"(?:rain|snow|storms?|flooding|warnings?|alerts?|closures?)\b",
    re.I,
)
# Only a candidate for visitor confirmation may come from the first clause. A qualifier in the destination
# itself ("Zion, Illinois", "Grand Canyon North Rim") must reach the resolver intact.
EXTRA_CLAUSE = re.compile(r"[.!?;]|\b(?:with|because|we(?:'ll)?|i(?:'ll)?|can you|will there be)\b", re.I)


def normalize_trip_text(text: str) -> str:
    """Normalize a small set of planning and weekend phrases shared by city and park intake."""
    text = " ".join(text.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split())
    # "Play a song about a trip" is a different request. Only repair the anchored imperative.
    text = re.sub(r"^(please\s+)?play(?=\s+(?:(?:a|my|our|the)\s+)?trip\b)", r"\1plan", text, flags=re.I)
    text = re.sub(r"\bweek[ -]+end\b", "weekend", text, flags=re.I)
    text = POLITE_PLAN.sub("", text)
    return re.sub(r"\b(?:yosemitte|yosmite)\b", "Yosemite", text, flags=re.I)


def _travel_fields(normalized: str, fields: dict[str, str]) -> tuple[bool, bool]:
    """Carry party and airport inputs forward, keeping service opt-outs separate from travel mode."""
    for count, field in PARTY.findall(normalized.casefold()):
        fields[f"{field}s"] = count if count.isdigit() else str(COUNT_WORDS.index(count) + 1)
    ages: list[int] = []
    for children in CHILDREN.finditer(PARTY.sub(" ", normalized)):
        stated = [int(value) for value in re.findall(r"\d+", children["ages"])]
        count = (children["count"] or "").casefold()
        expected = COUNT_WORDS.index(count) + 1 if count in COUNT_WORDS else int(count or len(stated))
        if expected != len(stated) or max(stated) > 17:
            ages = []
            break
        ages.extend(stated)
    if 0 < len(ages) <= 8:
        fields["children_ages"] = ",".join(str(age) for age in ages)
    driving = DRIVING.search(normalized) and not DECLINES_DRIVING.search(normalized)
    skipped = " ".join(OPT_OUT.findall(normalized)).casefold()
    skip_flights = bool(DECLINES_FLIGHT.search(normalized) or re.search(r"\bfl", skipped))
    skip_hotels = "hotel" in skipped or "lodging" in skipped
    routes = list(AIRPORT_ROUTE.finditer(normalized))
    route = routes[0] if len(routes) == 1 else None
    if driving and (route is None or not route[2]):
        fields["transport"] = "drive"
    if route and not (route[2] and driving):
        origin = normalize_origin(route[1])
        code = len(origin) == 3 and origin.isupper()
        fields["origin"] = origin
        explicit_flight = route.group().casefold().startswith("fly")
        if not skip_flights and not driving and (code or route[2] or explicit_flight):
            fields["transport"] = "fly"
            if route[2]:
                fields["gateway"] = route[2].upper()
    return skip_flights, skip_hotels


def _departure_window(text: str, weekend: bool) -> str:
    """Use an explicit departure period before the editable weekend default."""
    default = "evening" if weekend else ""
    outbound = re.search(r"\bfriday (?P<window>morning|night|evening)\b", text, re.I)
    return ("morning" if outbound["window"].lower() == "morning" else "evening") if outbound else default


def analyze_trip(
    question: str, knowledge: KnowledgeService | None, previous_user_text: str, now: datetime, time_zone: str
) -> TripIntent | None:
    """Resolve a park before any lookup; route a valid dated visit to conditions and incomplete details to intake."""
    # ① Ambiguous parks and an unsupported qualified name require an explicit selection.
    normalized = normalize_trip_text(question)
    if previous_user_text and not TRIP_WORDS.search(normalized):
        # A bare park name only continues a park choice made by the preceding user request.
        answer = normalized.rstrip(".!? ").casefold()
        chosen = next(
            (
                key
                for key, (name, _, _) in PARKS.items()
                if answer in {name.casefold(), f"{name.casefold()} national park"}
            ),
            None,
        )
        if chosen:
            previous = analyze_trip(previous_user_text, knowledge, "", now, time_zone)
            if previous and previous.kind in {"choose_park", "form"} and chosen in previous.candidate_parks:
                chosen_fields = {**previous.fields, "park": chosen}
                chosen_kind: TripKind = (
                    "choose_weekend"
                    if previous.weekend_options
                    else ("briefing" if chosen_fields.get("departure") else "form")
                )
                return replace(
                    previous, fields=chosen_fields, kind=chosen_kind, candidate_parks=(), destination_id=chosen
                )
    if not TRIP_WORDS.search(normalized) or DECLINES_PLAN.search(normalized):
        return None
    if WEATHER_ASK.search(normalized) and not EXPLICIT_PLAN.search(normalized):
        return None
    return_pref = return_preference(normalized)
    referent = return_pref.text
    if previous_user_text:
        for detail in (
            AIRPORT_ROUTE,
            ISO_DATE,
            NAMED_DATE,
            THANKSGIVING,
            SATURDAY,
            TRIP_DETAILS,
            OPT_OUT,
            PARTY,
            CHILDREN,
        ):
            referent = detail.sub(" ", referent)
        referent = re.sub(r"[,.?!;:]", " ", referent)
        referent = re.sub(r"\b(?:for|with|and)\s*$", " ", referent, flags=re.I)
    place_context = (
        WEATHER_PREFIX.sub("", normalize_trip_text(previous_user_text))
        if previous_user_text and FOLLOW_UP.fullmatch(" ".join(referent.split()))
        else return_pref.text
    )
    # The resolver ignores punctuation. Mark the itinerary boundary to distinguish a geographic qualifier
    # inside the destination from a separate, unrecognized request that follows the park or origin.
    place = AIRPORT_ROUTE.sub("; ", place_context)
    place = re.sub(r"\bweekend(?=\s+(?:trip|visit|getaway)\b)", " ", place, flags=re.I)
    for pattern in (
        ISO_DATE,
        NAMED_DATE,
        THANKSGIVING,
        SATURDAY,
        PARTY,
        CHILDREN,
        OPT_OUT,
        MODE_STATEMENT,
        WEEKEND_TIMES,
        GENERIC_CHECK,
        WEATHER_QUESTION,
        REQUEST_WORDS,
        TRIP_DETAILS,
        TRIP_FILLER,
    ):
        place = pattern.sub("; " if pattern is TRIP_DETAILS else " ", place)
    # The resolver limits input to 500 characters. Never drop a qualifier by passing an overlong location.
    resolved = knowledge.resolve(place) if knowledge is not None and len(place) <= 500 else {}
    destination = resolved.get("destination") if resolved.get("status") == "resolved" else None
    if not destination and not PARK_MENTION.search(place_context):
        return None
    fields: dict[str, str] = {}
    if destination and destination["park_id"] in PARKS:
        fields["park"] = destination["park_id"]
    # ② Only an unambiguous destination and usable local date range can start condition checks.
    skip_flights, skip_hotels = _travel_fields(return_pref.text, fields)
    zone = AIRPORT_ZONES.get(fields.get("origin", ""), time_zone)
    dates = return_dates(visit_dates(normalized, now, zone), return_pref)
    if dates.interval:
        fields.update(zip(("arrival", "departure"), dates.interval, strict=True))
    elif dates.arrival_only:
        fields["arrival"] = dates.arrival_only
    candidates = tuple(dict.fromkeys(c["park_id"] for c in resolved.get("candidates", []) if c["park_id"] in PARKS))
    if not destination and GENERIC_PARK.fullmatch(" ".join(place.strip(" ;.,!?").split())):
        candidates = tuple(PARKS)
    if knowledge and not destination and not candidates and (dates.interval or dates.options) and len(place) <= 500:
        prefix = EXTRA_CLAUSE.split(place, maxsplit=1)[0].strip()
        if prefix and prefix != place.strip():
            possible = knowledge.resolve(prefix).get("candidates", [])
            candidates = tuple(dict.fromkeys(c["park_id"] for c in possible if c["park_id"] in PARKS))
    kind: TripKind = "form"
    if destination and dates.options:
        kind = "choose_weekend"
    elif destination and dates.interval:
        kind = "briefing"
    elif dates.interval or dates.options:
        if candidates or resolved.get("status") in {None, "unavailable"}:
            kind = "choose_park"
            candidates = candidates or tuple(PARKS)
        else:
            kind = "other_place"
    depart_window = _departure_window(normalized, dates.weekend)
    return_window = return_pref.window if return_pref.window is not None else ("evening" if dates.weekend else "")
    if fields.get("transport") == "drive" or skip_flights:
        depart_window = return_window = ""
    return TripIntent(
        kind,
        fields,
        destination_id=destination["id"] if destination else "",
        skip_flights=skip_flights,
        skip_hotels=skip_hotels,
        depart_window=depart_window,
        return_window=return_window,
        origin_zone=zone,
        weekend_options=dates.options,
        candidate_parks=candidates,
    )
