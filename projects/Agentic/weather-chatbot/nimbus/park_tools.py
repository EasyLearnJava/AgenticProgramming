"""
nimbus/park_tools.py: the park tools shared by all weather lanes. The model reads destination metadata and cited
guidance; the page receives a source record, never a fictitious weather request. Questions and passages stay out of
logs.
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Protocol, Self

import structlog
from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from nimbus.nps_alerts import PARKS, AlertsCallRecord, AlertsReport, NpsAlertsService, ParkId
from nimbus.park_ranking import VisitSeason, resolve_season
from nimbus.utils import checked_source_url, to_ms

PARK_TOOL_SECONDS = 6.0
STATUS_WORD = re.compile(r"[a-z_]{1,32}")
PARK_GUIDANCE_UNAVAILABLE = "The park guidance is unavailable right now. I can still check the weather."
_PARK_NAME = "(?:" + "|".join(re.escape(item[0]) for item in PARKS.values()) + ")(?: National Park)?"
_ALTERNATIVES = re.compile(
    rf"\b(?:either|undecided between|torn between)\s+({_PARK_NAME})\s+(?:or|and)\s+({_PARK_NAME})(?=\s*[;.!?]|\s*$)",
    re.I,
)


def undecided_park_query(question: str) -> str | None:
    """Recognize an explicit choice between parks. Keep comparisons and qualified place names in ordinary chat."""
    choice = _ALTERNATIVES.search(question)
    if not choice or not re.search(
        r"\b(?:which (?:park |destination )?(?:preparation |packing |safety )?(?:guidance|advice|guide)|"
        r"what should (?:I|we) (?:pack|wear|bring)|how should (?:I|we) prepare)\b",
        question,
        re.I,
    ):
        return None
    if re.search(
        r"\b(?:compare|comparison|both|each|differences?|versus|vs|better|instead|chose|chosen|"
        r"actually|decided|also|separately|forecast|hotels?|flights?|not either)\b",
        question,
        re.I,
    ):
        return None
    first, second = (name.casefold().removesuffix(" national park") for name in choice.groups())
    return f"{choice[1]} or {choice[2]}" if first != second else None


class KnowledgeService(Protocol):
    """The small service contract injected into the app and replaced by recordings in tests."""

    def resolve(self, query: str) -> dict[str, Any]:
        """Return verified destination candidates or an explicit coverage limitation."""
        ...

    async def search(
        self, destination_id: str, query: str, visit_date: date | None = None, *, season: VisitSeason | None = None
    ) -> dict[str, Any]:
        """Return a bounded collection of cited passages for a verified destination."""
        ...


def _without_additional_properties(schema: dict[str, Any]) -> None:
    """Keep Gemini's function schema compatible while Pydantic still refuses unknown input fields."""
    schema.pop("additionalProperties", None)


class _ParkInput(BaseModel):
    """Validated park-tool input with the same Gemini schema convention as the existing weather tools."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra=_without_additional_properties)


class ResolveDestinationInput(_ParkInput):
    """A park or trail name, bounded and stripped before lookup."""

    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] = Field(
        description="The park or trail name, including its park when known, such as 'Zion Narrows'."
    )


class SearchParkGuidanceInput(_ParkInput):
    """A verified destination ID and a preparation question, with the intended visit's date when known."""

    destination_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,100}$")] = Field(
        description="An exact destination ID returned by resolve_destination."
    )
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] = Field(
        description="The user's weather-related preparation question, with the activity or equipment topic."
    )
    visit_date: date | None = Field(default=None, description="The intended visit date as YYYY-MM-DD, when known.")
    season: VisitSeason | None = Field(
        default=None,
        description="The explicitly requested season, when no exact visit date is known. Never invent a date.",
    )

    @model_validator(mode="after")
    def consistent_season(self) -> Self:
        """Reject contradictory explicit date and season filters before calling either retriever."""
        resolve_season(self.query, self.visit_date, self.season)
        return self


class ParkAlertsInput(_ParkInput):
    """A supported park ID from this turn's destination resolution, never a URL or visitor question."""

    park_id: ParkId = Field(description="The park_id returned by resolve_destination: zion, grand-canyon or yosemite.")


