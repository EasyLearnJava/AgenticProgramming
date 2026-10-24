"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing an answer with the articles the search found
  2. Printing the tuning scores: one line per chunk size and search

Usage (pipeline.py and tuning.py call them; this file only defines them):
    print_result(question, engine.query(question))   ->  the question, the answer, then each source
    print_table(rows, total)                         ->  the scores, one line per chunk size and search
"""


def print_result(question: str, result: dict) -> None:
    """Print one question, its answer, the articles the search found (what Gemini was given, not a checked list
    of what the answer used), then a blank line."""
    print(f"Q: {question}\nA: {result['answer']}")
    for source in result["sources"]:
        print(f"   found by the search: {source['title']} ({source['system']}, {source['category']})")
    print()


def print_table(rows: list[dict], total: int) -> None:
    """The scores, one line per chunk size and search, each score under its heading; a blank line between sizes."""
    keys = [key for key in rows[0] if key.startswith("top_")]
    headings = [f"found in {key.replace('_', ' ')}" for key in keys]
    print("chunk size  chunks  search    " + "  ".join(headings))
    for number, row in enumerate(rows):
        if number > 0 and row["chunk_size"] != rows[number - 1]["chunk_size"]:
            print()
        # Each score right-aligned under its heading; :g drops a whole number's ".0" (a random row's 1.0 -> 1)
        cells = "  ".join(f"{row[key]:g} of {total}".rjust(len(heading)) for key, heading in zip(keys, headings))
        print(f"{row['chunk_size']:>10}  {row['chunks']:>6}  {row['search']:<8}  {cells}")
