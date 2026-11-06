"""Interpret bounded visit dates in the traveler's local calendar, independently of the model."""

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nimbus.travel.models import MAX_DAYS_AHEAD, MAX_STAY_NIGHTS

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MONTH_NAMES = {
    name.lower(): index
    for names in (calendar.month_name, calendar.month_abbr)
    for index, name in enumerate(names)
    if index
}
MONTH_NAMES["sept"] = 9
NAMED_DATE = re.compile(r"\b(" + "|".join(MONTH_NAMES) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4})\b)?", re.I)
THANKSGIVING = re.compile(r"\b(?:us\s+|u\.s\.\s+)?thanksgiving\s+weekend(?:\s+(\d{4}))?\b", re.I)
SATURDAY = re.compile(r"\bthis\s+saturday\b", re.I)
WEEKEND_TRIP = re.compile(r"\bweekend\s+(?:trip|visit|getaway)\b", re.I)
UNSPECIFIED_DATES = re.compile(
    r"\b(?:someday|sometime|later|next (?:week|month|year)|in (?:the|a|" + "|".join(MONTH_NAMES) + r"))\b", re.I
)
WEEKEND = re.compile(r"\b(this|next|following|upcoming|coming)\s+weekend\b", re.I)
FRIDAY_SUNDAY = re.compile(r"\bfriday (?:evening|night)\b.{0,55}\bsunday (?:evening|night)\b", re.I)
UNCERTAIN_WEEKEND = re.compile(
    r"\b(?:not|except|skip|avoid)\s+(?:this|next|following|upcoming|coming)\s+weekend\b"
    r"|\bweekend\s+or\s+(?:sometime|(?:next|this)\s+(?:month|week)|in\s+\w+)\b",
    re.I,
)
type DatePair = tuple[str, str]


@dataclass(frozen=True)
class VisitDates:
    """A usable range, explicit alternatives when the weekend has started, or dates to ask about."""

    interval: DatePair | None = None
    options: tuple[DatePair, ...] = ()
    weekend: bool = False
    arrival_only: str = ""


def _pair(start: date, end: date) -> DatePair:
    return start.isoformat(), end.isoformat()


def _named_date(match: re.Match[str], earliest: date) -> date:
    month, day, year = match.groups()
    candidate = date(int(year or earliest.year), MONTH_NAMES[month.lower()], int(day))
    if not year and candidate < earliest:
        candidate = candidate.replace(year=candidate.year + 1)
    return candidate


def _thanksgiving_friday(year: int) -> date:
    """The day after US Thanksgiving (the fourth Thursday of November)."""
    november = date(year, 11, 1)
    return november + timedelta(days=(3 - november.weekday()) % 7 + 22)


def visit_dates(text: str, now: datetime, time_zone: str) -> VisitDates:
    """Explicit dates override relative days. Incomplete, invalid or conflicting dates need editing."""
    today = now.astimezone(ZoneInfo(time_zone)).date()
    iso = ISO_DATE.findall(text)
    named = list(NAMED_DATE.finditer(text))
    if iso or named:
        try:
            if len(iso) + len(named) == 1:
                start = date.fromisoformat(iso[0]) if iso else _named_date(named[0], today)
                return (
                    VisitDates(arrival_only=start.isoformat())
                    if 0 <= (start - today).days <= MAX_DAYS_AHEAD
                    else VisitDates()
                )
            if len(iso) == 2 and not named:
                start, end = map(date.fromisoformat, iso)
            elif len(named) == 2 and not iso:
                start = _named_date(named[0], today)
                end = _named_date(named[1], start)
            else:
                return VisitDates()
        except ValueError:
            return VisitDates()
        if start < today or (end - today).days > MAX_DAYS_AHEAD or not 1 <= (end - start).days <= MAX_STAY_NIGHTS:
            return VisitDates()
        return VisitDates(interval=_pair(start, end))

    weekends = WEEKEND.findall(text.lower())
    if len(weekends) > 1 or UNCERTAIN_WEEKEND.search(text):
        return VisitDates()
    if holiday := THANKSGIVING.search(text):
        if weekends or re.search(r"\b(?:canadian|except|avoid|skip|not|or)\s*$", text[: holiday.start()], re.I):
            return VisitDates()
        year = int(holiday[1] or today.year)
        if year < today.year or year > today.year + 1:
            return VisitDates()
        friday = _thanksgiving_friday(year)
        if not holiday[1] and today > friday + timedelta(days=2):
            friday = _thanksgiving_friday(year + 1)
        sunday = friday + timedelta(days=2)
        if (friday - today).days > MAX_DAYS_AHEAD or today >= sunday:
            return VisitDates()
        return VisitDates(interval=_pair(max(today, friday), sunday), weekend=True)
    if SATURDAY.search(text):
        saturday = today + timedelta(days=(5 - today.weekday()) % 7)
        if weekends or re.search(r"\b(?:until|to|through)\s+sunday\b", text, re.I):
            return VisitDates(interval=_pair(saturday, saturday + timedelta(days=1)), weekend=True)
        return VisitDates(arrival_only=saturday.isoformat())
    if not weekends and not FRIDAY_SUNDAY.search(text) and not WEEKEND_TRIP.search(text):
        return VisitDates()
    if not weekends and WEEKEND_TRIP.search(text) and UNSPECIFIED_DATES.search(text):
        return VisitDates()
    friday = today + timedelta(days=4 - today.weekday())
    label = weekends[0] if weekends else "this"
    if label in {"next", "following"} or (label in {"coming", "upcoming"} and today > friday):
        friday += timedelta(days=7)
    sunday = friday + timedelta(days=2)
    if today > friday:
        # A same-day Sunday trip needs different travel choices than the overnight planner.
        options = (_pair(today, sunday),) if today < sunday else ()
        following = _pair(friday + timedelta(days=7), sunday + timedelta(days=7))
        return VisitDates(options=(*options, following), weekend=True)
    return VisitDates(interval=_pair(friday, sunday), weekend=True)
