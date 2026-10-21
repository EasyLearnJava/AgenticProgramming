"""
IT Knowledge Base: Embeddings
=============================

Turns the knowledge base's 28 chunks into vectors with Gemini: lists of numbers that stand for each chunk's meaning,
so texts with close meanings get vectors that point in close directions. It handles:
  1. Embedding every chunk's text in one call to Gemini
  2. Printing every chunk with its vector's size and first numbers

    embed_chunks(split_documents(load_documents()), embeddings)  ->  28 vectors of 768 numbers, in the chunks' order

Usage:
    python embed_chunks.py    # every chunk with its vector's size and first 5 numbers (one call to Gemini)
"""
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_MODEL, embeddings


def embed_chunks(chunks: list[Document], embeddings: Embeddings) -> list[list[float]]:
    """One vector per chunk, from one embed_documents() call. Only the text is embedded, not the metadata."""
    return embeddings.embed_documents([chunk.page_content for chunk in chunks])


if __name__ == "__main__":
    chunks = split_documents(load_documents())
    vectors = embed_chunks(chunks, embeddings)
    print(f"{len(chunks)} chunks -> {len(vectors)} vectors ({EMBEDDING_MODEL})")
    print()
    for number, (chunk, vector) in enumerate(zip(chunks, vectors), 1):
        start = chunk.metadata["start_index"]
        end = start + len(chunk.page_content)
        first = ", ".join(f"{x:.4f}" for x in vector[:5])
        print(f"Chunk {number} of {len(chunks)}: {chunk.metadata['title']}, from character {start} to {end} "
              f"-> converted to {len(vector)} numbers: [{first}, ...]")
