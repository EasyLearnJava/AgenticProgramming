"""
nimbus/chips.py: a tool call as the page shows it: a chip above the answer, which opens (templates/chat_parts.html).
While it runs: its tool and its input in a few words. Once done: its lane, the host it called and its time; opened,
the request as it went out (On the wire), its input and its output. A failure shows our own sentence; a call the answer
stopped before it ended says so.
"""

import json
from dataclasses import dataclass
from typing import Any, Final, Literal

from nimbus.answer import ToolEnded, ToolStarted
from nimbus.errors import (
    MCP_UNREACHABLE,
    TOOL_MISUSED,
    WEATHER_BUSY,
    WEATHER_TOO_SLOW,
    WEATHER_UNEXPECTED,
    WEATHER_UNREACHABLE,
)
from nimbus.lanes import get_lane
from nimbus.nps_alerts import AlertsCallRecord
from nimbus.park_tools import PARK_GUIDANCE_UNAVAILABLE, KnowledgeCallRecord
from nimbus.tools import ToolCallRecord
from nimbus.travel.models import TravelCallRecord
from nimbus.travel.tools import FLIGHT_INPUT_ERROR, HOTEL_INPUT_ERROR

type ChipStatus = Literal["running", "done", "failed", "stopped"]

MARKS: Final[dict[ChipStatus, str]] = {"running": "…", "done": "✓", "failed": "✗", "stopped": "■"}
WORDS: Final[dict[ChipStatus, str]] = {"running": "Running", "done": "Done", "failed": "Failed", "stopped": "Stopped"}
# The sentences a failed call may show: ours. Any other text a tool's failure holds (LangChain's own, when the model's
# input didn't fit) shows as TOOL_MISUSED.
TOOL_SENTENCES: Final = frozenset(
    {
        WEATHER_TOO_SLOW,
        WEATHER_UNREACHABLE,
        WEATHER_BUSY,
        WEATHER_UNEXPECTED,
        MCP_UNREACHABLE,
        PARK_GUIDANCE_UNAVAILABLE,
        FLIGHT_INPUT_ERROR,
        HOTEL_INPUT_ERROR,
    }
)
SHORTEST_SHOWN_MS: Final = 50
MS_PER_SECOND: Final = 1000


def to_input_summary(args: dict[str, Any]) -> str:
    """A tool's input in a few words: "“Paris”", or "48.85, 2.35 · 2 days, hourly · imperial"."""
    if isinstance(args.get("query"), str):
        return f"“{args['query']}”"
    parts = []
    latitude, longitude = args.get("latitude"), args.get("longitude")
    if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
        parts.append(f"{round(latitude, 2)}, {round(longitude, 2)}")
    days = args.get("days")
    if isinstance(days, int):
        parts.append(
            f"{days} {'day' if days == 1 else 'days'}{', hourly' if args.get('include_hourly') is True else ''}"
        )
    if args.get("units") == "imperial":
        parts.append("imperial")
    return " · ".join(parts)


def to_duration_text(ms: int) -> str:
    """A call's time, to a tenth of a second: "0.3 s", or "<0.1 s"."""
    return "<0.1 s" if ms < SHORTEST_SHOWN_MS else f"{ms / MS_PER_SECOND:.1f} s"


