"""
tests/unit/test_answer.py: the answer: the agent's run as events, each tool call as it starts and ends and the model's
words as it writes them; the tokens of every call to the model counted; a failed tool call read by the model as our
sentence; at most 5 calls to the model; every failure turned into one of our errors; a cap on its time; and the
finished answer's Markdown, made into HTML with no raw HTML, no picture, and no link that could run code.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import httpx2
import pytest
from langchain_core.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)
from langchain_core.exceptions import ModelTimeoutError as LangChainModelTimeoutError
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_google_genai.chat_models import GoogleInvalidRequestError
from langsmith import Client

from nimbus import answer
from nimbus.agent import make_agent
from nimbus.answer import (
    LINK_REL,
    AnswerEvent,
    AnswerStats,
    ToolEnded,
    ToolStarted,
    render_answer,
    stream_answer,
    stream_weather_answer,
)
from nimbus.errors import WEATHER_UNREACHABLE, AnswerTimeoutError, ConfigError, ModelBusyError, ModelFailedError
from nimbus.model import Tracer
from nimbus.tools import ToolCallRecord
from tests.fakes import ANSWER, PARIS_STEPS, TOKENS_IN, TOKENS_OUT, FakeModel, OpenMeteoRecordings

GEOCODE_PARIS: list[dict[str, Any]] = [{"name": "geocode_location", "args": {"query": "Paris"}}]


def collect(
    model: FakeModel, stats: AnswerStats | None = None, recordings: OpenMeteoRecordings | None = None
) -> list[AnswerEvent]:
    """Every event of an answer, as the chat gets them, with Open-Meteo played back."""

    async def run() -> list[AnswerEvent]:
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(recordings or OpenMeteoRecordings()))
        events = stream_weather_answer(model, [HumanMessage("Hi")], stats or AnswerStats(), None, http)
        return [event async for event in events]

    return asyncio.run(run())


def words(events: list[AnswerEvent]) -> list[str]:
    """An answer's pieces of words, without its tool calls."""
    return [event for event in events if isinstance(event, str)]


def test_streams_the_model_s_words_as_it_writes_them() -> None:
    pieces = words(collect(FakeModel()))
    assert "".join(pieces) == ANSWER
    assert len(pieces) == len(ANSWER.split())


def test_adds_up_the_tokens_each_chunk_reports() -> None:
    # Gemini reports each chunk's share of the tokens, not a running total (issue 35).
    stats = AnswerStats()
    collect(FakeModel(), stats)
    assert (stats.tokens_in, stats.tokens_out) == (TOKENS_IN, TOKENS_OUT)


def test_the_tokens_add_up_over_every_call_to_the_model() -> None:
    # Three calls: the place, its forecast, the words. Each sends the whole conversation so far, its tokens in too.
    stats = AnswerStats()
    collect(FakeModel(tool_steps=PARIS_STEPS), stats)
    assert (stats.tokens_in, stats.tokens_out) == (3 * TOKENS_IN, 1 + 1 + TOKENS_OUT)


def test_the_model_gets_the_four_weather_tools() -> None:
    model = FakeModel()
    collect(model)
    assert model.bound_tools == ["geocode_location", "get_current_weather", "get_forecast", "get_air_quality"]


def test_each_tool_call_starts_then_ends_with_its_record_before_the_words() -> None:
    model = FakeModel(tool_steps=PARIS_STEPS)
    events = collect(model)
    calls = [event for event in events if not isinstance(event, str)]
    assert [(type(event).__name__, event.call_id, event.name) for event in calls] == [
        ("ToolStarted", "call-0-0", "geocode_location"),
        ("ToolEnded", "call-0-0", "geocode_location"),
        ("ToolStarted", "call-1-0", "get_forecast"),
        ("ToolEnded", "call-1-0", "get_forecast"),
    ]
    assert isinstance(calls[0], ToolStarted)
    assert calls[0].args == {"query": "Paris"}
    ended = calls[1]
    assert isinstance(ended, ToolEnded)
    assert not ended.failed
    assert isinstance(ended.record, ToolCallRecord)
    assert ended.record.request.host == "geocoding-api.open-meteo.com"
    assert "".join(words(events)) == ANSWER


def test_words_written_before_a_tool_call_end_their_paragraph() -> None:
    # Gemini may write a few words, then ask for a tool: the answer's words, later, start a paragraph of their own.
    events = collect(FakeModel(tool_steps=PARIS_STEPS, step_words="Let me check."))
    assert "".join(words(events)) == f"Let me check.\n\nLet me check.\n\n{ANSWER}"


def test_the_model_reads_the_weather_only_never_the_request() -> None:
    model = FakeModel(tool_steps=PARIS_STEPS)
    collect(model)
    [result] = [message for message in model.seen[1] if isinstance(message, ToolMessage)]
    assert '"name":"Paris"' in str(result.content)
    assert "open-meteo.com" not in str(result.content)


