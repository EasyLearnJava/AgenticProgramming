"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database: one point per chunk, with its vector, its text and
its metadata. Qdrant can also run as a server in Docker (docker-compose.yml), which keeps its points between runs.
It handles:
  1. Connecting to the Qdrant server at QDRANT_URL
  2. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  3. Opening a collection that's already there, to reuse its points
  4. Giving each chunk an id made from its content, so storing it again replaces it instead of copying it

Usage (this file only defines these; pipeline.py runs the steps):
    make_client()                                           ->  a client for the server at QDRANT_URL
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  a new, empty collection "it_knowledge_base", in memory
    store = open_vector_store(embeddings, client)           ->  the collection already there, with its points
    chunk_id(chunk)                                         ->  the chunk's id, the same on every run
"""
import os
import uuid

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config import ENV_FILE

# Not the course app's "it_kb", so the two apps never change each other's points on the same Qdrant server
COLLECTION = "it_knowledge_base"

# The Qdrant server's address, from .env or the environment; else the one docker-compose.yml opens on this machine
load_dotenv(ENV_FILE)
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")


def make_client(url: str = QDRANT_URL) -> QdrantClient:
    """A client for the Qdrant server; it sends nothing until the first request."""
    # check_compatibility=False skips a background version check that only warns: docker-compose.yml pins the version
    return QdrantClient(url=url, check_compatibility=False)


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    return open_vector_store(embeddings, client, collection)


def open_vector_store(embeddings: Embeddings, client: QdrantClient,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a collection that's already there, with the points it holds."""
    # The check would embed a sample text (one more call to Gemini); make_vector_store() made it with the right size
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


def chunk_id(chunk: Document) -> str:
    """The same id every time for the same chunk: a UUID made from its article, place and text."""
    key = f"it-kb/{chunk.metadata['doc_id']}/{chunk.metadata['start_index']}/{chunk.page_content}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