def alerts_context(report: AlertsReport) -> tuple[str, tuple[str, ...]]:
    """Bound model context separately from the page's full report, and retain exactly the URLs the model saw."""
    # ③ API completeness and model-context completeness are independent; only exposed sources support citations.
    output = report.model_dump(mode="json", exclude={"notices"})
    notices: list[dict[str, Any]] = []
    budget = 0
    truncated = False
    for item in report.notices[:8]:
        entry = item.model_dump()
        entry["title"], entry["description"] = item.title[:300], item.description[:1500]
        entry["text_truncated"] = len(item.title) > 300 or len(item.description) > 1500
        size = len(json.dumps(entry, ensure_ascii=False))
        if budget + size > 12000:
            break
        budget += size
        truncated = truncated or entry["text_truncated"]
        notices.append(entry)
    output["notices"] = notices
    output["context_limited"] = truncated or len(notices) < len(report.notices)
    sources = (report.source_url, *(str(item["url"]) for item in notices))
    return json.dumps(output, ensure_ascii=False), tuple(dict.fromkeys(sources))


def make_alert_tools(service: NpsAlertsService) -> list[StructuredTool]:
    """Expose official park-level notices independently of stored preparation guidance and weather transports."""

    async def alerts(park_id: ParkId) -> tuple[str, AlertsCallRecord]:
        """Fetch a bounded report or an explicit missing-key/unavailable status, preserving its provenance."""
        started = time.perf_counter()
        params = ParkAlertsInput(park_id=park_id)
        report = await service.get(params.park_id)
        content, sources = alerts_context(report)
        return content, AlertsCallRecord(to_ms(time.perf_counter() - started), report, sources)

    return [
        StructuredTool.from_function(
            coroutine=alerts,
            name="get_park_alerts",
            args_schema=ParkAlertsInput,
            description=(
                "Check recently published official NPS park-level notices after resolve_destination. "
                "Returns notices, source links, indexing/fetch timestamps and completeness; no_alerts means "
                "no notices returned, never that a trail is open or safe. Missing configuration and outages "
                "are explicit. Do not use stored guides to infer current closures."
            ),
            response_format="content_and_artifact",
            handle_tool_error=True,
        )
    ]


@dataclass(frozen=True)
class KnowledgeSource:
    """A source's public provenance, suitable for the page's escaped link and date labels."""

    title: str
    url: str
    updated_at: str | None
    fetched_at: str | None


@dataclass(frozen=True)
class KnowledgeCallRecord:
    """A local knowledge operation's duration, index version, result summary and cited documents."""

    ms: int
    summary: str
    index_version: str
    sources: tuple[KnowledgeSource, ...] = ()
    retrieval_mode: str = "registry"


def to_knowledge_sources(output: dict[str, Any]) -> tuple[KnowledgeSource, ...]:
    """Unique approved HTTPS source links; malformed or foreign addresses never become links in the source card."""
    sources: dict[str, KnowledgeSource] = {}
    for passage in output.get("passages", []):
        if not isinstance(passage, dict):
            continue
        url = passage.get("source_url")
        if not isinstance(url, str):
            continue
        try:
            url = checked_source_url(url)
        except ValueError:
            continue
        sources[url] = KnowledgeSource(
            str(passage.get("title", "National Park Service")),
            url,
            str(passage["source_updated_at"]) if passage.get("source_updated_at") else None,
            str(passage["fetched_at"]) if passage.get("fetched_at") else None,
        )
    return tuple(sources.values())


