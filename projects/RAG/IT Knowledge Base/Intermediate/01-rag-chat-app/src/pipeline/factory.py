"""
IT Knowledge Base: The Engine's Parts
=====================================

The one place that decides which classes the app runs with: every part is made from its section of config.yaml and
handed to RAGEngine, which only knows the parts' interfaces. To replace a part, change it here (or in config.yaml);
nothing else has to know. It handles:
  1. Building each part from its settings: loader, chunker, embedder, vector store, retriever, LLM client
  2. Building the two models with the API key, unless stand-ins are passed in (the tests pass them)

Usage:
    engine = create_engine(settings, api_key)     ->  RAGEngine, not built yet: no file is read and no call is made
"""
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.chunking.chunker import Chunker
from src.config.settings import Settings
from src.embeddings.embedder import Embedder, create_embedding_model
from src.ingestion.loader import KBLoader
from src.llm.llm_client import LLMClient, create_chat_model
from src.pipeline.rag_engine import RAGEngine
from src.retrieval.retriever import KBRetriever
from src.vectordb.vector_store import create_vector_store


def create_engine(settings: Settings, api_key: SecretStr | None = None, *, embedding_model: Embeddings | None = None,
                  chat_model: BaseChatModel | None = None) -> RAGEngine:
    """The engine, with every part config.yaml names. The models are built with api_key unless they're passed in."""
    embedder = Embedder(embedding_model or create_embedding_model(settings.embeddings, api_key),
                        dimensions=settings.embeddings.dimensions, batch_size=settings.embeddings.batch_size)
    store = create_vector_store(settings.vectordb)
    return RAGEngine(
        loader=KBLoader(settings.ingestion.path, text_columns=settings.ingestion.text_columns,
                        metadata_columns=settings.ingestion.metadata_columns,
                        required_columns=settings.ingestion.required_columns, encoding=settings.ingestion.encoding),
        chunker=Chunker(chunk_size=settings.chunking.chunk_size, chunk_overlap=settings.chunking.chunk_overlap),
        embedder=embedder,
        store=store,
        retriever=KBRetriever(embedder=embedder, store=store, k=settings.retrieval.top_k),
        llm=LLMClient(chat_model or create_chat_model(settings.llm, api_key)),
        max_sources=settings.pipeline.max_sources,
        snippet_length=settings.pipeline.snippet_length,
    )
