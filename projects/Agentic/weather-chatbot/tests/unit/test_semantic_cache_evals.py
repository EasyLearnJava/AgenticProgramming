"""Live-cache evaluation pass rules must distinguish outage, recall and false reuse."""

from typing import Any

from tools.eval_semantic_cache import score_outcomes


def positives(last: str = "semantic_hit") -> list[dict[str, Any]]:
    """Five held-out positives with an explicitly controlled last outcome."""
    return [
        {"split": "validation", "expected": "hit", "result": result, "passed": result == "semantic_hit"}
        for result in [*(["semantic_hit"] * 4), last]
    ]


def test_provider_error_cannot_hide_inside_eighty_percent_recall() -> None:
    """An otherwise acceptable recall result fails when the provider was unavailable."""
    report = score_outcomes(positives("error"), "exact_hit", "miss")
    assert report["positive_recall"] == 0.8
    assert report["provider_errors"] == 1
    assert not report["passed"]
    assert score_outcomes(positives("miss"), "exact_hit", "miss")["passed"]


def test_one_false_hit_fails_even_when_all_paraphrases_hit() -> None:
    """Semantic recall never excuses a mismatched city or private scope."""
    outcomes = [*positives(), {"split": "validation", "expected": "miss", "result": "semantic_hit", "passed": False}]
    report = score_outcomes(outcomes, "exact_hit", "miss")
    assert report["false_hits"] == 1
    assert not report["passed"]
    assert not score_outcomes(positives(), "exact_hit", "semantic_hit")["passed"]
    assert not score_outcomes(positives(), "error", "miss")["passed"]
