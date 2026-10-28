"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing every chunk with its vector's size and first numbers
  2. Printing how close chunk 1's vector is to every other chunk's (cosine similarity)

Usage (pipeline.py calls it; this file only defines it):
    print_vectors(chunks, vectors, EMBEDDING_MODEL)   ->  every chunk with its vector's size and first 5 numbers,
                                                          then how close chunk 1 is to every other chunk, closest first
"""
import math

from langchain_core.documents import Document


def cosine(a: list[float], b: list[float]) -> float:
    """How close two vectors' directions are: 1 for the same direction, 0 at right angles, -1 for opposite."""
    # hypot() comes from Python's math module: a vector's length, the square root of the sum of its squares
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


def print_vectors(chunks: list[Document], vectors: list[list[float]], model_name: str) -> None:
    """Print how many vectors came back, then every chunk: where it is in its article, and its first numbers. Then
    how close chunk 1's vector is to every other chunk's, closest first."""
    print(f"{len(chunks)} chunks -> {len(vectors)} vectors ({model_name})")
    print()
    for number, (chunk, vector) in enumerate(zip(chunks, vectors), 1):
        start = chunk.metadata["start_index"]
        end = start + len(chunk.page_content)
        first = ", ".join(f"{x:.4f}" for x in vector[:5])
        print(f"Chunk {number} of {len(chunks)}: {chunk.metadata['title']}, from character {start} to {end} "
              f"-> converted to {len(vector)} numbers: [{first}, ...]")

    print()
    print(f"How close chunk 1 ({chunks[0].metadata['title']}) is to every other chunk, closest first")
    print("(cosine similarity: 1 is the same direction, 0 is at right angles):")
    closeness = sorted(((cosine(vectors[0], vector), number) for number, vector in enumerate(vectors[1:], 2)),
                       reverse=True)
    for score, number in closeness:
        print(f"  {score:.3f}  chunk {number}: {chunks[number - 1].metadata['title']}")
