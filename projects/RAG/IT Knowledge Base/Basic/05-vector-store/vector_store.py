"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database: one point per chunk, with its vector, its text and
its metadata. Qdrant runs in local mode, inside this script, and saves its points in the folder qdrant_data/. It
handles:
  1. Opening Qdrant in local mode, on disk in qdrant_data/
  2. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  3. Making the LangChain store on it, which keeps the embedding model for searches
  4. Storing the chunks with the vectors embed_chunks() made for them: no call to Gemini here

Usage (this file only defines these; pipeline.py runs the steps):
    client = make_client()                                ->  Qdrant in local mode, its points in qdrant_data/
    store = make_vector_store(embeddings, size, client)   ->  a new, empty collection, "it_knowledge_base"
    store_vectors(store, chunks, vectors)                 ->  one point per chunk: its vector, text and labels
"""
import uuid
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FilterSelector, PointStruct, VectorParams

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"

# Where Qdrant's local mode saves the points: next to this file, whichever folder the script is run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
QDRANT_PATH = Path(__file__).resolve().parent / "qdrant_data"


def make_client(path: str | Path = QDRANT_PATH) -> QdrantClient:
    """Qdrant in local mode: it runs inside this program and saves its points in the folder `path`, made if it's not
    there. Only one program at a time can open the folder."""
    # QdrantClient comes from qdrant_client: path= runs Qdrant inside this program, its points in that folder
    return QdrantClient(path=str(path))


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
