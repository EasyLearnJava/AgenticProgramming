"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing a search: the question's vector, the closest chunks with their scores, and what a prompt gets

Usage (pipeline.py calls it; this file only defines it):
    print_retrieval(question, vector, scored, chunks)   ->  each step of a search, then the prompt's text
"""
from langchain_core.documents import Document

from retriever import format_docs


def print_retrieval(question: str, question_vector: list[float], scored: list[tuple[Document, float]],
                    chunks: list[Document]) -> None:
    """Print the question's vector, the closest chunks with their scores, the retriever's chunks, and the prompt."""
    print(f"Question: {question}")
    start = ", ".join(f"{x:.4f}" for x in question_vector[:5])
    print(f"The question became {len(question_vector)} numbers: [{start}, ...]")
    # The score is the cosine similarity, from -1 to 1; the closer to 1, the closer the meaning
    print(f"\nThe {len(scored)} closest chunks, with their scores, closest first:")
    for chunk, score in scored:
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print("\nThe retriever, embedding and searching in one call, found:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print("\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):")
    print(format_docs(chunks[:2]))
