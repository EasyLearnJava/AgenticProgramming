"""Bounded official NPS notice checks, separate from the static guidance index and every visitor's question."""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx2
import structlog
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from nimbus.utils import checked_source_url

NPS_ALERTS_URL = "https://developer.nps.gov/api/v1/alerts"
NPS_TIMEOUT_SECONDS = 6.0
MAX_RESPONSE_BYTES = 1_000_000
PAGE_SIZE = 50
MAX_PAGES = 3
PARKS = {
    "zion": ("Zion", "zion", "https://www.nps.gov/zion/index.htm"),
    "grand-canyon": ("Grand Canyon", "grca", "https://www.nps.gov/grca/index.htm"),
    "yosemite": ("Yosemite", "yose", "https://www.nps.gov/yose/index.htm"),
}
type ParkId = Literal["zion", "grand-canyon", "yosemite"]
type NoticeCategory = Literal["Danger", "Caution", "Information", "Park Closure"]


class NpsNotice(BaseModel):
    """Public API text; lastIndexedDate is an indexing timestamp, not a publication or validity date."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)
    id: str = Field(min_length=1, max_length=150)
    park_code: str = Field(alias="parkCode", max_length=10)
    category: NoticeCategory
    title: str = Field(min_length=1, max_length=1000)
    description: str = Field(max_length=15000)
    url: str = Field(default="", max_length=3000)
    last_indexed: str = Field(default="", alias="lastIndexedDate", max_length=100)
    source_is_fallback: bool = False


class AlertsReport(BaseModel):
    """A successful, empty, incomplete or unavailable check; absence of notices is never a safety guarantee."""

    model_config = ConfigDict(frozen=True)
    status: Literal["found", "no_alerts", "not_configured", "unavailable", "unsupported"]
    park_id: str
    park_name: str
    source_url: str
    notices: list[NpsNotice] = Field(default_factory=list)
    total: int = 0
    complete: bool = False
    cached: bool = False
    fetched_at: datetime | None = None
    reason: str | None = None
    scope_note: str = (
        "Park-level notices, not a complete trail status or safety check. NPS API updates may lag its website "
        "by about two hours; check the official park page. Notices do not predict conditions for a future trip."
    )


@dataclass(frozen=True)
class AlertsCallRecord:
    """The chat's public notice artifact; credentials and wire headers are never included."""

    ms: int
    report: AlertsReport
    sources: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        """A public chip summary without confusing an unsuccessful check with an empty successful check."""
        return f"{self.report.park_name} notices: {self.report.status.replace('_', ' ')}"


class _Page(BaseModel):
    """Bound and validate API records before any public rendering or model input."""

    total: int = Field(ge=0, le=100000)
    start: int = Field(default=0, ge=0)
    data: list[Any] = Field(max_length=PAGE_SIZE)


