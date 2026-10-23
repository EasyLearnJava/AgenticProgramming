"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database: one point per chunk, with its vector, its text and
its metadata. Qdrant runs in local mode, inside this script, and saves its points in the folder qdrant_data/. It
handles:
  1. Opening Qdrant in local mode, on disk in qdrant_data/
  2. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  3. Making the LangChain store on it, whose add_documents() embeds and stores chunks (one call to Gemini)

Usage (this file only defines these; pipeline.py runs the steps):
    client = make_client()                                ->  Qdrant in local mode, its points in qdrant_data/
    store = make_vector_store(embeddings, size, client)   ->  a new, empty collection, "it_knowledge_base"
    store.add_documents(chunks)                           ->  the chunks embedded and stored (one call to Gemini)
"""
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FilterSelector, VectorParams

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"

# Where Qdrant's local mode saves the points: next to this file, whichever folder the script is run from
QDRANT_PATH = Path(__file__).resolve().parent / "qdrant_data"


def make_client(path: str | Path = QDRANT_PATH) -> QdrantClient:
    """Qdrant in local mode: it runs inside this program and saves its points in the folder `path`, made if it's not
    there. Only one program at a time can open the folder."""
    return QdrantClient(path=str(path))


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it. Its
    # points go first: on Windows, Qdrant's local mode can't remove the files of a collection it has open, and a new
    # collection by the same name would find the old points in them.
    if client.collection_exists(collection):
        client.delete(collection, points_selector=FilterSelector(filter=Filter()))   # no rules: every point
        client.delete_collection(collection)
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)
