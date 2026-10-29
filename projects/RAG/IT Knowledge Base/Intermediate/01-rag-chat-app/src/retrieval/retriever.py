"""
IT Knowledge Base: The Retriever
================================

Finds the chunks closest to a question: the question's vector from the embedder, then a search of the vector store.
A LangChain retriever, so it has invoke(), ainvoke() and batch(), and fits in any LangChain chain. It handles:
  1. Embedding the question with the same model as the chunks, so the two can be compared
  2. Searching the store for the k closest chunks, closest first, each with its score in its metadata
  3. One span for the whole retrieval, naming each chunk found ("doc_id#chunk_index") with its score; and at DEBUG,
     a line per chunk with its title

Usage:
    retriever = KBRetriever(embedder=embedder, store=store, k=5)
    chunks = retriever.invoke("My VPN won't connect")          ->  5 Documents, each with metadata["score"]
    chunks = await retriever.ainvoke("My VPN won't connect")   ->  the same, for async code
"""
import asyncio
import logging

from langchain_core.callbacks import AsyncCallbackManagerForRetrieverRun, CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from src.embeddings.embedder import Embedder
from src.observability.tracing import span
from src.vectordb.vector_store import BaseVectorStore, SearchHit

logger = logging.getLogger(__name__)


class KBRetriever(BaseRetriever):
    """The knowledge base's retriever: embed the question, then search the store."""

    embedder: Embedder
    store: BaseVectorStore
    k: int

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        with span("retrieval.retrieve", top_k=self.k) as fields:
            hits = self.store.search(self.embedder.embed_query(query), self.k)
            return self._documents(hits, fields)

    async def _aget_relevant_documents(self, query: str, *,
                                       run_manager: AsyncCallbackManagerForRetrieverRun) -> list[Document]:
        with span("retrieval.retrieve", top_k=self.k) as fields:
            vector = await self.embedder.aembed_query(query)
            # The store's client blocks while it searches: a worker thread keeps the server free (the trace ID goes
            # with it)
            hits = await asyncio.to_thread(self.store.search, vector, self.k)
            return self._documents(hits, fields)

    @staticmethod
    def _documents(hits: list[SearchHit], fields: dict) -> list[Document]:
        """Each hit as a Document with its score in its metadata; what was found goes on the span's log line."""
        fields.update(found=[f"{hit.chunk.metadata['doc_id']}#{hit.chunk.metadata['chunk_index']}" for hit in hits],
                      scores=[round(hit.score, 4) for hit in hits])
        for rank, (label, hit) in enumerate(zip(fields["found"], hits, strict=True), 1):
            metadata = hit.chunk.metadata
            logger.debug("Chunk found", extra={"rank": rank, "chunk": label, "title": metadata.get("title"),
                                               "score": round(hit.score, 4), "chunk_id": metadata["chunk_id"]})
        return [Document(page_content=hit.chunk.page_content, metadata=hit.chunk.metadata | {"score": hit.score})
                for hit in hits]
