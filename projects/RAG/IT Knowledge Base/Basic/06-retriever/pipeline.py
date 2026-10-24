"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding them (one call to Gemini)
  4. Step 4: storing them in Qdrant, in memory, with their vectors
  5. Step 5: the chunks closest to a question, searched by hand and with the retriever (two calls), then printed

Usage:
    python pipeline.py                      # each step for "How do I fix VPN connection timeouts?"
    python pipeline.py "my email bounced"   # each step for your question (3 calls to Gemini)
"""
import sys

from langchain_core.embeddings import Embeddings

from chunking import CHUNK_SIZE, split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from retriever import QUESTIONS, TOP_K, make_retriever
from utils import print_retrieval
from vector_store import make_vector_store, store_vectors


# The tests pass a stand-in for Gemini as `embeddings`, with its vector size
def main(question: str = QUESTIONS[0], embeddings: Embeddings = embeddings, size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    vectors = embed_chunks(chunks, embeddings)     # one call to Gemini: every chunk's embedding
    print(f"Step 3: Embed: {len(vectors)} vectors of {len(vectors[0])} numbers")
    store = make_vector_store(embeddings, size)
    store_vectors(store, chunks, vectors)          # Step 3's vectors: no call to Gemini
    # count() comes from qdrant_client's QdrantClient: how many points the collection holds
    print(f"Step 4: Store: {store.client.count(store.collection_name).count} points, in Qdrant in memory")
    print("Step 5: Retrieve")
    # The question becomes a vector from the same model as the chunks, so the two can be compared (one call)
    # embed_query() comes from LangChain's Embeddings (Gemini's, here): one text in, one vector out
    question_vector = embeddings.embed_query(question)
    # similarity_search_with_score_by_vector() comes from langchain_qdrant's QdrantVectorStore: k closest, scored
    scored = store.similarity_search_with_score_by_vector(question_vector, k=TOP_K)
    # The retriever does both in one call (one more call to Gemini), without the scores
    # invoke() comes from LangChain's Runnable: the retriever embeds the question and searches, in one call
    found = make_retriever(store).invoke(question)
    # The top chunk's vector, read back from Qdrant by its point's id, so its score can be worked out by hand
    # langchain_qdrant puts each found point's id in the chunk's metadata, under "_id"
    # retrieve() comes from qdrant_client's QdrantClient: points by id, with their vectors when asked
    top_point = store.client.retrieve(store.collection_name, [scored[0][0].metadata["_id"]], with_vectors=True)[0]
    print_retrieval(question, question_vector, scored, found, top_point.vector)


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTIONS[0])
