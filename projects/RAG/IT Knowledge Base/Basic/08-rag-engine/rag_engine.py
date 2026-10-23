"""
IT Knowledge Base: The RAG Engine
=================================

The whole pipeline in one class, the way a server uses it: build() fills the vector store once, and query() then
answers each question with its sources. It handles:
  1. Building: load and split the articles, embed and store the chunks, make the chain (one call to Gemini)
  2. Answering: one question, with up to MAX_SOURCES different articles as sources
  3. Stats: what the engine holds and how it's set up

Usage (this file only defines these; pipeline.py runs the steps):
    engine = RAGEngine()                             ->  settings only: nothing is read and no call is made
    engine.build()                                   ->  read, chunk, embed and store (one call to Gemini)
    engine.query(question)                           ->  the answer and up to 3 sources (two calls)
"""
from pathlib import Path

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, CHUNK_SIZE, split_documents
from knowledge_base import KB_FILE, load_documents
from models import CHAT_MODEL, EMBEDDING_MODEL, EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import TOP_K, make_retriever
from vector_store import COLLECTION, make_vector_store

MAX_SOURCES = 3        # sources per answer: the first 3 different articles among the chunks found
SNIPPET_LENGTH = 200   # characters of each source's text shown with it


class RAGEngine:
    """
    The RAG pipeline as one object.

    Step 1: Configure: the constructor stores the settings; nothing is read and no call is made
    Step 2: Build: build() loads, splits, embeds and stores the articles, and makes the chain
    Step 3: Answer: query() answers one question with its sources
    """

    # Every setting has a default and is passed by name (the *); the tests pass stand-ins for Gemini
    def __init__(self, *, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
                 embedding_size: int = EMBEDDING_SIZE, client: QdrantClient | None = None,
                 data_path: str | Path = KB_FILE, collection: str = COLLECTION,
                 chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP, top_k: int = TOP_K):
        self.embeddings, self.model, self.embedding_size, self.client = embeddings, model, embedding_size, client
        # Path comes from Python's pathlib: a file path that works the same on every system
        self.data_path, self.collection = Path(data_path), collection
        self.chunk_size, self.chunk_overlap, self.top_k = chunk_size, chunk_overlap, top_k
        self.documents, self.chunks = [], []
        self.chain: Runnable | None = None

    def build(self) -> None:
        """Load and split the articles, embed and store the chunks (one call to Gemini), and make the chain."""
        self.documents = load_documents(self.data_path)
        self.chunks = split_documents(self.documents, self.chunk_size, self.chunk_overlap)
        store = make_vector_store(self.embeddings, self.embedding_size, self.client, self.collection)
        # add_documents() comes from LangChain's VectorStore: it embeds the chunks, then stores them
        store.add_documents(self.chunks)
        self.chain = make_rag_chain(make_retriever(store, self.top_k), self.model)

    def query(self, question: str) -> dict:
        """Answer one question: {"answer": ..., "sources": [...]}."""
        # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
        return self._with_sources(self._built_chain().invoke(question))

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
        """What the engine holds and how it's set up."""
        return {"documents": len(self.documents), "chunks": len(self.chunks), "collection": self.collection,
                "chunk_size": self.chunk_size, "chunk_overlap": self.chunk_overlap, "top_k": self.top_k,
                "embedding_model": EMBEDDING_MODEL, "chat_model": CHAT_MODEL}
