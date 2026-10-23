"""
IT Knowledge Base: The Vector Store
===================================

Stores the knowledge base's chunks in Qdrant, the vector database: one point per chunk, with its vector, its text and
its metadata. Qdrant runs in local mode, inside this program, and saves its points in the folder qdrant_data/, so
they're kept between runs. It handles:
  1. Opening Qdrant in local mode, on disk in qdrant_data/
  2. Making a new collection for EMBEDDING_SIZE-number vectors, compared by cosine; any old one is deleted first
  3. Opening a collection that's already there, to reuse its points
  4. Giving each chunk an id made from its content, so storing it again replaces it instead of copying it

Usage (this file only defines these; pipeline.py runs the steps):
    make_client()                                           ->  Qdrant in local mode, its points in qdrant_data/
    store = make_vector_store(embeddings, EMBEDDING_SIZE)   ->  a new, empty collection "it_knowledge_base", in memory
    store = open_vector_store(embeddings, client)           ->  the collection already there, with its points
    chunk_id(chunk)                                         ->  the chunk's id, the same on every run
"""
import uuid
from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, Filter, FilterSelector, VectorParams

# Qdrant's word for a table of points; not the course app's "it_kb", so the two apps' points never mix
COLLECTION = "it_knowledge_base"

# Where Qdrant's local mode saves the points: next to this file, whichever folder the app is started from
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
    return open_vector_store(embeddings, client, collection)


def open_vector_store(embeddings: Embeddings, client: QdrantClient,
                      collection: str = COLLECTION) -> QdrantVectorStore:
    """A LangChain QdrantVectorStore on a collection that's already there, with the points it holds."""
    # The check would embed a sample text (one more call to Gemini); make_vector_store() made it with the right size
    # QdrantVectorStore comes from langchain_qdrant: LangChain's vector store on a Qdrant collection
    return QdrantVectorStore(client=client, collection_name=collection, embedding=embeddings,
                             validate_collection_config=False)


def chunk_id(chunk: Document) -> str:
    """The same id every time for the same chunk: a UUID made from its article, place and text."""
    key = f"it-kb/{chunk.metadata['doc_id']}/{chunk.metadata['start_index']}/{chunk.page_content}"
    # uuid5() comes from Python's uuid module: the same id for the same text, every time
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
