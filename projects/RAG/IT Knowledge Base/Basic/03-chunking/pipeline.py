"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks, then printing how many each article makes, and every chunk

Usage:
    python pipeline.py        # chunks of at most 512 characters
    python pipeline.py 200    # chunks of at most 200 characters
"""
import sys

from chunking import CHUNK_SIZE, print_chunks, split_documents
from knowledge_base import load_documents


def main(chunk_size: int = CHUNK_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    print("Step 2: Chunk")
    chunks = split_documents(docs, chunk_size=chunk_size)
    print_chunks(docs, chunks, chunk_size)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else CHUNK_SIZE)
