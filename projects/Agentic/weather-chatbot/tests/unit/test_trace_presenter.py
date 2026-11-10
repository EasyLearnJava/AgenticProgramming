"""Trace presentation preserves real nesting, parallel timing and honest incomplete/error summaries."""

import pytest

from nimbus.trace_presenter import duration_label, present_trace
from nimbus.trace_view import TraceRow, TraceView


@pytest.mark.parametrize("status", ["Completed", "Failed", "Running"])
def test_standalone_memory_trace_summarizes_its_own_operation(status: str) -> None:
    """A preference operation does not invent a model call or lose its root duration and status."""
    view = present_trace(TraceView("ready", (TraceRow("Mem0 save", "Memory", 145, 0, 0, status),)))
    assert view.duration_ms == 145
    assert view.status == status
    assert view.model_count == view.tool_count == 0
    assert view.memory_count == view.total_count == 1
    assert view.rows[0].kind_slug == "memory"
    assert view.rows[0].parent_index is None
    assert view.failed_count == int(status == "Failed")
    assert view.memory_root


def test_a_chat_requests_mem0_read_is_counted_but_the_trace_is_the_requests() -> None:
    """A read inside a chat request's trace is one memory operation of that request, not a Mem0 trace of its own."""
    view = present_trace(
        TraceView(
            "ready",
            (
                TraceRow("Chat request", "Agent", 900, 0, 0, "Completed"),
                TraceRow("Mem0 read", "Memory", 120, 10, 1, "Completed", parent_index=0),
            ),
        )
    )
    assert view.memory_count == 1
    assert not view.memory_root
    assert view.duration_ms == 900


def test_cache_details_preserve_scores_without_counting_qdrant_as_model_or_weather_tools() -> None:
    """The inspector shows an actual cosine score and cutoff, not a percentage confidence estimate."""
    view = present_trace(
        TraceView(
            "ready",
            (
                TraceRow("Chat request", "Agent", 900, 0, 0, "Completed", outcome="Similarity hit"),
                TraceRow("Weather answer cache lookup", "Step", 40, 0, 1, "Completed", parent_index=0),
                TraceRow(
                    "Qdrant similarity search",
                    "Step",
                    35,
                    5,
                    2,
                    "Completed",
                    parent_index=1,
                    outcome="Similarity hit",
                    similarity_score=0.87654,
                    similarity_threshold=0.8,
                ),
            ),
        )
    )
    assert view.model_count == view.tool_count == 0
    assert view.rows[-1].outcome == "Similarity hit"
    assert view.rows[-1].similarity_score == "0.877"
    assert view.rows[-1].similarity_threshold == "0.800"
    assert view.rows[0].similarity_score == ""


def call(
    label: str,
    start: int,
    took: int | None,
    parent: int | None = None,
    *,
    kind: str = "Tool",
    status: str = "Completed",
) -> TraceRow:
    """Build a sanitized span while deliberately giving depth no authority over its actual parent relation."""
    return TraceRow(label, kind, took, start, 99, status, parent_index=parent)


def test_parallel_nested_calls_stay_with_their_parent_instead_of_the_preceding_row() -> None:
    trace = TraceView(
        "ready",
        (
            call("Nimbus agent", 0, 2000, kind="Agent"),
            call("get_current_weather", 100, 700, 0),
            call("get_forecast", 110, 600, 0),
            call("get_current_weather", 120, 650, 1),
            call("get_forecast", 130, 500, 2),
            call("Gemini", 900, 800, 0, kind="Model"),
        ),
    )
    view = present_trace(trace)
    assert [row.key for row in view.rows] == [0, 1, 3, 2, 4, 5]
    assert [row.depth for row in view.rows] == [0, 1, 2, 1, 2, 1]
    assert view.rows[2].ancestor_keys == (0, 1)
    assert view.rows[4].ancestor_keys == (0, 2)
    assert view.rows[1].has_children
    assert not view.rows[2].has_children
    assert view.tool_count == 4
    assert view.model_count == 1
    assert view.total_count == 6
    assert view.duration == "2 s"
    assert view.duration_exact == "2,000 ms"
    assert view.timeline_ms == 2000
    assert view.rows[1].bar_x == 50
    assert view.rows[1].bar_width == 350
    assert view.rows[3].bar_x == 55
    assert view.rows[3].bar_width == 300


