"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing every chunk with its vector's size and first numbers

Usage (pipeline.py calls it; this file only defines it):
    print_vectors(chunks, vectors)   ->  every chunk with its vector's size and first 5 numbers
"""
from langchain_core.documents import Document

from models import EMBEDDING_MODEL


def print_vectors(chunks: list[Document], vectors: list[list[float]]) -> None:
    """Print how many vectors came back, then every chunk: where it is in its article, and its first numbers."""
    print(f"{len(chunks)} chunks -> {len(vectors)} vectors ({EMBEDDING_MODEL})")
    print()
    for number, (chunk, vector) in enumerate(zip(chunks, vectors), 1):
        start = chunk.metadata["start_index"]
        end = start + len(chunk.page_content)
        first = ", ".join(f"{x:.4f}" for x in vector[:5])
        print(f"Chunk {number} of {len(chunks)}: {chunk.metadata['title']}, from character {start} to {end} "
              f"-> converted to {len(vector)} numbers: [{first}, ...]")
