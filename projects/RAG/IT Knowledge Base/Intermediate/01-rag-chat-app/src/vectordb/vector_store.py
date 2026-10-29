"""
IT Knowledge Base: The Vector Store
===================================

Stores the chunks with their vectors, and finds the closest ones to a question's vector. It handles:
  1. BaseVectorStore: the four methods the rest of the app uses, and all a new store has to provide
  2. QdrantStore: those four methods on Qdrant, each timed in a span, with Qdrant's failures turned into
     VectorStoreError
  3. Building the store config.yaml names

    recreate(size)          a new, empty collection for size-number vectors, compared by cosine; any old one deleted
    upsert(chunks, vectors) one point per chunk: its chunk_id as the point's ID, its vector, its text and metadata
    search(vector, k)       the k closest chunks, closest first, each with its score (cosine: 1.0 is the same direction)
    count()                 how many points the collection holds

To use another store (Chroma, pgvector, ...): subclass BaseVectorStore, and add a builder to BUILDERS.

Usage:
    store = create_vector_store(settings.vectordb)
    store.recreate(768); store.upsert(chunks, vectors); hits = store.search(question_vector, 5)
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.config.settings import VectorDBSettings
from src.exceptions import VectorStoreError
from src.observability.tracing import span


@dataclass(frozen=True)
class SearchHit:
    """One chunk a search found, and how close it is to the question."""
    chunk: Document
    score: float


class BaseVectorStore(ABC):
    """What the app needs from a vector store. Every method raises VectorStoreError when the store fails."""

    collection: str

    @abstractmethod
    def recreate(self, vector_size: int) -> None:
        """A new, empty collection for vectors of vector_size numbers; any old one by this name is deleted first."""

    @abstractmethod
    def upsert(self, chunks: list[Document], vectors: list[list[float]]) -> int:
        """Store each chunk with its vector (the same number of each); returns how many points were written."""

    @abstractmethod
    def search(self, vector: list[float], k: int) -> list[SearchHit]:
        """The k chunks closest to the vector, closest first."""

    @abstractmethod
    def count(self) -> int:
        """How many chunks the collection holds."""


class QdrantStore(BaseVectorStore):
    """
    The vector store on a Qdrant collection.

    Step 1: Configure: the constructor stores the client and the collection's name; nothing is created
    Step 2: Use: recreate() once per build, upsert() the chunks, then search() for each question
    """

    def __init__(self, client: QdrantClient, collection: str):
        self.client = client
        self.collection = collection

    def recreate(self, vector_size: int) -> None:
        with span("vectordb.recreate", collection=self.collection, vector_size=vector_size):
            try:
                if self.client.collection_exists(self.collection):
                    self.client.delete_collection(self.collection)
                self.client.create_collection(self.collection,
                                              vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE))
            except Exception as err:
                raise VectorStoreError(f"Couldn't make the collection {self.collection}: {err}") from err

    def upsert(self, chunks: list[Document], vectors: list[list[float]]) -> int:
        with span("vectordb.upsert", collection=self.collection, points=len(chunks)):
            if len(chunks) != len(vectors):
                raise VectorStoreError(f"{len(chunks)} chunks but {len(vectors)} vectors: nothing was stored")
            # The text and metadata go under "page_content" and "metadata", the names LangChain's stores use too
            points = [PointStruct(id=chunk.metadata["chunk_id"], vector=vector,
                                  payload={"page_content": chunk.page_content, "metadata": chunk.metadata})
                      for chunk, vector in zip(chunks, vectors, strict=True)]
            try:
                self.client.upsert(self.collection, points=points)
            except Exception as err:
                raise VectorStoreError(f"Couldn't store the chunks in {self.collection}: {err}") from err
            return len(points)

    def search(self, vector: list[float], k: int) -> list[SearchHit]:
        with span("vectordb.search", collection=self.collection, top_k=k) as fields:
            try:
                points = self.client.query_points(self.collection, query=vector, limit=k, with_payload=True).points
            except Exception as err:
                raise VectorStoreError(f"Couldn't search {self.collection}: {err}") from err
            fields.update(hits=len(points), top_score=round(points[0].score, 4) if points else None)
            return [SearchHit(Document(page_content=point.payload["page_content"],
                                       metadata=point.payload["metadata"]), point.score) for point in points]

    def count(self) -> int:
        try:
            return self.client.count(self.collection).count
        except Exception as err:
            raise VectorStoreError(f"Couldn't count the points in {self.collection}: {err}") from err


def _qdrant(settings: VectorDBSettings) -> BaseVectorStore:
    """Qdrant in memory: inside this process, so the points are gone when it stops."""
    return QdrantStore(QdrantClient(location=settings.location), settings.collection)


BUILDERS: dict[str, Callable[[VectorDBSettings], BaseVectorStore]] = {"qdrant": _qdrant}


def create_vector_store(settings: VectorDBSettings) -> BaseVectorStore:
    """The vector store config.yaml names. Nothing is created in it yet: build() calls recreate()."""
    return BUILDERS[settings.provider](settings)
