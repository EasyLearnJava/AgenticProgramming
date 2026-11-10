"""A chat request's own root: real LangSmith serialization, offline, of its runs, its steps and its single ending."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from structlog.testing import capture_logs

from nimbus.request_trace import REQUEST_TRACE_NAME, RequestTrace
from tests.unit.test_memory_tracing import tracer

PRIVATE = "private visitor question"


async def events(*items: str, fail: bool = False) -> AsyncGenerator[str]:
    """A response's events, failing after them when asked."""
    for item in items:
        yield item
    if fail:
        raise RuntimeError(PRIVATE)


def started(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The runs as each was first sent: only a start carries its name."""
    return [run for run in runs if run.get("name") and run.get("start_time")]


def ended(runs: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    """Each time the run was sent with its end."""
    return [run for run in runs if run["id"] == run_id and run.get("end_time")]


def test_without_a_tracer_nothing_is_traced_and_no_line_names_a_trace() -> None:
    """Tracing off: no root, no parent for the agent or Mem0, and the response's events pass as they are."""
    trace = RequestTrace.begin(None)
    assert trace.fields() == {}
    assert trace.parent is None
    assert trace.run_tree() is None
    with trace.step("lookup"):
        pass

    async def read() -> list[str]:
        return [item async for item in trace.wrap(events("a", "b"))]

    assert asyncio.run(read()) == ["a", "b"]
    assert trace.ended


def test_the_root_and_its_cache_steps_hold_only_names_timings_and_outcomes() -> None:
    """The root and each cache step are queued with empty payloads; a step that raised is an error, not its text."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    assert trace.parent is not None
    root_id = str(trace.parent.run_id)
    assert trace.fields() == {"traceId": root_id}
    with trace.step("lookup"):
        pass
    with pytest.raises(RuntimeError), trace.step("store"):
        raise RuntimeError(PRIVATE)
    trace.workflow = "cached"
    trace.end()
    trace.end()
    runs = client.kept_runs
    root, lookup, store = started(runs)
    assert (root["name"], root["id"], root["trace_id"]) == (REQUEST_TRACE_NAME, root_id, root_id)
    assert root.get("parent_run_id") is None
    assert root["run_type"] == "chain"
    assert root["session_name"] == "synthetic-memory"
    for step, name in ((lookup, "weather_cache.lookup"), (store, "weather_cache.store")):
        assert step["name"] == name
        assert step["trace_id"] == root_id
        assert step["parent_run_id"] == root_id
        assert step["dotted_order"].startswith(root["dotted_order"] + ".")
        assert step["inputs"] == {}
    [lookup_end] = ended(runs, lookup["id"])
    [store_end] = ended(runs, store["id"])
    assert not lookup_end.get("error")
    assert store_end.get("error")
    # Ended once, however often it's asked to end, with its workflow and no failure.
    [root_end] = ended(runs, root_id)
    assert root_end["extra"]["metadata"]["workflow"] == "cached"
    assert not root_end.get("error")
    assert root_end["outputs"] == {}
    assert PRIVATE not in str(runs)


def test_the_run_tree_is_the_queued_root_for_the_agent_to_nest_under() -> None:
    """LangChain finds the root by this object: same IDs, same order, same project."""
    tracing, _client = tracer()
    trace = RequestTrace.begin(tracing)
    tree = trace.run_tree()
    assert trace.parent is not None
    assert tree is not None
    assert (tree.id, tree.trace_id, tree.dotted_order) == (
        trace.parent.run_id,
        trace.parent.trace_id,
        trace.parent.dotted_order,
    )
    assert tree.session_name == "synthetic-memory"


@pytest.mark.parametrize("ending", ["finished", "failed", "closed"])
def test_wrap_ends_the_root_once_however_the_events_end(ending: str) -> None:
    """A finished or closed stream ends the root unfailed; one that raised ends it failed, and still raises."""
    tracing, client = tracer()
    trace = RequestTrace.begin(tracing)
    assert trace.parent is not None

    async def run() -> None:
        stream = trace.wrap(events("a", "b", fail=ending == "failed"))
        if ending == "closed":
            await anext(stream)
            await stream.aclose()
            return
        async for _item in stream:
            pass

    if ending == "failed":
        with pytest.raises(RuntimeError):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert trace.ended
    assert trace.failed is (ending == "failed")
    [root_end] = ended(client.kept_runs, str(trace.parent.run_id))
    assert bool(root_end.get("error")) is (ending == "failed")


def test_a_root_that_couldnt_be_written_leaves_the_request_untraced(monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer goes on: no trace ID on its lines, no parent for the agent, and a warning without the error text."""
    tracing, client = tracer()

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(client, "create_run", broken)
    with capture_logs() as logs:
        trace = RequestTrace.begin(tracing)
        trace.end()
    assert trace.fields() == {}
    assert trace.run_tree() is None
    assert [line["event"] for line in logs] == ["trace.request_write_failed"]
    assert PRIVATE not in str(logs)
