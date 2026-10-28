"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing a search: the question's vector, the closest chunks with their scores, the top score worked out by
     hand, and a sample of what a prompt gets

Usage (pipeline.py calls it; this file only defines it):
    print_retrieval(question, vector, scored, chunks, top_vector, format_docs(chunks[:2]))
        ->  each step of a search, then the prompt's text: the first 2 chunks, as format_docs() joins them
"""
import math

from langchain_core.documents import Document


def print_retrieval(question: str, question_vector: list[float], scored: list[tuple[Document, float]],
                    chunks: list[Document], top_vector: list[float], sample: str) -> None:
    """Print the question's vector, the closest chunks with their scores, the top score worked out by hand from
    the question's vector and the top chunk's stored one, the retriever's chunks, and a sample of the prompt:
    `sample`, the first 2 chunks as format_docs() joins them."""
    print(f"Question: {question}")
    start = ", ".join(f"{x:.4f}" for x in question_vector[:5])
    print(f"The question became {len(question_vector)} numbers: [{start}, ...]")
    # The score is the cosine similarity, from -1 to 1; the closer to 1, the closer the meaning
    print(f"\nThe {len(scored)} closest chunks, with their scores, closest first:")
    for chunk, score in scored:
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")

    # The cosine: the numbers multiplied pair by pair and added up, then divided by both vectors' lengths
    # hypot() comes from Python's math module: a vector's length, the square root of the sum of its squares
    products = sum(x * y for x, y in zip(question_vector, top_vector))
    question_length, chunk_length = math.hypot(*question_vector), math.hypot(*top_vector)
    print("\nThe top score, worked out by hand from the question's vector and the top chunk's stored one:")
    print(f"  the {len(top_vector)} numbers multiplied pair by pair, then added up: {products:.4f}")
    print(f"  the lengths: {question_length:.4f} (the question's), "
          f"{chunk_length:.4f} (the chunk's, as Qdrant keeps it)")
    cosine = products / (question_length * chunk_length)
    print(f"  {products:.4f} / ({question_length:.4f} × {chunk_length:.4f}) = {cosine:.3f}, "
          f"and Qdrant's score: {scored[0][1]:.3f}")

    print("\nThe retriever, embedding and searching in one call, found:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print(f"\nA sample of what a prompt gets: the first 2 of the {len(chunks)} chunks, as one text (format_docs):")
    print(sample)
