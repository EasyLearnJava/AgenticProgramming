"""Independent park checks shared by the initial conditions briefing and the confirmed travel form."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Literal
from zoneinfo import ZoneInfo

import structlog

from nimbus.constants import MAX_FORECAST_DAYS
from nimbus.nps_alerts import PARKS, AlertsReport, NpsAlertsService, NpsNotice, ParkId
from nimbus.nws_alerts import NwsAlertsService, NwsReport
from nimbus.park_tools import KnowledgeService
from nimbus.parks import Destination, ParkChunk
from nimbus.tools import Day, ForecastOutput
from nimbus.weather import UNKNOWN_CONDITIONS

type Forecast = Callable[[Destination, int], Awaitable[ForecastOutput]]
type Decision = Literal["pause", "review", "adapt", "proceed"]
GENERAL_GUIDANCE: Final = "visit hiking weather preparation water clothing"


@dataclass(frozen=True)
class Section[T]:
    """Data from one check, or an explicit reason the check has no data."""

    data: T | None = None
    message: str = ""
    failed: bool = False


@dataclass(frozen=True)
class TripWeather:
    days: tuple[Day, ...]
    unit: str
    reference: str
    partial: bool


@dataclass(frozen=True)
class Conditions:
    weather: Section[TripWeather]
    guidance: Section[tuple[ParkChunk, ...]]
    alerts: Section[AlertsReport]
    warnings: Section[NwsReport]
    decision: Decision
    reason: str
    checked: datetime


async def checked[T](call: Awaitable[Section[T]], deadline: float, name: str) -> Section[T]:
    """Keep a single upstream failure local to its section and propagate visitor cancellation."""
    try:
        async with asyncio.timeout_at(deadline):
            return await call
    except TimeoutError:
        return Section(message=f"The {name} check timed out.", failed=True)
    except Exception as error:
        structlog.get_logger().warning("travel.section_error", section=name, errorClass=type(error).__name__)
        return Section(message=f"The {name} check is unavailable.", failed=True)


def verified_reference(
    knowledge: KnowledgeService | None, park_id: ParkId, destination_id: str = ""
) -> Destination | None:
    """Verify the requested registry ID and parent before using coordinates or a park timezone."""
    if knowledge is None:
        return None
    try:
        lookup = knowledge.resolve(PARKS[park_id][0])
        if destination_id and destination_id != park_id:
            name = next((d["name"] for d in lookup.get("supported_destinations", []) if d["id"] == destination_id), "")
            if not name:
                return None
            lookup = knowledge.resolve(name)
        dest = Destination.model_validate(lookup.get("destination"))
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
        return None
    return dest if dest.id == (destination_id or park_id) and dest.park_id == park_id else None


async def visit_weather(
    destination: Destination | None, arrival: date, departure: date, forecast: Forecast, now: datetime
) -> Section[TripWeather]:
    """Use the park's local dates and the upstream forecast horizon."""
    if destination is None:
        return Section(message="Park forecast coordinates are unavailable.", failed=True)
    today = now.astimezone(ZoneInfo(destination.time_zone)).date()
    end = min(departure, today + timedelta(days=MAX_FORECAST_DAYS - 1))
    if end < arrival:
        return Section(message=f"Check again within the {MAX_FORECAST_DAYS}-day forecast window.")
    result = await forecast(destination, (end - today).days + 1)
    days = tuple(day for day in result.days if arrival <= date.fromisoformat(day.date) <= end)
    if not days:
        return Section(message="No forecast days were returned for this visit.", failed=True)
    known_days = len({day.date for day in days})
    return Section(
        TripWeather(
            days, result.temperature_unit, destination.forecast_reference, known_days < (departure - arrival).days + 1
        ),
        failed=known_days < (end - arrival).days + 1,
    )


async def preparation(
    knowledge: KnowledgeService | None, park: ParkId, destination_id: str, activity: str, arrival: date
) -> Section[tuple[ParkChunk, ...]]:
    """Keep dated preparation references scoped to the confirmed park or trail."""
    if knowledge is None:
        return Section(message="The park guidance index is unavailable.", failed=True)
    queries = dict.fromkeys([activity or GENERAL_GUIDANCE, GENERAL_GUIDANCE])
    for query in queries:
        response = await knowledge.search(destination_id, query, arrival)
        if response.get("status") in {"unsupported", "unavailable"}:
            return Section(message="The park guidance index is unavailable.", failed=True)
        passages = (ParkChunk.model_validate(raw) for raw in response.get("passages", [])[:3])
        scoped = tuple(p for p in passages if p.park_id == park and destination_id in p.destination_ids)
        if scoped:
            label = (
                "No passages matched your topic. Showing general park preparation."
                if query != (activity or GENERAL_GUIDANCE)
                else ""
            )
            return Section(scoped, message=label)
    return Section(message="No preparation passages matched the visit.")


async def park_notices(
    park: ParkId, alerts: NpsAlertsService, caller: Literal["park_trip_plan", "park_trip_briefing"] = "park_trip_plan"
) -> Section[AlertsReport]:
    report = await alerts.get(park, tool=caller)
    return Section(report, failed=not report.complete and report.status != "not_configured")


async def weather_alerts(destination: Destination | None, nws: NwsAlertsService) -> Section[NwsReport]:
    if destination is None:
        return Section(message="The reference point for NWS alerts is unavailable.", failed=True)
    report = await nws.get(destination)
    return Section(report, message=report.message, failed=not report.complete)


