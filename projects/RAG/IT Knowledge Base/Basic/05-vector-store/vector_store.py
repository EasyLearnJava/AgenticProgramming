"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database, running in memory inside this process: one point
per chunk, with its vector, its text and its metadata. It handles:
  1. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine, with the settings for an index
     (which Qdrant ignores in memory); any old one is deleted first
  2. Making the LangChain store on it, which keeps the embedding model for searches
  3. Storing the chunks with the vectors embed_chunks() made for them: no call to Gemini here

Usage (this file only defines these; pipeline.py runs the steps):
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  a new, empty collection, "it_knowledge_base"
    store_vectors(store, chunks, vectors)                   ->  one point per chunk: its vector, text and labels
"""
import uuid

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, PointStruct, VectorParams

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"


def make_vector_store(embeddings: Embeddings, size: int, client: QdrantClient | None = None,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a new, empty collection of `size`-number vectors; in memory if no client."""
    # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
    client = client if client is not None else QdrantClient(":memory:")
    # Always fresh: a collection already there by this name is deleted, so nothing from before is left in it
    # collection_exists() comes from qdrant_client's QdrantClient: whether a collection by this name is there
    if client.collection_exists(collection):
        # delete_collection() comes from qdrant_client's QdrantClient: it removes the collection and its points
        client.delete_collection(collection)
    # create_collection() and VectorParams come from qdrant_client: a new collection, its vector size and distance
    # HnswConfigDiff comes from qdrant_client too: the settings for an index, HNSW, a graph linking each vector to its
    # m nearest, so a search hops through the graph and checks a small part of the vectors, not all of them.
    # ef_construct is how thoroughly it searches while building the graph; 16 and 100 are Qdrant's defaults.
    # An index makes search faster, not better: at best it finds the same chunks as comparing every vector.
    # Here it does nothing: in memory, Qdrant ignores these settings and compares every vector, which is fine for 28.
    # A Qdrant server (in Docker, say) builds the index only once it holds thousands of chunks, not 28
    client.create_collection(collection, vectors_config=VectorParams(size=size, distance=Distance.COSINE),
                             hnsw_config=HnswConfigDiff(m=16, ef_construct=100))
    # The check would embed a sample text (one more call to Gemini); the collection was just made with the right size
    # QdrantVectorStore comes from langchain_qdrant: LangChain's vector store on a Qdrant collection
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


def store_vectors(store: QdrantVectorStore, chunks: list[Document], vectors: list[list[float]]) -> None:
    """Store each chunk as one point: the vector embed_chunks() made for it, its text and its labels; nothing is
    embedded here. A chunk without a vector, or a vector without a chunk, stops it: no chunk is left out."""
    # The text and labels go under "page_content" and "metadata", the names LangChain's store reads them from
    # PointStruct comes from qdrant_client, uuid4() from Python's uuid module: one point, with a new random id
    points = [PointStruct(id=str(uuid.uuid4()), vector=vector,
                          payload={"page_content": chunk.page_content, "metadata": chunk.metadata})
              for chunk, vector in zip(chunks, vectors, strict=True)]     # strict: the two lists, the same length
    # upsert() comes from qdrant_client's QdrantClient: it writes the points into the collection
    store.client.upsert(store.collection_name, points=points)
