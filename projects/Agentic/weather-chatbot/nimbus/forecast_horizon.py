"""Answer unambiguous single-date forecast requests beyond the forecast window without opening any tools."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from nimbus.constants import MAX_FORECAST_DAYS

# "In 30 days" is one day in the future; "for the next 30 days" includes days we can forecast.
FUTURE_DATE = re.compile(
    r"\b(?:in\s+(?P<ahead>\d{1,3})\s+(?P<unit>days?|weeks?)|"
    r"(?P<offset>\d{1,3})\s+(?P<period>days?|weeks?)\s+from\s+(?:today|now)|"
    r"(?:on\s+)?(?P<iso>\d{4}-\d{2}-\d{2}))\b",
    re.I,
)
WEATHER_ONLY = re.compile(
    r"(?:(?:what(?:'s| is| will)|how(?:'s| is| will)|show me|give me)\s+)?(?:the\s+)?"
    r"(?:weather|forecast|temperatures?)(?:\s+be)?(?:\s+like)?|will it (?:rain|snow)",
    re.I,
)
PLACE = re.compile(r"(?:in|at|for|near)\s+([^\W\d_]+(?:[-'. ,]+[^\W\d_]+){0,6})", re.I)
# If anything in the alleged place is another date, a second request, or a range, keep ordinary chat available.
EXTRA_CLAUSE = re.compile(
    r"\b(?:and|or|then|but|today|tomorrow|yesterday|now|next|last|this|through|from|until|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|week|month|year|"
    r"flight|flights|hotel|hotels|alerts?|notices?|warnings?|plan|check|show|find)\b",
    re.I,
)


def forecast_limit_reply(question: str, now: datetime, time_zone: str) -> str | None:
    """Return the local forecast limit only when the entire question asks for one unavailable weather date."""
    text = " ".join(question.replace("\N{RIGHT SINGLE QUOTATION MARK}", "'").split()).strip(" .!?")
    # ① Require a date at the beginning or end of a simple weather question. Compound queries need other tools.
    period = FUTURE_DATE.search(text)
    if period is None or (period.start() and period.end() != len(text)):
        return None
    request = (text[: period.start()] + text[period.end() :]).strip(" ,")
    weather = WEATHER_ONLY.match(request)
    if weather is None:
        return None
    place = request[weather.end() :].strip()
    if place and (not PLACE.fullmatch(place) or EXTRA_CLAUSE.search(place)):
        return None
    # ② Today is day one of the weather API's window; an invalid date is a request to clarify, never an invented day.
    today = now.astimezone(ZoneInfo(time_zone)).date()
    last_day = today + timedelta(days=MAX_FORECAST_DAYS - 1)
    if period["iso"]:
        try:
            requested = date.fromisoformat(period["iso"])
        except ValueError:
            return None
    else:
        span = int(period["ahead"] or period["offset"])
        in_weeks = (period["unit"] or period["period"]).lower().startswith("week")
        requested = today + (timedelta(weeks=span) if in_weeks else timedelta(days=span))
    if requested <= last_day:
        return None
    return (
        f"The forecast covers up to {MAX_FORECAST_DAYS} days, through {last_day:%B} {last_day.day}, {last_day.year}. "
        f"Check again closer to {requested:%B} {requested.day}, {requested.year}."
    )
