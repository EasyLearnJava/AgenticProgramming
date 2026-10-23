"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database, running in memory inside this process: one point
per chunk, with its vector, its text and its metadata. It handles:
  1. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  2. Making the LangChain store on it, whose add_documents() embeds and stores chunks (one call to Gemini)

Usage (this file only defines these; pipeline.py runs the steps):
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  a new, empty collection, "it_knowledge_base"
    # add_documents() comes from LangChain's VectorStore: it embeds the chunks, then stores them
    store.add_documents(chunks)                             ->  the chunks embedded and stored (one call to Gemini)
"""
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FilterSelector, VectorParams

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it. Its
    # points go first: on Windows, Qdrant's local mode can't remove the files of a collection it has open, and a new
    # collection by the same name would find the old points in them.
    # collection_exists() comes from qdrant_client's QdrantClient: whether a collection by this name is there
    if client.collection_exists(collection):
        # delete(), FilterSelector and Filter come from qdrant_client: delete the points the filter matches
        client.delete(collection, points_selector=FilterSelector(filter=Filter()))   # no rules: every point
        # delete_collection() comes from qdrant_client's QdrantClient: it removes the collection
        client.delete_collection(collection)
    # create_collection() and VectorParams come from qdrant_client: a new collection, its vector size and distance
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    # QdrantVectorStore comes from langchain_qdrant: LangChain's vector store on a Qdrant collection
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)