def test_a_failed_tool_call_ends_failed_and_the_model_reads_our_sentence() -> None:
    model = FakeModel(tool_steps=PARIS_STEPS)
    events = collect(model, recordings=OpenMeteoRecordings(failing=frozenset({"/v1/forecast"})))
    [failed] = [event for event in events if isinstance(event, ToolEnded) and event.name == "get_forecast"]
    assert (failed.failed, failed.content, failed.record) == (True, WEATHER_UNREACHABLE, None)
    results = [message for message in model.seen[2] if isinstance(message, ToolMessage)]
    assert results[-1].content == WEATHER_UNREACHABLE


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (ModelRateLimitError("quota used up"), ModelBusyError),
        (LangChainModelTimeoutError("too slow"), AnswerTimeoutError),
        (TimeoutError(), AnswerTimeoutError),
        (ModelAuthenticationError("bad key"), ConfigError),
        (ModelPermissionDeniedError("not allowed"), ConfigError),
        (ModelNotFoundError("no such model"), ConfigError),
        (GoogleInvalidRequestError("400 INVALID_ARGUMENT: API key not valid. reason: API_KEY_INVALID"), ConfigError),
        (ModelInvalidRequestError("400 INVALID_ARGUMENT: a bad request"), ModelFailedError),
        (ModelAPIError("500 from the API"), ModelFailedError),
        (ModelConnectionError("reset"), ModelFailedError),
        (RuntimeError("anything else"), ModelFailedError),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, BaseException) else value.__name__,
)
def test_a_failure_becomes_one_of_ours_and_keeps_the_model_s_as_its_cause(
    raised: BaseException, expected: type[Exception]
) -> None:
    with pytest.raises(expected) as caught:
        collect(FakeModel(fail_after_first_word=raised))
    assert caught.value.__cause__ is raised


def test_an_answer_stops_at_its_time_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(answer, "ANSWER_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(AnswerTimeoutError):
        collect(FakeModel(delay=0.02))


def test_a_deadline_that_passes_while_the_page_takes_its_time_is_still_ours(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the agent's own waits are timed: the deadline never lands in the page's code, as a cancel (issue 38).
    monkeypatch.setattr(answer, "ANSWER_TIMEOUT_SECONDS", 0.05)

    async def run() -> None:
        async for _event in stream_answer(make_agent(FakeModel(), []), [HumanMessage("Hi")], AnswerStats(), None):
            await asyncio.sleep(0.03)

    with pytest.raises(AnswerTimeoutError):
        asyncio.run(run())


def test_closing_the_answer_closes_the_model_s_stream() -> None:
    # Stop, on your computer: the model's stream ends too, never left open until it's collected (issue 39).
    model = FakeModel(delay=0.01)

    async def run() -> None:
        events = stream_answer(make_agent(model, []), [HumanMessage("Hi")], AnswerStats(), None)
        await anext(events)
        await events.aclose()

    asyncio.run(run())
    assert model.closed


def traced_with(monkeypatch: pytest.MonkeyPatch, tracer: Tracer | None) -> list[dict[str, object]]:
    """How the answer set LangSmith's tracing up, for one answer with this tracer."""
    seen: list[dict[str, object]] = []

    @contextmanager
    def recording_context(**kwargs: object) -> Iterator[None]:
        seen.append(kwargs)
        yield

    monkeypatch.setattr(answer, "tracing_context", recording_context)

    async def run() -> None:
        async for _event in stream_answer(make_agent(FakeModel(), []), [HumanMessage("Hi")], AnswerStats(), tracer):
            pass

    asyncio.run(run())
    return seen


def test_with_a_tracer_the_run_is_traced_by_its_client_into_its_project(monkeypatch: pytest.MonkeyPatch) -> None:
    # The client hides inputs and outputs itself (issue 34); the project is the app's setting, not only the
    # environment's (issue 42).
    tracer = Tracer(client=cast("Client", object()), project="nimbus-tests")
    expected = {"enabled": True, "client": tracer.client, "project_name": "nimbus-tests"}
    assert traced_with(monkeypatch, tracer) == [expected]


def test_without_a_tracer_tracing_is_off_whatever_the_environment_says(monkeypatch: pytest.MonkeyPatch) -> None:
    # LangChain would trace by itself whenever LANGSMITH_TRACING is set (issue 33).
    assert traced_with(monkeypatch, None) == [{"enabled": False, "client": None, "project_name": None}]


def test_the_limits_are_1024_tokens_a_call_5_calls_and_30_seconds() -> None:
    # In numbers: a test that took them from the constants would follow any change to them.
    from nimbus.constants import AGENT_RECURSION_LIMIT, ANSWER_TIMEOUT_SECONDS, MAX_MODEL_CALLS, MAX_OUTPUT_TOKENS

    assert (MAX_OUTPUT_TOKENS, MAX_MODEL_CALLS, AGENT_RECURSION_LIMIT, ANSWER_TIMEOUT_SECONDS) == (1024, 5, 10, 30)


def test_markdown_becomes_html() -> None:
    html = render_answer("It's **warm**, so:\n\n- a T-shirt\n- `sunscreen`")
    assert "<strong>warm</strong>" in html
    assert "<li>a T-shirt</li>" in html
    assert "<code>sunscreen</code>" in html


def test_raw_html_is_shown_as_text() -> None:
    html = render_answer("<script>alert(1)</script> <b>x</b>")
    assert "<script>" not in html
    assert "<b>" not in html
    assert "&lt;script&gt;" in html


def test_a_picture_is_never_loaded() -> None:
    assert "<img" not in render_answer("![a cloud](https://example.com/cloud.png)")


def test_a_link_opens_in_a_new_tab_and_tells_the_other_site_nothing() -> None:
    html = render_answer("See [the forecast](https://example.com/forecast).")
    assert f'<a href="https://example.com/forecast" rel="{LINK_REL}" target="_blank">the forecast</a>' in html


def test_a_script_address_never_becomes_a_link() -> None:
    assert "<a" not in render_answer("[click](javascript:alert(1))")