async def _run_knowledge(name: str, run: Callable[[], Awaitable[dict[str, Any]]]) -> tuple[str, KnowledgeCallRecord]:
    """Run within a short deadline; log counts and versions only, and return sanitized failures to the agent."""
    # ① The outer answer's cancellation still propagates; only a tool's own failure becomes a recoverable tool error.
    started = time.perf_counter()
    log = structlog.get_logger()
    try:
        async with asyncio.timeout(PARK_TOOL_SECONDS):
            output = await run()
    except Exception as error:
        log.info(
            "knowledge.call",
            tool=name,
            status="failed",
            ms=to_ms(time.perf_counter() - started),
            errorClass=type(error).__name__,
        )
        raise ToolException(PARK_GUIDANCE_UNAVAILABLE) from None
    # ② The source text is the tool's content, but its provenance is also kept separately for the source card.
    ms = to_ms(time.perf_counter() - started)
    sources = to_knowledge_sources(output)
    version = str(output.get("index_version", "unavailable"))
    status = str(output.get("status", "unavailable"))
    count = len(output.get("passages", []))
    summary = f"{count} guidance passages" if name == "search_park_guidance" else f"Destination: {status}"
    if status in {"unavailable", "not_found", "unsupported", "ambiguous"}:
        summary = f"Park guidance: {status.replace('_', ' ')}"
    # A search says which retrieval ran, so keywords-only after a hosted failure shows in the logs, not only in traces.
    retrieval = (
        {
            "retrievalMode": to_status_word(output.get("retrieval_mode")),
            "keywordStatus": to_status_word(output.get("keyword_status")),
            "semanticStatus": to_status_word(output.get("semantic_status")),
            "rerankStatus": to_status_word(output.get("rerank_status")),
        }
        if name == "search_park_guidance"
        else {}
    )
    log.info(
        "knowledge.call",
        tool=name,
        status="failed" if status == "unavailable" else status,
        ms=ms,
        indexVersion=version,
        sourceCount=len(sources),
        **retrieval,
    )
    record = KnowledgeCallRecord(ms, summary, version, sources, str(output.get("retrieval_mode", "registry")))
    # The trace ID links the Playground to its trace; the model needs none, and could repeat it in an answer.
    content = {key: value for key, value in output.items() if key != "trace_id"}
    return json.dumps(content, ensure_ascii=False), record


def to_status_word(value: object) -> str:
    """A fixed status word as the retrieval code wrote it ("hybrid", "index_mismatch"); anything else, "unknown"."""
    return value if isinstance(value, str) and STATUS_WORD.fullmatch(value) else "unknown"


async def resolve_park(knowledge: KnowledgeService, query: str) -> tuple[str, KnowledgeCallRecord]:
    """Resolve the full place name using the same input, timeout, artifact and logs for both chat paths."""
    params = ResolveDestinationInput(query=query)

    async def run() -> dict[str, Any]:
        """Return the registry's checked candidates."""
        return knowledge.resolve(params.query)

    return await _run_knowledge("resolve_destination", run)


def make_park_tools(knowledge: KnowledgeService) -> list[StructuredTool]:
    """Two local knowledge tools, composed with any weather lane without changing the weather or MCP catalog."""

    async def resolve(query: str) -> tuple[str, KnowledgeCallRecord]:
        """Resolve a park or trail name to its approved forecast reference and document identity."""
        return await resolve_park(knowledge, query)

    async def search(
        destination_id: str, query: str, visit_date: date | None = None, season: VisitSeason | None = None
    ) -> tuple[str, KnowledgeCallRecord]:
        """Find supporting passages, bounded by destination and date."""
        params = SearchParkGuidanceInput(
            destination_id=destination_id, query=query, visit_date=visit_date, season=season
        )

        async def run() -> dict[str, Any]:
            """Retrieve guidance using validated inputs."""
            return await knowledge.search(params.destination_id, params.query, params.visit_date, season=params.season)

        return await _run_knowledge("search_park_guidance", run)

    return [
        StructuredTool.from_function(
            coroutine=resolve,
            name="resolve_destination",
            description=(
                "Resolve a supported park or trail before fetching its weather or guidance. Coverage: Zion, Grand "
                "Canyon, Yosemite, and selected trails. Use returned coordinates and forecast_reference; ask for "
                "clarification if ambiguous. Unsupported means this guide collection has no matching destination."
            ),
            args_schema=ResolveDestinationInput,
            response_format="content_and_artifact",
            handle_tool_error=True,
        ),
        StructuredTool.from_function(
            coroutine=search,
            name="search_park_guidance",
            description=(
                "Search official preparation guidance for a destination_id returned by resolve_destination. "
                "Include visit_date when known, or season when only a season was requested; never invent a date. "
                "Returns cited passages and source dates, not live closures, alerts "
                "or river conditions. Use for weather-related clothing, equipment and seasonal preparation."
            ),
            args_schema=SearchParkGuidanceInput,
            response_format="content_and_artifact",
            handle_tool_error=True,
        ),
    ]
