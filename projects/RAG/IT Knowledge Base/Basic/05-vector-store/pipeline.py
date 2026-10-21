"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding and storing them in Qdrant (one call to Gemini), then printing the collection and every point

Usage:
    python pipeline.py    # with QDRANT_URL in .env: in the Qdrant server (docker compose up -d), shown in its
                          # dashboard; without it: Qdrant in memory, inside this script
"""
import sys

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException

from chunking import CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, QDRANT_URL, make_vector_store, print_points


def connect(qdrant_url: str) -> QdrantClient:
    """The Qdrant server at qdrant_url, without this collection; or Qdrant in memory when there's no address."""
    if not qdrant_url:
        print("Qdrant: in memory, inside this script")
        return QdrantClient(":memory:")
    # A server keeps its points between runs, and these get random ids, so the collection is deleted first.
    # check_compatibility=False skips qdrant-client's background version check, which only warns.
    client = QdrantClient(url=qdrant_url, check_compatibility=False)
    try:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
    except ResponseHandlingException:
        sys.exit(f"Can't reach Qdrant at {qdrant_url}. Start it first, in this folder: docker compose up -d "
                 "(or remove QDRANT_URL from .env to run Qdrant in memory).")
    print(f"Qdrant: the server at {qdrant_url}")
    return client


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE, qdrant_url: str = QDRANT_URL) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed and store")
    store = make_vector_store(embeddings, size, connect(qdrant_url))
    store.add_documents(chunks)                    # one call to Gemini: every chunk's embedding
    print_points(store)
    if qdrant_url:
        print(f"\nSee them in Qdrant's dashboard: {qdrant_url.rstrip('/')}/dashboard")
        print("In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.")


if __name__ == "__main__":
    main()
