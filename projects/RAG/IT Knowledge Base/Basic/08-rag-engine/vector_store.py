"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database, running in memory inside this process: one point
per chunk, with its vector, its text and its metadata. It handles:
  1. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  2. Making the LangChain store on it, whose add_documents() embeds and stores chunks (one call to Gemini)

Usage (this file only defines these; pipeline.py runs the steps):
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  a new, empty collection, "it_knowledge_base"
    store.add_documents(chunks)                             ->  the chunks embedded and stored (one call to Gemini)
"""
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Not the course app's "it_kb", so the two apps never change each other's points on the same Qdrant server
COLLECTION = "it_knowledge_base"


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)
