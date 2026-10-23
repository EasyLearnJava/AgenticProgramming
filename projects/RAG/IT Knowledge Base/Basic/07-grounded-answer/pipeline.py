"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding and storing them in Qdrant, in memory (one call to Gemini)
  4. Step 4: retrieving the closest chunks and answering from them, in one chain (two calls), then printing the answer

Usage:
    python pipeline.py                          # the answer to the VPN question, and its sources
    python pipeline.py "my printer is missing"  # the answer to your question (3 calls to Gemini)
"""
import sys

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from chunking import CHUNK_SIZE, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import QUESTION, make_rag_chain
from retriever import make_retriever
from utils import print_answer
from vector_store import make_vector_store


# The tests pass stand-ins for Gemini as `embeddings` and `model`, with the embeddings' vector size
def main(question: str = QUESTION, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
         size: int = EMBEDDING_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    chunks = split_documents(docs)
    print(f"Step 2: Chunk: {len(chunks)} chunks of at most {CHUNK_SIZE} characters")
    store = make_vector_store(embeddings, size)
    # add_documents() comes from LangChain's VectorStore: it embeds the chunks, then stores them
    store.add_documents(chunks)                    # one call to Gemini: every chunk's embedding
    # count() comes from qdrant_client's QdrantClient: how many points the collection holds
    print(f"Step 3: Embed and store: {store.client.count(store.collection_name).count} points, in Qdrant in memory")
    print("Step 4: Retrieve and answer")
    chain = make_rag_chain(make_retriever(store), model)
    # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
    result = chain.invoke(question)                # retrieval, prompt and answer, all in this one call
    print_answer(question, result)


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTION)
