"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding them (one call to Gemini)
  4. Step 4: storing them in Qdrant, in memory, with their vectors, then printing the collection and every point

Usage:
    python pipeline.py    # Qdrant runs in memory, inside this script: the points are gone when it ends
"""
from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from utils import print_points
from vector_store import make_vector_store, store_vectors


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    vectors = embed_chunks(chunks, embeddings)     # one call to Gemini: every chunk's embedding
    print(f"Step 3: Embed: {len(vectors)} vectors of {len(vectors[0])} numbers")
    print("Step 4: Store")
    print("Qdrant: in memory, inside this script: the points are gone when it ends")
    store = make_vector_store(embeddings, size)    # Qdrant in memory, and a new collection in it
    store_vectors(store, chunks, vectors)          # Step 3's vectors: no call to Gemini
    print_points(store)


if __name__ == "__main__":
    main()
