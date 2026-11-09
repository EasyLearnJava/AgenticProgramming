"""Cache hits have their own truthful workflow; cache operation metadata cannot expose visitor contents."""

from datetime import UTC, datetime

import pytest

from nimbus.axiom_query import Row
from nimbus.chat import render_part
from nimbus.observability import (
    ACTIVITY_VIEWS,
    RESPONSE_WORKFLOW,
    TIMELINE_EVENTS,
    TIMELINE_FIELDS,
    response_bars,
    to_activity_line,
    to_activity_requests,
)


def event(name: str = "semantic_cache.operation", **fields: object) -> Row:
    """Use only the public event shape supplied by the real cache service."""
    return {
        "_time": datetime.now(UTC).isoformat(),
        "requestId": "cache-request-12345678",
        "event": name,
        "ms": 45,
        **fields,
    }


@pytest.mark.parametrize(
    ("status", "expected", "tone"),
    [
        ("exact_hit", "Exact match", "ok"),
        ("semantic_hit", "Similar question matched", "ok"),
        ("miss", "No reusable answer", "idle"),
        ("bypass", "Skipped", "idle"),
        ("error", "Unavailable; normal answer flow continues", "warn"),
        ("stored", "Answer saved", "ok"),
        ("shadow_hit", "Match measured; answer not reused", "idle"),
        ("ready", "Inventory read", "ok"),
        ("disabled", "Disabled", "idle"),
    ],
)
def test_cache_timeline_distinguishes_hit_miss_shadow_and_failure(status: str, expected: str, tone: str) -> None:
    """An unavailable optional cache must not look like a failed model call or a successful cache hit."""
    line = to_activity_line(event(action="lookup", status=status))
    assert line is not None
    assert line.what == "Weather answer cache · lookup"
    assert expected in line.detail
    assert "45 ms" in line.detail
    assert line.tone == tone


def test_cache_timeline_rejects_unknown_metadata_and_private_values() -> None:
    """Even a contaminated provider event cannot disclose questions, values, scopes or keys on public Activity."""
    private = "private-question-answer-key-scope"
    line = to_activity_line(
        event(action=private, status=private, reason=private, question=private, answer=private, scope=private)
    )
    assert line is not None
    assert line.what == "Weather answer cache"
    assert line.detail == "Outcome unavailable in 45 ms"
    assert private not in str(line)
    assert not {"question", "answer", "scope", "vector", "api_key"} & set(TIMELINE_FIELDS)


def test_cached_response_has_no_missing_model_trace_warning() -> None:
    """A successful cache hit truthfully records zero model calls and links no previous visitor's trace."""
    rows = [
        event("chat.request", lane="rest-no-auth"),
        event(action="lookup", status="semantic_hit"),
        event("chat.done", workflow="cached", toolCalls=0),
    ]
    [request] = to_activity_requests(["cache-request-12345678"], rows)
    assert request.summary.what == "Cached weather answer"
    assert "no model or tool calls" in request.summary.detail
    assert request.trace_url is None
    assert "reused a fresh weather answer" in request.trace_note
    assert "No LangSmith model trace" in request.trace_note
    assert "token usage unavailable" not in request.summary.detail


def test_cache_workflow_has_separate_metrics_and_errors_are_findable() -> None:
    """Cached responses do not dilute agent latency or disappear from workflow reporting."""
    assert '"cached"' in RESPONSE_WORKFLOW
    [bar] = response_bars([{"responseWorkflow": "cached", "responses": 2, "p50": 40, "p95": 50}])
    assert bar.label == "Cached weather answers"
    assert "semantic_cache.operation" in TIMELINE_EVENTS
    assert 'event == "semantic_cache.operation"' in ACTIVITY_VIEWS["errors"]


def test_cache_badge_and_receipt_stay_outside_the_answer_text() -> None:
    """Browser history collects only answer prose; cache status and verification receipts stay separate."""
    output = render_part(
        "chat_end.html",
        {
            "turn_id": "test",
            "answer": "Weather summary",
            "cache_note": "Cached answer · expires in 90 seconds",
            "cache_receipt": 'signed<receipt>"',
        },
    )
    assert 'class="answer-cache-note"' in output
    assert 'data-cache-receipt="signed&lt;receipt&gt;&#34;"' in output
    assert 'id="answer-test">Weather summary</div>' in output
    assert output.index("Cached answer") < output.index('id="answer-test"')
