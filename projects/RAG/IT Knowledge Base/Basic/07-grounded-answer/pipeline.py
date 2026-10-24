"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base into Documents
  2. Step 2: cutting them into chunks
  3. Step 3: embedding them (one call to Gemini)
  4. Step 4: storing them in Qdrant, in memory, with their vectors
  5. Step 5: retrieving the closest chunks and answering from them, in one chain (two calls), then printing the
     prompt Gemini got, the answer and the sources
  6. Then, for comparison, the same question to Gemini alone, with no articles (one more call)

Usage:
    python pipeline.py                          # a question only this knowledge base can answer, both ways
    python pipeline.py "my printer is missing"  # your question, both ways (4 calls to Gemini)
"""
import sys

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from chunking import CHUNK_SIZE, split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain, prompt
from retriever import format_docs, make_retriever
from utils import print_answer, print_answer_alone
from vector_store import make_vector_store, store_vectors

# Only this knowledge base knows the answer: the WiFi article's notes say Building C's upgrade is due in Q2
QUESTION = "When will the access points in Building C be upgraded?"


# The tests pass stand-ins for Gemini as `embeddings` and `model`, with the embeddings' vector size
def main(question: str = QUESTION, embeddings: Embeddings = embeddings, model: BaseChatModel = chat_model,
         size: int = EMBEDDING_SIZE) -> None:
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
    print("Step 5: Retrieve and answer")
    chain = make_rag_chain(make_retriever(store), model)
    # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
    result = chain.invoke(question)                # retrieval, prompt and answer, all in this one call
    # What Gemini got: the chain's own prompt, filled in with the chunks it found and the question
    # format_messages() comes from LangChain's ChatPromptTemplate: the prompt's messages, filled in
    messages = prompt.format_messages(context=format_docs(result["docs"]), question=question)
    print_answer(question, messages, result)
    # For comparison: the same question to Gemini alone, with no retriever and no articles (one more call)
    # StrOutputParser comes from langchain_core: it turns the model's reply into plain text
    print_answer_alone((model | StrOutputParser()).invoke(question))


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or QUESTION)
