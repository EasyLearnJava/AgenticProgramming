"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing the answer, then the articles it came from

Usage (pipeline.py calls it; this file only defines it):
    print_answer(question, chain.invoke(question))   ->  the answer, then the articles it came from
"""


def print_answer(question: str, result: dict) -> None:
    """Print the question, Gemini's answer, then the articles of the chunks found, each once, closest first."""
    print(f"Question: {question}\n")
    print("Answer (Gemini's, from the chunks found):")
    print(result["answer"])
    print("\nSources (the articles of the chunks found, closest first):")
    for title in dict.fromkeys(doc.metadata["title"] for doc in result["docs"]):   # each title once, in order
        print(f"  {title}")