def test_child_failures_do_not_falsely_relabel_a_successfully_recovered_agent() -> None:
    view = present_trace(
        TraceView(
            "ready",
            (
                call("Nimbus agent", 0, 500, kind="Agent"),
                call("get_forecast", 100, 10, 0, status="Failed"),
                call("Gemini", 120, 300, 0, kind="Model"),
            ),
        )
    )
    assert view.failed_count == 1
    assert view.status == "Completed"
    assert view.rows[1].status_slug == "failed"
    assert view.duration_ms == 500


def test_running_and_unknown_durations_do_not_become_zero_or_guessed_end_times() -> None:
    view = present_trace(
        TraceView(
            "ready",
            (
                call("Nimbus agent", 0, None, kind="Agent", status="Running"),
                call("Gemini", 30, None, 0, kind="Model", status="Running"),
                call("get_forecast", 10, 0, 0),
            ),
        )
    )
    assert view.duration == "Unknown"
    assert view.duration_exact == "Unknown"
    assert view.duration_ms is None
    assert view.running_count == 2
    assert view.status_slug == "running"
    assert view.timeline_ms == 30
    pending = next(row for row in view.rows if row.label == "Gemini")
    zero = next(row for row in view.rows if row.label == "get_forecast")
    assert pending.duration == "Unknown"
    assert pending.duration_exact == "Unknown"
    assert pending.elapsed_ms is None
    assert pending.bar_width == 0
    assert zero.duration == "0 ms"
    assert zero.duration_exact == "0 ms"
    assert zero.elapsed_ms == 0


@pytest.mark.parametrize("status", ["pending", "unavailable", "disabled", "denied"])
def test_nonready_views_cannot_present_partial_rows_as_success(status: str) -> None:
    trace = TraceView("ready", (call("Nimbus agent", 0, 300, kind="Agent"),))
    # Read failures should never retain or summarize a previously successful lookup.
    object.__setattr__(trace, "status", status)
    view = present_trace(trace)
    assert view.rows == ()
    assert view.total_count == 0
    assert view.duration == "Unknown"
    assert view.status_slug == "unknown"


def test_malformed_parents_and_cycles_are_safe_unlinked_rows_not_an_infinite_tree() -> None:
    view = present_trace(
        TraceView(
            "ready",
            (
                call("Nimbus agent", 0, 100, kind="Agent"),
                call("get_forecast", 10, 20, 2),
                call("get_current_weather", 11, 10, 1),
                call("Gemini", 30, 20, 999, kind="Model"),
                call("get_forecast", 60, 10, 4),
            ),
        )
    )
    assert len(view.rows) == 5
    assert all(row.parent_index is None for row in view.rows)
    assert all(row.depth == 0 for row in view.rows)


def test_negative_or_zero_timing_stays_bounded_without_fabricating_a_finished_duration() -> None:
    view = present_trace(
        TraceView("ready", (call("Nimbus agent", -20, -1, kind="Agent"), call("get_forecast", 0, 0, 0)))
    )
    assert view.duration == "Unknown"
    assert view.timeline_ms == 0
    assert view.ticks == ("0 ms", "0 ms", "0 ms")
    assert all(row.bar_x == row.bar_width == 0 for row in view.rows)
    assert view.rows[0].start_exact == "+0 ms"


def test_missing_parent_does_not_infer_an_ancestor_from_depth_or_chronology() -> None:
    view = present_trace(TraceView("ready", (call("Nimbus agent", 0, 100, kind="Agent"), call("get_forecast", 50, 25))))
    assert view.rows[1].parent_index is None
    assert view.rows[1].ancestor_keys == ()
    assert view.rows[1].depth == 0


def test_children_outside_root_duration_extend_axis_but_never_change_root_elapsed_time() -> None:
    view = present_trace(
        TraceView("ready", (call("Nimbus agent", 0, 1000, kind="Agent"), call("get_forecast", 900, 500, 0)))
    )
    assert view.duration_ms == 1000
    assert view.timeline_ms == 1400
    assert all(0 <= row.bar_x <= row.bar_x + row.bar_width <= 1000 for row in view.rows)


@pytest.mark.parametrize(
    ("milliseconds", "label"), [(None, "Unknown"), (0, "0 ms"), (990, "990 ms"), (1000, "1 s"), (3362, "3.36 s")]
)
def test_duration_labels_keep_zero_and_unknown_distinct(milliseconds: int | None, label: str) -> None:
    assert duration_label(milliseconds) == label
