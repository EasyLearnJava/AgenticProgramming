"""Activity describes recorded workflow outcomes without inventing model usage or hiding incomplete checks."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk
from structlog.testing import capture_logs

from nimbus.answer import AnswerEvent, AnswerStats, _from_message
from nimbus.axiom_query import Row
from nimbus.chat import stream_turn
from nimbus.config import Settings
from nimbus.observability import TIMELINE_EVENTS, TIMELINE_FIELDS, to_activity_line, to_activity_requests
from nimbus.parks import ParkKnowledge
from nimbus.travel.conditions import Section, checked, preparation
from tests.park_fakes import fixture_knowledge


def event(name: str, **fields: object) -> Row:
    """One synthetic public event, using the same fields the runtime records."""
    return {
        "_time": datetime.now(UTC).isoformat(),
        "requestId": "workflows-12345678",
        "event": name,
        **fields,
    }


def summary(*rows: Row) -> tuple[str, str, str]:
    """Project events through the same fields that Axiom is asked to return."""
    projected = [{key: value for key, value in row.items() if key in TIMELINE_FIELDS} for row in rows]
    item = to_activity_requests(["workflows-12345678"], projected)[0].summary
    return item.what, item.detail, item.tone


@pytest.mark.parametrize(
    ("fields", "label"),
    [
        ({"workflow": "intake", "tripForm": True}, "Trip details requested"),
        ({"cityTripIntake": True}, "City trip clarification"),
        ({"hotelDateIntake": True}, "Hotel date clarification"),
        ({"forecastHorizon": True}, "Forecast limit explained"),
    ],
)
def test_intake_events_identify_the_workflow_without_model_usage(fields: dict[str, object], label: str) -> None:
    what, detail, tone = summary(event("chat.done", toolCalls=0, ms=2, **fields))
    assert what == label
    assert "token" not in detail
    assert "tool call" not in detail
    assert tone == "ok"


@pytest.mark.parametrize(("decision", "label"), [("pause", "Pause travel"), ("adapt", "Adjust plans")])
def test_a_successful_conditions_decision_is_not_a_broken_request(decision: str, label: str) -> None:
    what, detail, tone = summary(
        event("travel.briefing", status=decision, failedSections=0, missingSections=0),
        event("chat.done", workflow="briefing", tripForm=False, toolCalls=0, ms=1200),
    )
    assert what == "Park trip briefing"
    assert label in detail
    assert "went wrong" not in detail
    assert "token" not in detail
    assert "tool call" not in detail
    assert tone == "idle"


def test_incomplete_conditions_remain_visible_and_warn() -> None:
    what, detail, tone = summary(
        event("travel.briefing", status="review", failedSections=1, missingSections=2),
        event("chat.done", workflow="briefing", tripForm=False, ms=30000),
    )
    assert what == "Park trip briefing"
    assert "2 checks incomplete" in detail
    assert tone == "warn"


def test_an_incomplete_plan_is_a_named_warning_even_when_no_section_threw() -> None:
    what, detail, tone = summary(
        event("travel.plan", status="partial", missingSections=1, failedSections=0),
        event("http.request", status=200, ms=12),
    )
    assert what == "Park trip plan"
    assert "1 section unavailable" in detail
    assert tone == "warn"


def test_optional_health_failure_is_visible_in_the_summary_tone() -> None:
    what, detail, tone = summary(
        event("health.check", check="kiwi-mcp", status="down", errorClass="UpstreamTimeoutError", ms=5000),
        event("health.done", status="ok", ms=5010),
    )
    assert what == "Health check"
    assert "Kiwi flight search tools" in detail
    assert tone == "warn"


def test_legacy_missing_token_usage_does_not_become_zero() -> None:
    _, missing, _ = summary(event("chat.done", toolCalls=1, ms=20))
    _, measured, _ = summary(event("chat.done", toolCalls=1, tokensIn=0, tokensOut=0, ms=20))
    assert "token usage unavailable" in missing
    assert "0 tokens in, 0 out" in measured
    assert "0 tokens in, 0 out" not in missing


def test_section_errors_are_projected_and_do_not_echo_unknown_names() -> None:
    assert "travel.section_error" in TIMELINE_EVENTS
    line = to_activity_line(event("travel.section_error", section="private user input", errorClass="private error"))
    assert line is not None
    assert line.tone == "bad"
    assert "private" not in line.what + line.detail


def test_a_section_timeout_emits_a_visible_failure_without_the_exception_message() -> None:
    async def slow() -> Section[str]:
        await asyncio.sleep(10)
        return Section("unreachable")

    async def run() -> Section[str]:
        return await checked(slow(), asyncio.get_running_loop().time() + 0.001, "NPS notices")

    with capture_logs() as logs:
        result = asyncio.run(run())
    assert result.failed
    failure = next(row for row in logs if row["event"] == "travel.section_error")
    assert failure["section"] == "NPS notices"
    assert failure["status"] == "failed"
    assert failure["errorClass"] == "TimeoutError"


@pytest.mark.parametrize("recorded", [False, True])
def test_new_model_events_preserve_unknown_usage_and_report_an_explicit_zero(recorded: bool) -> None:
    stats = AnswerStats(agent_started=True)
    chunk = AIMessageChunk(
        content="Synthetic answer",
        usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0} if recorded else None,
    )

    async def answer() -> AsyncGenerator[AnswerEvent]:
        for text in _from_message((chunk, {}), stats):
            yield text

    async def run() -> None:
        async for _ in stream_turn(answer(), "synthetic question", "test-12345678", stats, "synthetic"):
            pass

    with capture_logs() as logs:
        asyncio.run(run())
    done = next(row for row in logs if row["event"] == "chat.done")
    assert done["workflow"] == "agent"
    assert ("tokensIn" in done) is recorded
    assert ("tokensOut" in done) is recorded
    if recorded:
        assert done["tokensIn"] == done["tokensOut"] == 0


def test_undecided_park_clarification_does_not_claim_a_model_run(client: TestClient) -> None:
    with capture_logs() as logs:
        reply = client.post(
            "/api/chat", data={"question": "I mean either Zion or Yosemite; which park preparation guidance applies?"}
        )
    assert reply.status_code == 200
    done = next(row for row in logs if row["event"] == "chat.done")
    assert done["workflow"] == "intake"
    assert "tokensIn" not in done
    assert "tokensOut" not in done


@pytest.mark.parametrize(
    ("topic", "expected_statuses"),
    [
        ("visit hiking weather preparation water clothing", ["found"]),
        ("private-marker-7462", ["not_found", "found"]),
    ],
)
def test_preparation_logs_each_scoped_retrieval_for_activity(
    settings: Settings, topic: str, expected_statuses: list[str]
) -> None:
    knowledge = fixture_knowledge(settings.parks_index_path)
    with capture_logs() as logs:
        guidance = asyncio.run(preparation(knowledge, "zion", "zion", topic, date(2026, 11, 6)))
    assert guidance.data
    assert all(p.park_id == "zion" and "zion" in p.destination_ids for p in guidance.data)
    recorded = [row for row in logs if row["event"] == "knowledge.call"]
    assert [row["status"] for row in recorded] == expected_statuses
    assert recorded[-1]["count"] == len(guidance.data)
    assert all(row["ms"] >= 0 for row in recorded)
    assert all(row["tool"] == "search_park_guidance" for row in recorded)
    assert all(set(row) == {"event", "log_level", "tool", "status", "count", "ms"} for row in recorded)
    assert topic not in str(recorded)
    rows = [{"_time": datetime.now(UTC).isoformat(), "requestId": "workflows-12345678", **row} for row in recorded]
    what, detail, tone = summary(*rows, event("http.request", status=200, ms=10))
    assert what == "search_park_guidance"
    assert "found" in detail
    assert tone == "ok"


@pytest.mark.parametrize("missing", [True, False])
def test_unavailable_preparation_is_recorded_and_visible(tmp_path: Path, missing: bool) -> None:
    knowledge = None if missing else ParkKnowledge(tmp_path / "missing.json")
    with capture_logs() as logs:
        guidance = asyncio.run(preparation(knowledge, "zion", "zion", "private-topic", date(2026, 11, 6)))
    assert guidance.failed
    recorded = [row for row in logs if row["event"] == "knowledge.call"]
    assert len(recorded) == 1
    assert recorded[0]["status"] == "unavailable"
    assert recorded[0]["count"] == 0
    row = {"_time": datetime.now(UTC).isoformat(), "requestId": "workflows-12345678", **recorded[0]}
    line = to_activity_line(row)
    assert line is not None
    assert line.what == "search_park_guidance"
    assert line.tone == "bad"
    assert "private-topic" not in str(recorded)
