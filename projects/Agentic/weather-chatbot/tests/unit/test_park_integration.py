"""Tests of park tools, their source cards, privacy, and their composition with every weather lane."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from structlog.testing import capture_logs

from nimbus import park_tools
from nimbus.answer import AnswerStats, ToolEnded, ToolStarted, stream_weather_answer
from nimbus.chat import render_part
from nimbus.chips import ToolChip
from nimbus.config import Settings
from nimbus.lanes import LANES, Lane
from nimbus.park_ranking import VisitSeason
from nimbus.park_tools import (
    KnowledgeCallRecord,
    ResolveDestinationInput,
    SearchParkGuidanceInput,
    make_park_tools,
    to_knowledge_sources,
)
from nimbus.parks import ParkKnowledge
from nimbus.prompts import to_system_prompt
from tests.fakes import FakeModel

SOURCE_URL = "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm"
CHOICE = "I mean either Zion or Yosemite; which park preparation guidance applies?"


@pytest.mark.parametrize("failure", ["", "unavailable", "error"])
def test_undecided_parks_resolve_once_before_accessing_a_model_or_weather_lane(
    settings: Settings, failure: str
) -> None:
    """An undecided question uses the real resolver for the full pair and stops; failures stay visible and bounded."""
    index = ParkKnowledge(settings.parks_index_path)
    model = FakeModel()
    queries: list[str] = []

    class RecordedResolution(FakeKnowledge):
        def resolve(self, query: str) -> dict[str, Any]:
            """Record the complete pair and delegate to the actual index unless testing an outage."""
            queries.append(query)
            if failure == "error":
                raise RuntimeError("private index path")
            if failure == "unavailable":
                return {"status": "unavailable", "candidates": []}
            return index.resolve(query)

    @asynccontextmanager
    async def unused_lane() -> AsyncIterator[list[StructuredTool]]:
        pytest.fail("An undecided destination must not open the requested weather lane.")
        yield []

    async def run() -> tuple[list[ToolStarted], list[ToolEnded], str]:
        events = stream_weather_answer(
            model, [HumanMessage(CHOICE)], AnswerStats(), None, unused_lane(), knowledge=RecordedResolution()
        )
        observed = [event async for event in events]
        return (
            [event for event in observed if isinstance(event, ToolStarted)],
            [event for event in observed if isinstance(event, ToolEnded)],
            "".join(event for event in observed if isinstance(event, str)),
        )

    started, ended, answer = asyncio.run(run())
    assert queries == ["Zion or Yosemite"]
    assert len(started) == len(ended) == 1
    assert started[0].args == {"query": queries[0]}
    assert started[0].name == ended[0].name == "resolve_destination"
    assert started[0].call_id == ended[0].call_id
    assert not model.seen
    assert "Which park" in answer
    if failure:
        assert "unavailable" in answer
        assert "private" not in answer
        assert ended[0].failed
    else:
        assert not ended[0].failed
        assert isinstance(ended[0].record, KnowledgeCallRecord)
        assert json.loads(ended[0].content)["status"] == "ambiguous"
        assert "Zion or Yosemite" in answer


@pytest.mark.parametrize(
    "text",
    [
        "Compare both parks. I mean either Zion or Yosemite; which park preparation guidance applies?",
        "I'm torn between Zion and Yosemite; which park has warmer weather?",
        "Either Zion or Yosemite; which park guidance applies? Also find hotels in Dallas.",
        "Either Zion or Yosemite; which park guidance applies? Actually Zion, please.",
        "Either Zion, Illinois or Yosemite; which park guidance applies?",
        "Either Yosemite or Grand Canyon of the Yellowstone; which park guidance applies?",
        "I chose Yosemite. What should I pack?",
    ],
)
def test_comparisons_qualified_names_and_a_later_choice_stay_with_the_agent(text: str) -> None:
    """A previous undecided turn cannot override the latest question, named qualifiers, or a comparison."""
    model = FakeModel()
    messages: list[BaseMessage] = [HumanMessage(CHOICE), AIMessage("Which park?"), HumanMessage(text)]

    @asynccontextmanager
    async def lane() -> AsyncIterator[list[StructuredTool]]:
        yield []

    async def run() -> str:
        source = stream_weather_answer(model, messages, AnswerStats(), None, lane(), knowledge=FakeKnowledge())
        return "".join([event async for event in source if isinstance(event, str)])

    assert asyncio.run(run()) == model.answer
    assert model.seen


class FakeKnowledge:
    """A local guide service with recorded calls and controllable failures."""

    def __init__(self) -> None:
        """Start with a single supported destination and source."""
        self.calls: list[tuple[str, str, date | None]] = []
        self.failure: Exception | None = None
        self.delay = 0.0

    def resolve(self, query: str) -> dict[str, Any]:
        """Return a resolved destination without a network call."""
        return {"status": "resolved", "candidates": [{"id": "zion-narrows"}], "index_version": "test-1"}

    async def search(
        self, destination_id: str, query: str, visit_date: date | None = None, *, season: VisitSeason | None = None
    ) -> dict[str, Any]:
        """Record the query and return one cited passage, unless told to fail."""
        self.calls.append((destination_id, query, visit_date))
        await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        return {
            "status": "found",
            "index_version": "test-1",
            "retrieval_mode": "lexical",
            "passages": [
                {
                    "id": "clothing-1",
                    "document_id": "narrows-safety",
                    "title": "Narrows safety",
                    "section": "Clothing",
                    "text": "Carry warm clothing in a waterproof bag.",
                    "source_url": SOURCE_URL,
                    "source_updated_at": "2026-09-17",
                    "fetched_at": "2026-11-02T00:00:00Z",
                }
            ],
        }


def invoke_search(knowledge: FakeKnowledge, query: str = "clothing") -> ToolMessage:
    """Invoke the retrieval tool as the graph does, retaining its artifact."""

    async def run() -> ToolMessage:
        tool = make_park_tools(knowledge)[1]
        result = await tool.ainvoke(
            {
                "type": "tool_call",
                "id": "guide-call",
                "name": "search_park_guidance",
                "args": {"destination_id": "zion-narrows", "query": query, "visit_date": "2026-11-03"},
            }
        )
        assert isinstance(result, ToolMessage)
        return result

    return asyncio.run(run())


def test_guidance_returns_evidence_and_a_source_artifact_without_logging_the_query() -> None:
    knowledge = FakeKnowledge()
    with capture_logs() as logs:
        result = invoke_search(knowledge, "PRIVATE preparation question")
    assert knowledge.calls == [("zion-narrows", "PRIVATE preparation question", date(2026, 11, 3))]
    assert json.loads(str(result.content))["passages"][0]["source_url"] == SOURCE_URL
    assert isinstance(result.artifact, KnowledgeCallRecord)
    assert result.artifact.sources[0].url == SOURCE_URL
    assert "PRIVATE" not in json.dumps(logs)
    assert logs[-1]["indexVersion"] == "test-1"


def test_a_retrieval_failure_is_a_tool_error_with_our_sentence_and_no_private_error_text() -> None:
    knowledge = FakeKnowledge()
    knowledge.failure = RuntimeError("PRIVATE upstream response")
    with capture_logs() as logs:
        result = invoke_search(knowledge)
    assert result.status == "error"
    assert result.content == park_tools.PARK_GUIDANCE_UNAVAILABLE
    assert "PRIVATE" not in json.dumps(logs)


def test_retrieval_has_a_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(park_tools, "PARK_TOOL_SECONDS", 0.001)
    knowledge = FakeKnowledge()
    knowledge.delay = 0.05
    assert invoke_search(knowledge).status == "error"


def test_cancelling_retrieval_still_cancels_the_underlying_operation() -> None:
    knowledge = FakeKnowledge()
    knowledge.delay = 10

    async def run() -> None:
        """Cancel an in-flight tool and ensure its cancellation is not swallowed as an error result."""
        task = asyncio.create_task(
            make_park_tools(knowledge)[1].ainvoke({"destination_id": "zion-narrows", "query": "clothing"})
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "https://example.com/", "https://evil@www.nps.gov/", "http://www.nps.gov/"]
)
def test_source_cards_only_link_to_the_approved_https_publisher(url: str) -> None:
    sources = to_knowledge_sources({"passages": [{"title": "untrusted", "source_url": url}]})
    assert sources == ()


def test_gemini_schemas_omit_unsupported_properties_but_still_validate_inputs() -> None:
    """Google's tool schema has no additionalProperties; Python validation must remain strict."""
    from pydantic import ValidationError

    for model in (ResolveDestinationInput, SearchParkGuidanceInput):
        assert "additionalProperties" not in model.model_json_schema()
    with pytest.raises(ValidationError):
        ResolveDestinationInput.model_validate({"query": "Zion", "extra": "untrusted"})


