"""Interpret explicit home-arrival times without silently replacing them with a weekend evening."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from nimbus.travel.weekend_dates import DatePair, VisitDates

_WEEKDAYS = {name.lower(): index for index, name in enumerate(calendar.day_name)}
_DAY = "(?:" + "|".join(_WEEKDAYS) + ")"
_CLOCK = r"(?:noon|midnight|morning|evening|night|afternoon|\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?|\d{1,2}(?::\d{2})?)"
# Only named return clauses, a deadline, or a bare weekday/time pair have return semantics.
_RETURN = re.compile(
    rf"\b(?:(?:(?:i|we)\s+(?:need|want|have)\s+to\s+)?(?:be\s+|get\s+|come\s+)?"
    rf"(?P<anchor>back|home|return(?:ing)?)\s+(?:(?:home|(?:at|in|to) [A-Za-z]{{3}})\s+)?"
    rf"|(?=(?:by|before)\s)|(?={_DAY}\s+{_CLOCK}))"
    rf"(?:(?P<relation>by|before|at|on|after)\s+)?"
    rf"(?:(?P<day_first>{_DAY})(?:\s+(?:(?P<relation_after>by|before|at|after)\s+)?(?P<clock_after>{_CLOCK}))?"
    rf"|(?P<clock>{_CLOCK})(?:\s+(?:on\s+)?(?P<day_last>{_DAY}))?)(?!\w)",
    re.I,
)
# A clock attached to a departure or park activity doesn't describe arrival back home.
_OTHER_EVENT = re.compile(
    r"\b(?:depart(?:ing)?|leave|leaving|fly(?:ing)? out|arriv(?:e|ing) at|hike|hiking|tour|see)\b"
    r"(?:\s+(?!(?:and|but|weekend|back|home|return)\b)[\w'-]+){0,5}\s*$",
    re.I,
)


@dataclass(frozen=True)
class ReturnPreference:
    text: str
    window: str | None = None
    weekday: int | None = None
    ambiguous: bool = False


def _window(clock: str, relation: str) -> str | None:
    if not clock:
        return "" if relation in {"", "on"} else None
    if relation == "after":
        return None
    if clock in {"night", "evening", "morning"}:
        return ("evening" if clock == "night" else clock) if relation not in {"by", "before"} else None
    if relation == "at" or clock == "afternoon":
        return None  # A point in time is not a latest-arrival deadline.
    if clock in {"noon", "midnight"}:
        minutes = 720 if clock == "noon" else 0
    else:
        parts = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])?m?", clock.replace(".", ""))
        if parts is None or relation not in {"by", "before"} or (not parts[2] and not parts[3]):
            return None
        hour, minute = int(parts[1]), int(parts[2] or 0)
        if minute > 59 or hour > 23 or (parts[3] and not 1 <= hour <= 12):
            return None
        if parts[3]:
            hour = hour % 12 + (12 if parts[3] == "p" else 0)
        minutes = hour * 60 + minute
    minutes -= int(relation == "before")
    if minutes < 0:
        return None
    return "by_noon" if minutes == 720 else f"by_{minutes // 60:02d}:{minutes % 60:02d}"


def return_preference(text: str) -> ReturnPreference:
    """Strip only recognized return clauses from the place and keep their local weekday and time."""
    choices = set()
    cleaned: list[str] = []
    end = 0
    ambiguous = False
    for match in _RETURN.finditer(text):
        day = (match["day_first"] or match["day_last"] or "").lower()
        prefix = text[: match.start()].rstrip()
        if not match["anchor"] and (
            _OTHER_EVENT.search(prefix) or (day == "friday" and match[0].lower().startswith(day))
        ):
            continue
        relation = (match["relation_after"] or match["relation"] or "").lower()
        clock = (match["clock_after"] or match["clock"] or "").lower()
        window = _window(clock, relation)
        if window is None or re.search(r"\b(?:not|never|except|next|following)$", prefix, re.I):
            ambiguous = True
        choices.add((window, _WEEKDAYS.get(day)))
        cleaned.extend((text[end : match.start()], " "))
        end = match.end()
    cleaned.append(text[end:])
    if not choices:
        return ReturnPreference(text)
    if ambiguous or len(choices) > 1:
        return ReturnPreference("".join(cleaned), "", ambiguous=True)
    window, weekday = choices.pop()
    return ReturnPreference("".join(cleaned), window, weekday)


def return_dates(dates: VisitDates, preference: ReturnPreference) -> VisitDates:
    """An explicit weekend return weekday overrides Sunday. Conflicting fixed dates require clarification."""
    if preference.ambiguous:
        return VisitDates()
    weekday = preference.weekday
    if weekday is None:
        return dates

    def adjust(pair: DatePair) -> DatePair | None:
        start, end = (date.fromisoformat(value) for value in pair)
        if dates.weekend:
            # Weekend ranges end on Sunday by default. Accept an unambiguous adjacent return day.
            if weekday not in {4, 5, 6, 0}:
                return None
            end += timedelta(days=1 if weekday == 0 else weekday - 6)
        if end.weekday() != weekday or end <= start:
            return None
        return start.isoformat(), end.isoformat()

    if dates.arrival_only:
        start = date.fromisoformat(dates.arrival_only)
        days = (weekday - start.weekday()) % 7
        if days:
            return VisitDates(interval=(start.isoformat(), (start + timedelta(days=days)).isoformat()))
        return dates  # Same-day returns need clarification in the overnight planner.
    if dates.interval:
        return VisitDates(interval=adjust(dates.interval), weekend=dates.weekend)
    options = tuple(adjusted for pair in dates.options if (adjusted := adjust(pair)))
    return VisitDates(options=options, weekend=dates.weekend)
