"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding and storing them in Qdrant (one call to Gemini), then printing the collection and every point

Usage:
    python pipeline.py    # the points are saved in qdrant_data/, next to this file (Qdrant's local mode)
"""
from pathlib import Path

from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from utils import print_points
from vector_store import QDRANT_PATH, make_client, make_vector_store


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size, and a folder of their own
def main(embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE, qdrant_path: Path = QDRANT_PATH) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed and store")
    client = make_client(qdrant_path)
    print(f"Qdrant: local mode, inside this script, saving its points in {Path(qdrant_path).name}/")
    store = make_vector_store(embeddings, size, client)   # a new collection: any old one is deleted
    store.add_documents(chunks)                    # one call to Gemini: every chunk's embedding
    print_points(store)
    client.close()                                 # the points stay in the folder, and another program can open it


if __name__ == "__main__":
    main()
