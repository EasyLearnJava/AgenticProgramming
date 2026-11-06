"""Official NWS active alerts at a registry forecast point. No visitor-provided text reaches the service."""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as wall_time
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx2
import structlog
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from nimbus.parks import Destination

ACTIVE_ALERTS = "https://api.weather.gov/alerts/active"
USER_AGENT = "Nimbus park trip planner (https://weather-chatbot-hazel.vercel.app/)"
MAX_BYTES = 1_000_000
MAX_ALERTS = 50


@dataclass(frozen=True)
class WeatherWarning:
    """An actual NWS product at the requested point, with the published alert interval."""

    event: str
    headline: str
    area: str
    severity: str
    start: datetime
    end: datetime | None
    message_expires: datetime | None = None

    def overlap(self, arrival: date, departure: date, time_zone: str) -> Literal["overlaps", "outside", "unknown"]:
        """Compare alert timestamps with inclusive park-local visit dates, including daylight-saving changes."""
        zone = ZoneInfo(time_zone)
        first = datetime.combine(arrival, wall_time.min, zone)
        after = datetime.combine(departure + timedelta(days=1), wall_time.min, zone)
        if self.end is None:
            if self.start >= after:
                return "outside"
            # NWS message expiration is a refresh deadline. A warning without an event end can continue beyond it.
            if first <= self.start or (self.message_expires is not None and self.message_expires > first):
                return "overlaps"
            return "unknown"
        return "overlaps" if self.start < after and self.end > first else "outside"


@dataclass(frozen=True)
class NwsReport:
    """Partial responses retain validated alerts and never masquerade as an empty successful check."""

    items: tuple[WeatherWarning, ...]
    complete: bool
    checked: datetime
    source_url: str
    message: str = ""
    failure_reason: str = ""


class _Properties(BaseModel):
    """Only the CAP fields used to determine coverage and display the official event."""

    event: str = Field(min_length=1, max_length=200)
    headline: str | None = Field(default=None, max_length=1200)
    area: str = Field(alias="areaDesc", min_length=1, max_length=4000)
    severity: Literal["Extreme", "Severe", "Moderate", "Minor", "Unknown"]
    effective: AwareDatetime
    onset: AwareDatetime | None = None
    expires: AwareDatetime
    ends: AwareDatetime | None = None

    @field_validator("effective", "onset", "expires", "ends", mode="before")
    @classmethod
    def timestamp(cls, value: object) -> object:
        if value is not None and not isinstance(value, str):
            raise ValueError("Expected an NWS timestamp")
        return value

    @model_validator(mode="after")
    def interval(self) -> "_Properties":
        if self.expires <= self.effective or (self.ends is not None and self.ends <= (self.onset or self.effective)):
            raise ValueError("Invalid alert interval")
        return self


def _items(payload: Any) -> tuple[tuple[WeatherWarning, ...], bool]:
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON collection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Missing alert records")
    pagination = payload.get("pagination")
    complete = len(features) <= MAX_ALERTS and (
        pagination is None or (isinstance(pagination, dict) and not pagination.get("next"))
    )
    items = []
    for feature in features[:MAX_ALERTS]:
        try:
            if not isinstance(feature, dict) or feature.get("type") != "Feature":
                raise ValueError("Invalid feature")
            raw = feature["properties"]
            if raw["status"] in {"Exercise", "System", "Test", "Draft"} or raw["messageType"] in {
                "Cancel",
                "Ack",
                "Error",
            }:
                continue
            if raw["status"] != "Actual" or raw["messageType"] not in {"Alert", "Update"}:
                raise ValueError("Unknown alert status")
            properties = _Properties.model_validate(raw)
            items.append(
                WeatherWarning(
                    properties.event,
                    properties.headline or properties.event,
                    properties.area,
                    properties.severity,
                    properties.onset or properties.effective,
                    properties.ends,
                    properties.expires,
                )
            )
        except (KeyError, TypeError, ValueError):
            complete = False
    return tuple(items), complete


class NwsAlertsService:
    """Coalesce and cache bounded requests per reviewed point, including short-lived failures."""

    def __init__(
        self,
        make_http_client: Callable[[], httpx2.AsyncClient] = httpx2.AsyncClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._make_http_client = make_http_client
        self._clock = clock
        self._cache: dict[str, tuple[float, NwsReport]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, destination: Destination) -> NwsReport:
        """Request active warnings for this exact reference point. A shared result retains its original check time."""
        started = self._clock()
        point = f"{destination.latitude:.4f},{destination.longitude:.4f}"
        async with self._locks.setdefault(point, asyncio.Lock()):
            cached = self._cache.get(point)
            if cached and cached[0] > self._clock():
                return self._logged(cached[1], started, cached=True)
            source = f"https://forecast.weather.gov/MapClick.php?lat={destination.latitude:.4f}&lon={destination.longitude:.4f}"
            checked = datetime.now(UTC)
            failure_reason = "invalid_response"
            try:
                async with (
                    asyncio.timeout(5),
                    self._make_http_client() as http,
                    http.stream(
                        "GET",
                        ACTIVE_ALERTS,
                        params={"point": point, "status": "actual"},
                        headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"},
                        follow_redirects=False,
                    ) as response,
                ):
                    if response.status_code != 200:
                        failure_reason = "rate_limited" if response.status_code == 429 else "upstream_error"
                        raise ValueError("NWS did not return a complete response")
                    body = bytearray()
                    async for part in response.aiter_bytes():
                        if len(body) + len(part) > MAX_BYTES:
                            raise ValueError("Alert response too large")
                        body.extend(part)
                items, complete = _items(json.loads(body))
                report = NwsReport(
                    items, complete, checked, source, "" if complete else "The NWS alert check is incomplete."
                )
            except (TimeoutError, httpx2.HTTPError, ValueError, TypeError, AttributeError, RecursionError) as error:
                if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
                    failure_reason = "timeout"
                elif isinstance(error, httpx2.HTTPError):
                    failure_reason = "network_error"
                report = NwsReport((), False, checked, source, "The NWS alert check is unavailable.", failure_reason)
            self._cache[point] = (self._clock() + (60 if report.complete else 30), report)
            return self._logged(report, started, cached=False)

    def _logged(self, report: NwsReport, started: float, *, cached: bool) -> NwsReport:
        """Log timing and outcome for Activity, without coordinates, alert contents or raw exceptions."""
        structlog.get_logger().info(
            "nws.alerts",
            tool="park_trip_briefing",
            status="ok" if report.complete else "failed" if report.failure_reason else "partial",
            reason=report.failure_reason,
            cached=cached,
            count=len(report.items),
            ms=round((self._clock() - started) * 1000),
        )
        return report