class NpsAlertsService:
    """Three fixed park codes, short shared caches and single-flight requests; no question or secret enters a URL."""

    def __init__(
        self,
        key: SecretStr | None,
        make_http_client: Callable[[], httpx2.AsyncClient] = httpx2.AsyncClient,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Configure without contacting NPS; each fetch owns and closes its own HTTP client."""
        self._key = key
        self._make_http_client = make_http_client
        self._clock = clock
        self._cache: dict[str, tuple[float, AlertsReport]] = {}
        self._pending: dict[str, asyncio.Task[AlertsReport]] = {}

    def configuration_report(self, park_id: str) -> AlertsReport | None:
        """Inspect configuration without performing or logging a check, including on ordinary page views."""
        if park_id not in PARKS:
            return AlertsReport(
                status="unsupported",
                park_id="unsupported",
                park_name="Unsupported park",
                source_url="https://www.nps.gov/index.htm",
            )
        name, _code, url = PARKS[park_id]
        if self._key is None:
            return AlertsReport(status="not_configured", park_id=park_id, park_name=name, source_url=url)
        return None

    async def get(
        self, park_id: str, *, tool: Literal["get_park_alerts", "park_alerts", "park_trip_plan"] = "get_park_alerts"
    ) -> AlertsReport:
        """Return a detached report and record its actual caller; missing configuration never makes a request."""
        started = self._clock()
        if report := self.configuration_report(park_id):
            return self._logged(report, started, tool)
        # ① Cache only bounded public reports, retaining the original fetch time and never serving expired data.
        cached = self._cache.get(park_id)
        if cached and cached[0] > self._clock():
            return self._logged(cached[1].model_copy(deep=True, update={"cached": True}), started, tool)
        task = self._pending.get(park_id)
        if task is None or task.get_loop() is not asyncio.get_running_loop():
            task = asyncio.create_task(self._fetch(park_id))
            self._pending[park_id] = task
            task.add_done_callback(lambda done: self._finished(park_id, done))
        return self._logged((await asyncio.shield(task)).model_copy(deep=True), started, tool)

    def _logged(self, report: AlertsReport, started: float, tool: str) -> AlertsReport:
        """Record every public check, including cache hits and missing configuration, with no notice or secret text."""
        structlog.get_logger().info(
            "nps.alerts",
            park=report.park_id,
            tool=tool,
            status="failed"
            if report.status == "unavailable"
            else "partial"
            if report.status == "found" and not report.complete
            else report.status,
            ms=round((self._clock() - started) * 1000),
            noticeCount=len(report.notices),
            complete=report.complete,
            cached=report.cached,
            reason=report.reason,
        )
        return report

    def _finished(self, park_id: str, task: asyncio.Task[AlertsReport]) -> None:
        """Release in-flight state even when the originating visitor has disconnected."""
        if self._pending.get(park_id) is task:
            self._pending.pop(park_id, None)
        if not task.cancelled():
            task.exception()

    async def _fetch(self, park_id: str) -> AlertsReport:
        """Fetch up to three pages within one deadline; preserve and label partial results, and sanitize failures."""
        name, code, source = PARKS[park_id]
        records: dict[str, NpsNotice] = {}
        total, offset, complete = 0, 0, False
        invalid_records = 0
        reason: str | None = None
        assert self._key is not None  # noqa: S101 - get() checks configuration before creating this task
        try:
            # ② Fixed HTTPS origin, header authentication, no redirects and no user text in API parameters.
            async with asyncio.timeout(NPS_TIMEOUT_SECONDS), self._make_http_client() as http:
                for _ in range(MAX_PAGES):
                    async with http.stream(
                        "GET",
                        NPS_ALERTS_URL,
                        params={"parkCode": code, "limit": PAGE_SIZE, "start": offset},
                        headers={"X-Api-Key": self._key.get_secret_value()},
                        follow_redirects=False,
                    ) as response:
                        if response.status_code != 200:
                            reason = (
                                "authentication_failed"
                                if response.status_code in (401, 403)
                                else "rate_limited"
                                if response.status_code == 429
                                else "upstream_error"
                            )
                            raise ValueError("NPS check failed")
                        body = bytearray()
                        async for part in response.aiter_bytes():
                            body.extend(part)
                            if len(body) > MAX_RESPONSE_BYTES:
                                raise ValueError("NPS response too large")
                    page = _Page.model_validate(json.loads(body))
                    if page.start != offset or (offset and page.total != total) or len(page.data) > page.total:
                        raise ValueError("Inconsistent NPS page")
                    total = page.total
                    if total and not page.data:
                        raise ValueError("Missing NPS records")
                    # Retain valid same-park records while clearly marking any omissions as incomplete.
                    for raw in page.data:
                        try:
                            item = NpsNotice.model_validate(raw)
                            if item.park_code != code:
                                raise ValueError("Unexpected park code")
                        except (ValidationError, ValueError):
                            invalid_records += 1
                            continue
                        try:
                            url = checked_source_url(item.url)
                            fallback = False
                        except ValueError:
                            url, fallback = source, True
                        records[item.id] = item.model_copy(update={"url": url, "source_is_fallback": fallback})
                    offset += len(page.data)
                    if offset >= total:
                        complete = len(records) == total and not invalid_records
                        break
        except (TimeoutError, httpx2.TimeoutException):
            reason = "timeout"
        except httpx2.RequestError:
            reason = "network_error"
        except Exception:
            reason = reason or "invalid_response"
        if invalid_records and reason is None:
            reason = "invalid_record"
        # ③ An incomplete or failed check is never represented as a successful empty list.
        status: Literal["found", "no_alerts", "unavailable"] = (
            "found" if records else "no_alerts" if complete and reason is None else "unavailable"
        )
        priorities = {"Park Closure": 0, "Danger": 1, "Caution": 2, "Information": 3}
        report = AlertsReport(
            status=status,
            park_id=park_id,
            park_name=name,
            source_url=source,
            total=total,
            notices=sorted(records.values(), key=lambda item: (priorities[item.category], item.title, item.id)),
            complete=complete and reason is None,
            fetched_at=datetime.now(UTC) if reason is None or records else None,
            reason=reason,
        )
        self._cache[park_id] = (self._clock() + (300 if report.complete else 60), report)
        return report