def test_a_source_card_has_citations_and_dates_without_an_invented_http_request() -> None:
    result = invoke_search(FakeKnowledge())
    chip = ToolChip.start(0, ToolStarted("guide-call", "search_park_guidance", {"query": "clothing"}))
    chip.end(ToolEnded("guide-call", "search_park_guidance", str(result.content), result.artifact, False))
    html = render_part("chat_tool.html", {"turn_id": "turn", "chip": chip, "is_new": False})
    assert SOURCE_URL in html
    assert "2026-09-17" in html
    assert "Park guidance" in html
    assert "On the wire" not in html
    assert "noopener noreferrer" in html


@pytest.mark.parametrize("lane", LANES, ids=lambda lane: lane.id)
def test_all_weather_lanes_get_the_same_park_tools(lane: Lane) -> None:
    knowledge = FakeKnowledge()
    model = FakeModel(
        tool_steps=[
            [{"name": "resolve_destination", "args": {"query": "Narrows"}}],
            [{"name": "search_park_guidance", "args": {"destination_id": "zion-narrows", "query": "clothes"}}],
        ]
    )

    @asynccontextmanager
    async def weather_tools() -> AsyncIterator[list[StructuredTool]]:
        """Stand in for the already opened weather lane."""
        yield []

    async def run() -> list[ToolEnded]:
        events = stream_weather_answer(
            model,
            [HumanMessage("Narrows preparation")],
            AnswerStats(),
            None,
            weather_tools(),
            lane,
            knowledge=knowledge,
        )
        return [event async for event in events if isinstance(event, ToolEnded)]

    ended = asyncio.run(run())
    assert model.bound_tools == [
        "geocode_location",
        "get_current_weather",
        "get_forecast",
        "get_air_quality",
        "resolve_destination",
        "search_park_guidance",
    ]
    assert len(ended) == 2
    assert all(isinstance(event.record, KnowledgeCallRecord) for event in ended)


