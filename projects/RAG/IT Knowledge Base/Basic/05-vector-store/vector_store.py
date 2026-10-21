"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database: one point per chunk, with its vector, its text and
its metadata. It handles:
  1. Making a collection for vectors of EMBEDDING_SIZE numbers, compared by cosine similarity
  2. Embedding and storing the 28 chunks (one call to Gemini)
  3. Printing the collection, then every point stored in it

    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  an empty collection, "it_knowledge_base"
    add_knowledge_base(store)                               ->  the 28 chunks embedded and stored

Usage:
    python vector_store.py    # the collection, then every point stored in it
                              # with QDRANT_URL in .env: in the Qdrant server (docker compose up -d), shown in its
                              # dashboard; without it: Qdrant in memory, inside the script
"""
import os
import sys

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import Distance, VectorParams

from chunking import split_documents
from config import ENV_FILE
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings

# Not the course app's "it_kb", so the two apps never change each other's points on the same Qdrant server
COLLECTION = "it_knowledge_base"

# The Qdrant server to use, from .env or the environment; not set: Qdrant in memory
load_dotenv(ENV_FILE)
QDRANT_URL = os.getenv("QDRANT_URL", "").strip()


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a collection of `size`-number vectors; in memory if no client is given."""
    client = client if client is not None else QdrantClient(":memory:")
    if not client.collection_exists(collection):
        client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


def add_knowledge_base(store: QdrantVectorStore) -> list[Document]:
    """Load the articles, cut them into chunks, and store them; returns the chunks."""
    chunks = split_documents(load_documents())
    # add_documents() embeds every chunk's text (one embed_documents() call) and stores each as a point
    store.add_documents(chunks)
    return chunks


if __name__ == "__main__":
    # A server keeps its points between runs, and these get random ids, so the collection is deleted first.
    # check_compatibility=False skips qdrant-client's background version check, which only warns.
    if QDRANT_URL:
        client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
        try:
            if client.collection_exists(COLLECTION):
                client.delete_collection(COLLECTION)
        except ResponseHandlingException:
            sys.exit(f"Can't reach Qdrant at {QDRANT_URL}. Start it first, in this folder: docker compose up -d "
                     "(or remove QDRANT_URL from .env to run Qdrant in memory).")
        print(f"Qdrant: the server at {QDRANT_URL}")
    else:
        client = QdrantClient(":memory:")
        print("Qdrant: in memory, inside this script")
    store = make_vector_store(embeddings, EMBEDDING_SIZE, client)
    add_knowledge_base(store)
    # scroll() returns points in id order, so they're sorted back into article and place order
    params = store.client.get_collection(COLLECTION).config.params.vectors
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    points.sort(key=lambda point: (int(point.payload["metadata"]["doc_id"]), point.payload["metadata"]["start_index"]))
    print(f"Collection {COLLECTION!r}: {len(points)} points, vectors of {params.size} numbers, "
          f"compared by {params.distance.value}")
    print(f"Each point holds an id, a vector and a payload with {', '.join(sorted(points[0].payload))}")
    print()
    for number, point in enumerate(points, 1):
        metadata = point.payload["metadata"]
        print(f"Point {number} of {len(points)}: {metadata['title']}, from character {metadata['start_index']}: "
              f"{len(point.vector)} numbers, {len(point.payload['page_content'])} characters of text, "
              f"{len(metadata)} labels")
    if QDRANT_URL:
        print(f"\nSee them in Qdrant's dashboard: {QDRANT_URL.rstrip('/')}/dashboard")
        print("In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.")
