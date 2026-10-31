"""
tests/unit/test_agent.py: the agent as our own graph: a model node and a tools node; at most 5 calls to the model, the
last with its tools turned off, so every answer ends in words; each tool call a task of its own; and the time limits:
a tool call's 8 s, and 10 s for the model's first words at each call.
"""

import asyncio
from typing import Any

import httpx2
import pytest
from langchain_core.messages import HumanMessage

from nimbus import agent, tools
from nimbus.agent import make_agent
from nimbus.answer import AnswerEvent, AnswerStats, ToolEnded, ToolStarted, stream_weather_answer
from nimbus.errors import WEATHER_TOO_SLOW, AnswerTimeoutError
from tests.fakes import ANSWER, PARIS_STEPS, FakeModel, OpenMeteoRecordings

GEOCODE_PARIS: list[dict[str, Any]] = [{"name": "geocode_location", "args": {"query": "Paris"}}]
FORECAST = {"latitude": 48.85, "longitude": 2.35, "days": 2, "include_hourly": False, "units": "metric"}


def collect(model: FakeModel, recordings: OpenMeteoRecordings | None = None) -> list[AnswerEvent]:
    """Every event of an answer, with Open-Meteo played back."""

    async def run() -> list[AnswerEvent]:
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(recordings or OpenMeteoRecordings()))
        events = stream_weather_answer(model, [HumanMessage("Hi")], AnswerStats(), None, http)
        return [event async for event in events]

    return asyncio.run(run())


def text(events: list[AnswerEvent]) -> str:
    """An answer's words, without its tool calls."""
    return "".join(event for event in events if isinstance(event, str))


def test_the_graph_is_a_model_node_and_a_tools_node_in_a_loop() -> None:
    graph = make_agent(FakeModel(), []).get_graph()
    assert set(graph.nodes) == {"__start__", "model", "tools", "__end__"}
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert edges == {("__start__", "model"), ("model", "tools"), ("model", "__end__"), ("tools", "model")}


def test_an_answer_that_needs_no_tool_takes_one_call_with_the_tools_on() -> None:
    model = FakeModel()
    assert text(collect(model)) == ANSWER
    assert model.tool_choices == ["auto"]


def test_the_fifth_call_to_the_model_has_its_tools_turned_off_and_answers_in_words() -> None:
    # A model that would ask for a tool forever: the fifth call can't, so the answer still ends in words.
    model = FakeModel(tool_steps=[GEOCODE_PARIS] * 10)
    events = collect(model)
    assert model.tool_choices == ["auto", "auto", "auto", "auto", "none"]
    assert len([event for event in events if isinstance(event, ToolStarted)]) == 4
    assert text(events) == ANSWER


def test_each_tool_call_of_a_round_is_a_task_of_its_own() -> None:
    both = [
        {"name": "get_forecast", "args": FORECAST},
        {"name": "get_air_quality", "args": {"latitude": 48.85, "longitude": 2.35}},
    ]
    events = collect(FakeModel(tool_steps=[both]))
    kinds = [(type(event).__name__, event.name) for event in events if not isinstance(event, str)]
    assert kinds[:2] == [("ToolStarted", "get_forecast"), ("ToolStarted", "get_air_quality")]
    assert sorted(kinds[2:]) == [("ToolEnded", "get_air_quality"), ("ToolEnded", "get_forecast")]


def test_a_tool_call_past_its_time_limit_fails_as_too_slow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "TOOL_TIMEOUT_SECONDS", 0.05)
    events = collect(FakeModel(tool_steps=PARIS_STEPS), OpenMeteoRecordings(delay=0.2))
    [geocode] = [event for event in events if isinstance(event, ToolEnded) and event.name == "geocode_location"]
    assert (geocode.failed, geocode.content) == (True, WEATHER_TOO_SLOW)


def test_a_call_whose_first_words_come_late_ends_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent, "MODEL_FIRST_CHUNK_SECONDS", 0.05)
    with pytest.raises(AnswerTimeoutError):
        collect(FakeModel(delay=0.2))


def test_the_limits_are_5_calls_8_seconds_a_tool_and_10_for_the_first_words() -> None:
    # In numbers: a test that took them from the constants would follow any change to them.
    from nimbus.constants import MAX_MODEL_CALLS, MODEL_FIRST_CHUNK_SECONDS, TOOL_TIMEOUT_SECONDS

    assert (MAX_MODEL_CALLS, TOOL_TIMEOUT_SECONDS, MODEL_FIRST_CHUNK_SECONDS) == (5, 8, 10)
