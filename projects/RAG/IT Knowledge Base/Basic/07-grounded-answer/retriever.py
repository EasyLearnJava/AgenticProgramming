"""
IT Knowledge Base: The Retriever
================================

Finds the chunks closest to a question: the question is embedded with the same model as the chunks, and Qdrant
gives back the closest ones. It handles:
  1. Making a retriever that embeds and searches in one call, and returns TOP_K chunks
  2. Turning the chunks into one numbered, titled text for a prompt

Usage (this file only defines these; pipeline.py runs the steps):
    retriever = make_retriever(store)   ->  a Runnable: retriever.invoke(question) gives the TOP_K closest chunks
    format_docs(chunks)                 ->  the chunks as one text for a prompt, each numbered and titled
"""
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_qdrant import QdrantVectorStore

TOP_K = 5   # how many chunks each search returns


def make_retriever(store: QdrantVectorStore, k: int = TOP_K) -> VectorStoreRetriever:
    """A retriever whose every invoke() returns the k closest chunks."""
    # as_retriever() comes from LangChain's VectorStore: a retriever that searches this store
    return store.as_retriever(search_kwargs={"k": k})


def format_docs(docs: list[Document]) -> str:
    """The chunks as one text for a prompt, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))
