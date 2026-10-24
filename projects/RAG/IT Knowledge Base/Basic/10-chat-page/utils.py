"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing an answer with the articles the search found

Usage (pipeline.py calls it; this file only defines it):
    print_result(question, engine.query(question))   ->  the question, the answer, then each source
"""


def print_result(question: str, result: dict) -> None:
    """Print one question, its answer, the articles the search found (what Gemini was given, not a checked list
    of what the answer used), then a blank line."""
    print(f"Q: {question}\nA: {result['answer']}")
    for source in result["sources"]:
        print(f"   found by the search: {source['title']} ({source['system']}, {source['category']})")
    print()
