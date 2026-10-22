"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database, running in memory inside this process: one point
per chunk, with its vector, its text and its metadata. It handles:
  1. Making a collection for vectors of EMBEDDING_SIZE numbers, compared by cosine similarity
  2. Embedding and storing the 28 chunks (one call to Gemini)

Usage (this file only defines these; pipeline.py runs the steps):
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  an empty collection, "it_knowledge_base"
    add_knowledge_base(store)                               ->  the 28 chunks embedded and stored
"""
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from chunking import split_documents
from knowledge_base import load_documents

# Not the course app's "it_kb", so the two apps never change each other's points on the same Qdrant server
COLLECTION = "it_knowledge_base"


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
    """Load the articles, cut them into chunks, and store them (one embed_documents() call); returns the chunks."""
    chunks = split_documents(load_documents())
    store.add_documents(chunks)
    return chunks
