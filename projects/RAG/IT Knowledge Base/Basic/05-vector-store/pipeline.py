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
from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from utils import connect, print_points
from vector_store import QDRANT_URL, make_vector_store


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE, qdrant_url: str = QDRANT_URL) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    print("Step 3: Embed and store")
    store = make_vector_store(embeddings, size, connect(qdrant_url))   # a new collection: any old one is deleted
    store.add_documents(chunks)                    # one call to Gemini: every chunk's embedding
    print_points(store)
    if qdrant_url:
        print(f"\nSee them in Qdrant's dashboard: {qdrant_url.rstrip('/')}/dashboard")
        print("In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.")


if __name__ == "__main__":
    main()
