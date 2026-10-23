"""
IT Knowledge Base: Embeddings
=============================

Turns the knowledge base's 28 chunks into vectors with Gemini: lists of numbers that stand for each chunk's meaning,
so texts with close meanings get vectors that point in close directions. It handles:
  1. Embedding every chunk's text in one call to Gemini

Usage (this file only defines these; pipeline.py runs the steps):
    vectors = embed_chunks(chunks, embeddings)   ->  28 vectors of 768 numbers, in order (one call to Gemini)
"""
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


def embed_chunks(chunks: list[Document], embeddings: Embeddings) -> list[list[float]]:
    """One vector per chunk, from one embed_documents() call. Only the text is embedded, not the metadata."""
    # embed_documents() comes from LangChain's Embeddings (Gemini's, here): a list of texts in, a vector each out
    return embeddings.embed_documents([chunk.page_content for chunk in chunks])
