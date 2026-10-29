"""
IT Knowledge Base: Helpers
==========================

Small helpers used across the app that aren't a layer of their own. It handles:
  1. Measuring how long something took, in milliseconds
  2. Shortening a text for display
  3. Printing an answer in the terminal, for `python main.py ask`

Usage:
    start = time.perf_counter(); ...; elapsed_ms(start)     ->  812.4
    truncate("a long text", 6)                              ->  "a long..."
    print_result(question, result, trace_id)                ->  the question, the answer, its sources, its trace ID
"""
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:                       # for the type hint only: utils imports nothing from the app's layers
    from src.pipeline.rag_engine import QueryResult


def elapsed_ms(start: float) -> float:
    """Milliseconds since `start`, a time.perf_counter() reading, to one decimal place."""
    return round((time.perf_counter() - start) * 1000, 1)


def truncate(text: str, limit: int) -> str:
    """The text, cut to `limit` characters with "..." added when it's longer."""
    return text if len(text) <= limit else text[:limit] + "..."


def print_result(question: str, result: "QueryResult", trace_id: str) -> None:
    """Print one question, its answer, the articles the search found (what the model was given, not a checked list
    of what the answer used), and the trace ID to find its log lines by; then a blank line."""
    print(f"Q: {question}\nA: {result.answer}")
    for source in result.sources:
        print(f"   found by the search: {source.title} ({source.system}, {source.category}), score {source.score:.3f}")
    print(f"   trace ID: {trace_id}")
    print()
