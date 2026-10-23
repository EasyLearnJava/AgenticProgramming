"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding every chunk (one call to Gemini), then printing each chunk's vector size and first numbers

Usage:
    python pipeline.py
"""
from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import embeddings
from utils import print_vectors


# The tests pass a stand-in for Gemini as `embeddings`
def main(embeddings: Embeddings = embeddings) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed")
    vectors = embed_chunks(chunks, embeddings)
    print_vectors(chunks, vectors)


if __name__ == "__main__":
    main()
