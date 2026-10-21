"""
IT Knowledge Base: The RAG Engine
=================================

The whole pipeline in one class, the way a server uses it, with the chunks kept in a Qdrant server between runs.
build() embeds the chunks only when the server doesn't already hold exactly these chunks. It handles:
  1. Building: load and split the articles, then reuse the stored chunks, or embed and store them (one call)
  2. Answering: one question, sync or async, with up to MAX_SOURCES different articles as sources
  3. Stats: what the engine holds, how it's set up, and whether it reused the stored chunks

Usage (the Qdrant server must be running first: docker compose up -d):
    python rag_engine.py                       # answers to the three sample questions
    python rag_engine.py "printer not found"   # the answer to your question
"""
import sys
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, CHUNK_SIZE, split_documents
from knowledge_base import KB_FILE, load_documents
from models import CHAT_MODEL, EMBEDDING_MODEL, EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import QUESTIONS, TOP_K, make_retriever
from vector_store import COLLECTION, QDRANT_URL, chunk_id, make_client, make_vector_store

MAX_SOURCES = 3        # sources per answer: the first 3 different articles among the chunks found
SNIPPET_LENGTH = 200   # characters of each source's text shown with it


class RAGEngine:
    """
    The RAG pipeline as one object.

    Step 1: Configure: the constructor stores the settings; nothing is read and no call is made
    Step 2: Build: build() loads and splits the articles, makes sure Qdrant holds their chunks, and makes the chain
    Step 3: Answer: query() or aquery() answers one question with its sources
    """

    # Every setting has a default and is passed by name (the *). Without a client, build() connects to the Qdrant
    # server at QDRANT_URL; the tests pass stand-ins for Gemini
    def __init__(self, *, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
                 embedding_size: int = EMBEDDING_SIZE, client: QdrantClient | None = None,
                 data_path: str | Path = KB_FILE, collection: str = COLLECTION,
                 chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, top_k: int = TOP_K):
        self.embeddings, self.model, self.embedding_size = embeddings, model, embedding_size
        self.client = client
        self.data_path, self.collection = Path(data_path), collection
        self.chunk_size, self.chunk_overlap, self.top_k = chunk_size, chunk_overlap, top_k
        self.documents, self.chunks = [], []
        self.reused_stored_chunks = False
        self.chain: Runnable | None = None

    def build(self) -> None:
        """Load and split the articles, make sure the server holds exactly these chunks, and make the chain."""
        if self.client is None:
            self.client = make_client()
        self.documents = load_documents(self.data_path)
        self.chunks = split_documents(self.documents, self.chunk_size, self.chunk_overlap)
        # Each chunk's id comes from its text, so "the server already holds these chunks" can be checked by id:
        # all stored and nothing else -> reuse them, no call to Gemini; anything else -> empty and store them anew.
        # Only this engine's collection is checked or emptied: engines with collections of their own keep theirs.
        ids = [chunk_id(chunk) for chunk in self.chunks]
        self.reused_stored_chunks = False
        if self.client.collection_exists(self.collection):
            stored = self.client.count(self.collection).count
            found = len(self.client.retrieve(self.collection, ids=ids, with_payload=False, with_vectors=False))
            self.reused_stored_chunks = stored == found == len(ids)
            if not self.reused_stored_chunks:
                self.client.delete_collection(self.collection)
        store = make_vector_store(self.embeddings, self.embedding_size, self.client, self.collection)
        if not self.reused_stored_chunks:
            store.add_documents(self.chunks, ids=ids)          # one call to Gemini: every chunk's embedding
        self.chain = make_rag_chain(make_retriever(store, self.top_k), self.model)

    def query(self, question: str) -> dict:
        """Answer one question: {"answer": ..., "sources": [...]}."""
        return self._with_sources(self._built_chain().invoke(question))

    async def aquery(self, question: str) -> dict:
        """The same, for async code such as a FastAPI route: the server can do other work while Gemini answers."""
        return self._with_sources(await self._built_chain().ainvoke(question))

    def _built_chain(self) -> Runnable:
        if self.chain is None:
            raise RuntimeError("The engine isn't built yet: call build() first.")
        return self.chain

    @staticmethod
    def _with_sources(result: dict) -> dict:
        """The answer, and the first MAX_SOURCES different articles among the chunks, each with a snippet."""
        sources, seen = [], set()
        for doc in result["docs"]:
            if doc.metadata["doc_id"] in seen:     # two chunks of one article give one source
                continue
            seen.add(doc.metadata["doc_id"])
            text = doc.page_content
            snippet = text[:SNIPPET_LENGTH] + ("..." if len(text) > SNIPPET_LENGTH else "")
            sources.append({key: doc.metadata[key] for key in ("title", "system", "category")} | {"snippet": snippet})
            if len(sources) == MAX_SOURCES:
                break
        return {"answer": result["answer"], "sources": sources}

    def stats(self) -> dict:
        """What the engine holds and how it's set up, including whether build() reused the stored chunks."""
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": self.collection,
                "chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap, "top_k": self.top_k,
                "embedding_model": EMBEDDING_MODEL, "chat_model": CHAT_MODEL,
                "reused_stored_chunks": self.reused_stored_chunks}


if __name__ == "__main__":
    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS
    engine = RAGEngine()
    engine.build()
    stats = engine.stats()
    how = "already stored, reused" if stats["reused_stored_chunks"] else "embedded and stored"
    print(f"Built: {stats['documents']} articles, {stats['chunks']} chunks ({how}) in Qdrant at {QDRANT_URL}\n")
    for question in questions:
        result = engine.query(question)
        print(f"Q: {question}\nA: {result['answer']}")
        for source in result["sources"]:
            print(f"   source: {source['title']} ({source['system']}, {source['category']})")
        print()