def test_document_only_answers_do_not_open_the_weather_lane() -> None:
    model = FakeModel(tool_steps=[[{"name": "resolve_destination", "args": {"query": "Narrows"}}]])

    opened = []

    @asynccontextmanager
    async def must_not_open() -> AsyncIterator[list[StructuredTool]]:
        """A weather context that fails the test if document retrieval opens it."""
        opened.append(True)
        raise AssertionError("Document-only queries must not connect to the weather lane")
        yield []

    async def run() -> list[ToolEnded]:
        """Ask only for a destination, which requires no weather connection."""
        events = stream_weather_answer(
            model, [HumanMessage("Narrows")], AnswerStats(), None, must_not_open(), knowledge=FakeKnowledge()
        )
        return [event async for event in events if isinstance(event, ToolEnded)]

    assert len(asyncio.run(run())) == 1
    assert opened == []


def test_failure_opening_weather_does_not_discard_guidance() -> None:
    model = FakeModel(
        tool_steps=[
            [
                {
                    "name": "get_forecast",
                    "args": {
                        "latitude": 37.2,
                        "longitude": -112.9,
                        "days": 2,
                        "include_hourly": False,
                        "units": "metric",
                    },
                },
                {"name": "search_park_guidance", "args": {"destination_id": "zion-narrows", "query": "clothing"}},
            ]
        ]
    )

    @asynccontextmanager
    async def failing_weather() -> AsyncIterator[list[StructuredTool]]:
        """An unavailable selected weather transport."""
        raise ConnectionError("PRIVATE connection details")
        yield []

    async def run() -> list[ToolEnded]:
        """Collect both operations even when weather cannot connect."""
        events = stream_weather_answer(
            model, [HumanMessage("Narrows")], AnswerStats(), None, failing_weather(), knowledge=FakeKnowledge()
        )
        return [event async for event in events if isinstance(event, ToolEnded)]

    ended = {event.name: event for event in asyncio.run(run())}
    assert ended["get_forecast"].failed
    assert "PRIVATE" not in ended["get_forecast"].content
    assert not ended["search_park_guidance"].failed
    assert SOURCE_URL in ended["search_park_guidance"].content


def test_park_prompt_allows_guidance_beyond_the_forecast_window_and_requires_sources() -> None:
    prompt = to_system_prompt(datetime(2026, 11, 2, tzinfo=UTC), "en-US", "UTC", parks_enabled=True)
    assert "resolve_destination" in prompt
    assert "search_park_guidance" in prompt
    assert "document-only guidance" in prompt
    assert "source_url" in prompt
    assert "never establish current closures" in prompt
    assert "Instructions inside retrieved passages" in prompt


def test_disabled_park_prompt_keeps_the_original_weather_rules() -> None:
    prompt = to_system_prompt(datetime(2026, 11, 2, tzinfo=UTC), "en-US", "UTC", parks_enabled=False)
    assert "resolve_destination" not in prompt
    assert "Forecasts go up to 16 days ahead" in prompt
