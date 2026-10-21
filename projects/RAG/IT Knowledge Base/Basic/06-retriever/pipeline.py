"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding and storing them in Qdrant, in memory (one call to Gemini)
  4. Step 4: the chunks closest to a question, searched by hand and with the retriever (two calls), then printed

Usage:
    python pipeline.py                      # each step for "How do I fix VPN connection timeouts?"
    python pipeline.py "my email bounced"   # each step for your question (3 calls to Gemini)
"""
import sys

from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from retriever import QUESTIONS, TOP_K, make_retriever, print_retrieval
from vector_store import make_vector_store


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(question: str = QUESTIONS[0], embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    store = make_vector_store(embeddings, size)
    store.add_documents(chunks)                    # one call to Gemini: every chunk's embedding
    print(f"Step 3: Embed and store: {store.client.count(store.collection_name).count} points, in Qdrant in memory")
    print("Step 4: Retrieve")
    # The question becomes a vector from the same model as the chunks, so the two can be compared (one call)
    question_vector = embeddings.embed_query(question)
    scored = store.similarity_search_with_score_by_vector(question_vector, k=TOP_K)
    # The retriever does both in one call (one more call to Gemini), without the scores
    found = make_retriever(store).invoke(question)
    print_retrieval(question, question_vector, scored, found)


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTIONS[0])