def _notice_effect(notice: NpsNotice, park: ParkId, arrival: date, departure: date, today: date) -> Decision:
    """Require explicit whole-park wording and time evidence. Indexed dates describe the API record only."""
    name = re.escape(PARKS[park][0])
    whole_park = rf"(?:the )?(?:entire (?:{name} national )?park|{name} national park)"
    entire = rf"{whole_park} (?:is |will be )?closed"
    span = r"(?: from)? (\d{4}-\d{2}-\d{2}) (?:through|to) (\d{4}-\d{2}-\d{2})"
    # Only affirmative, self-contained statements; qualifiers like "closed to buses" are not park-wide closures.
    text = notice.title + "\n" + notice.description
    remaining = []
    outside = False
    unverified_dates = False
    for sentence in re.split(r"(?:[.!?](?:\s+|$)|\n+)", text):
        statement = sentence.strip()
        dated = re.fullmatch(entire + span, statement, re.I)
        if not dated:
            remaining.append(statement)
            continue
        try:
            start, end = date.fromisoformat(dated[1]), date.fromisoformat(dated[2])
        except ValueError:
            unverified_dates = True
            continue
        if end < start:
            unverified_dates = True
        elif arrival <= end and start <= departure:
            return "pause"
        else:
            outside = True
    if re.fullmatch(whole_park + r" is (?:currently )?closed[.!]?", notice.description.strip(), re.I):
        return "pause" if arrival <= today <= departure else "review"
    residual = "\n".join(remaining)
    if (
        unverified_dates
        or re.search(r"\b(?:park[- ]wide|entire park)\b", residual, re.I)
        or re.search(entire, residual, re.I)
    ):
        return "review"
    scoped = re.search(
        r"\b(?:trail|road|campground|trailhead|shuttle|narrows|landing|entrance|bridge)\b", residual, re.I
    )
    if notice.category == "Information":
        return "adapt" if scoped and re.search(r"\b(?:closure|closed)\b", residual, re.I) else "proceed"
    if scoped or notice.category == "Caution":
        return "adapt"
    return "proceed" if outside else "review"


def _assess(
    park: ParkId,
    destination: Destination | None,
    arrival: date,
    departure: date,
    now: datetime,
    forecast: Section[TripWeather],
    nps: Section[AlertsReport],
    nws: Section[NwsReport],
) -> tuple[Decision, str]:
    if destination is None:
        return (
            "review",
            "The park reference point could not be verified. Review the official sources before continuing.",
        )
    today = now.astimezone(ZoneInfo(destination.time_zone)).date()
    notices = nps.data.notices if nps.data else []
    effects = {_notice_effect(n, park, arrival, departure, today) for n in notices}
    if "pause" in effects:
        return "pause", "NPS reports a park-wide closure affecting your visit. Review the notice or choose other dates."
    intervals = [
        (warning, warning.overlap(arrival, departure, destination.time_zone))
        for warning in (nws.data.items if nws.data else ())
        if warning.end is None or warning.end > now
    ]
    relevant = [warning for warning, overlap in intervals if overlap == "overlaps"]
    if any(w.severity in {"Severe", "Extreme"} and w.event.casefold().endswith("warning") for w in relevant):
        return (
            "pause",
            "A severe weather warning overlaps your visit at the checked point. Review it before planning travel.",
        )
    if (
        not nps.data
        or not nps.data.complete
        or not nws.data
        or not nws.data.complete
        or not forecast.data
        or forecast.data.partial
        or any(day.condition.startswith(UNKNOWN_CONDITIONS) for day in forecast.data.days)
    ):
        return "review", "Conditions could only be checked in part. Review the available information before continuing."
    if any(overlap == "unknown" for _, overlap in intervals):
        return "review", "NWS has not supplied an end time for a weather alert. Recheck its status before your visit."
    if "review" in effects:
        return "review", "A current park notice needs review. Its impact on your dates or route could not be verified."
    if "adapt" in effects:
        return (
            "adapt",
            "Review the locations in the park notices. Plan around affected activities and recheck before leaving.",
        )
    if relevant:
        return (
            "adapt",
            "An official weather alert overlaps your visit at the checked point. Adjust your activities to its timing.",
        )
    if any(
        re.search(r"thunderstorm|freezing (?:rain|drizzle)|heavy (?:snow|rain)|violent rain", day.condition, re.I)
        for day in forecast.data.days
    ):
        return (
            "adapt",
            "The forecast may disrupt outdoor activities. Adjust your plans to the affected days.",
        )
    return "proceed", "These checks found no major disruption for the visit dates. Recheck conditions before leaving."


async def check_conditions(
    *,
    park: ParkId,
    arrival: date,
    departure: date,
    activity: str,
    destination: Destination | None,
    knowledge: KnowledgeService | None,
    alerts: NpsAlertsService,
    nws: NwsAlertsService,
    forecast: Forecast,
    now: datetime,
    deadline: float,
) -> Conditions:
    """Read only park and weather sources. Preparing a briefing never contacts flight or hotel providers."""
    destination_id = destination.id if destination else park
    async with asyncio.TaskGroup() as group:
        sky = group.create_task(
            checked(visit_weather(destination, arrival, departure, forecast, now), deadline, "weather")
        )
        advice = group.create_task(
            checked(preparation(knowledge, park, destination_id, activity, arrival), deadline, "park guidance")
        )
        notices = group.create_task(checked(park_notices(park, alerts, "park_trip_briefing"), deadline, "NPS notices"))
        warnings = group.create_task(checked(weather_alerts(destination, nws), deadline, "NWS alerts"))
    decision, reason = _assess(
        park, destination, arrival, departure, now, sky.result(), notices.result(), warnings.result()
    )
    return Conditions(sky.result(), advice.result(), notices.result(), warnings.result(), decision, reason, now)
