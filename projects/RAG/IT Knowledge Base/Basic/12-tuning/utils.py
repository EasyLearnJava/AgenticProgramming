"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing an answer with its sources
  2. Printing the tuning scores: one line per chunk size

Usage (pipeline.py and tuning.py call them; this file only defines them):
    print_result(question, engine.query(question))   ->  the question, the answer, then each source
    print_table(rows, total)                         ->  the scores, one line per chunk size
"""


def print_result(question: str, result: dict) -> None:
    """Print one question, its answer and its sources, then a blank line."""
    print(f"Q: {question}\nA: {result['answer']}")
    for source in result["sources"]:
        print(f"   source: {source['title']} ({source['system']}, {source['category']})")
    print()


def print_table(rows: list[dict], total: int) -> None:
    """The scores, one line per chunk size."""
    keys = [key for key in rows[0] if key.startswith("top_")]
    print("chunk size  chunks  " + "  ".join(f"found in {key.replace('_', ' ')}" for key in keys))
    for row in rows:
        cells = "  ".join(f"{row[key]:>2} of {total:<6}" for key in keys)
        print(f"{row['chunk_size']:>10}  {row['chunks']:>6}  {cells}")