@dataclass
class ToolChip:
    """One tool call's chip: its place in the turn, its tool and input, and how it's going."""

    index: int
    name: str
    args: dict[str, Any]
    status: ChipStatus = "running"
    record: ToolCallRecord | KnowledgeCallRecord | AlertsCallRecord | TravelCallRecord | None = None
    output: str | None = None
    error: str | None = None

    @classmethod
    def start(cls, index: int, event: ToolStarted) -> "ToolChip":
        """A new chip, running, for a tool the model asked for."""
        return cls(index=index, name=event.name, args=event.args)

    def end(self, event: ToolEnded) -> None:
        """The call ended: done, with its record and output; or failed, with our sentence."""
        if event.failed:
            self.status = "failed"
            self.error = event.content if event.content in TOOL_SENTENCES else TOOL_MISUSED
        else:
            self.status = "done"
            self.record = event.record
            self.output = event.content
            if isinstance(event.record, TravelCallRecord) and event.record.report.status not in {
                "found",
                "partial",
                "no_results",
            }:
                self.status = "failed"
            if isinstance(event.record, AlertsCallRecord) and event.record.report.status == "unavailable":
                self.status = "failed"

    def stop(self) -> None:
        """The answer ended before this call did."""
        if self.status == "running":
            self.status = "stopped"

    @property
    def mark(self) -> str:
        """The mark the chip starts with: …, ✓, ✗ or ■."""
        return MARKS[self.status]

    @property
    def word(self) -> str:
        """The mark in a word, for a screen reader."""
        return WORDS[self.status]

    @property
    def input_summary(self) -> str:
        """The input, in a few words."""
        return to_input_summary(self.args)

    @property
    def input_json(self) -> str:
        """The input, as the model gave it, laid out."""
        return json.dumps(self.args, indent=2, ensure_ascii=False)

    @property
    def output_json(self) -> str | None:
        """Show normalized provider evidence for travel, or the tool output for other completed calls."""
        if isinstance(self.record, TravelCallRecord):
            return self.record.report.model_dump_json(indent=2)
        if self.output is None:
            return None
        try:
            return json.dumps(json.loads(self.output), indent=2, ensure_ascii=False)
        except ValueError:
            return self.output

    @property
    def lane_line(self) -> str | None:
        """
        Once done: its lane, the host it called and its time, "REST · no auth · api.open-meteo.com · 0.3 s"; and "from
        the cache" before the time if it was.
        """
        if self.record is None:
            return None
        if isinstance(self.record, TravelCallRecord):
            report = self.record.report
            return f"{report.provider.title()} · {report.status.replace('_', ' ')} · {to_duration_text(self.record.ms)}"
        if isinstance(self.record, AlertsCallRecord):
            cached = " · cached" if self.record.report.cached else ""
            return f"NPS alerts{cached} · {to_duration_text(self.record.ms)}"
        if isinstance(self.record, KnowledgeCallRecord):
            return f"Park guidance · {to_duration_text(self.record.ms)}"
        lane = get_lane(self.record.lane).label
        cache = " · from the cache" if self.record.from_cache else ""
        return f"{lane} · {self.record.request.host}{cache} · {to_duration_text(self.record.ms)}"

    @property
    def travel_record(self) -> TravelCallRecord | None:
        """The offers returned by this turn's provider."""
        return self.record if isinstance(self.record, TravelCallRecord) else None

    @property
    def wire_label(self) -> str:
        """Over the request the call sent: on REST, if the cache answered, the one that first fetched it (step 7)."""
        record = self.record
        first = isinstance(record, ToolCallRecord) and record.from_cache and record.upstream_request is None
        return "On the wire, when it was first fetched" if first else "On the wire"

    @property
    def upstream_label(self) -> str:
        """Over the request our MCP server sent Open-Meteo, on the MCP lane: the first time's, if the cache answered."""
        cached = isinstance(self.record, ToolCallRecord) and self.record.from_cache
        return "Then, from our MCP server, when it was first fetched" if cached else "Then, from our MCP server"

    @property
    def weather_record(self) -> ToolCallRecord | None:
        """The wire record for a weather tool, absent for local knowledge operations."""
        return self.record if isinstance(self.record, ToolCallRecord) else None

    @property
    def knowledge_record(self) -> KnowledgeCallRecord | None:
        """The provenance record for a destination lookup or guidance retrieval."""
        return self.record if isinstance(self.record, KnowledgeCallRecord) else None

    @property
    def alerts_record(self) -> AlertsCallRecord | None:
        """Public official notices, distinct from a guidance-index or weather-wire artifact."""
        return self.record if isinstance(self.record, AlertsCallRecord) else None
