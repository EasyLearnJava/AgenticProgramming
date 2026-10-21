"""
IT Knowledge Base: The Retriever
================================

Finds the chunks closest to a question: the question is embedded with the same model as the chunks, and Qdrant
gives back the closest ones. It handles:
  1. Making a retriever that embeds and searches in one call, and returns TOP_K chunks
  2. Turning the chunks into one numbered, titled text for a prompt

Usage:
    python retriever.py                      # each step for "How do I fix VPN connection timeouts?"
    python retriever.py "my email bounced"   # each step for your question (3 calls to Gemini)
"""
import sys

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_qdrant import QdrantVectorStore

from models import EMBEDDING_SIZE, embeddings
from vector_store import add_knowledge_base, make_vector_store

TOP_K = 5      # how many chunks each search returns
QUESTIONS = [  # the course app's sample questions
    "How do I fix VPN connection timeouts?",
    "I can't set up MFA on my mobile device",
    "My laptop is running very slow",
]


def make_retriever(store: QdrantVectorStore, k: int = TOP_K) -> VectorStoreRetriever:
    """A retriever whose every invoke() returns the k closest chunks."""
    return store.as_retriever(search_kwargs={"k": k})


def format_docs(docs: list[Document]) -> str:
    """The chunks as one text for a prompt, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or QUESTIONS[0]
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)                    # the 28 chunks embedded and stored (one call)
    print(f"Question: {question}")
    # The question becomes a vector from the same model as the chunks, so the two can be compared (one call)
    question_vector = embeddings.embed_query(question)
    start = ", ".join(f"{x:.4f}" for x in question_vector[:5])
    print(f"The question became {len(question_vector)} numbers: [{start}, ...]")
    # The search: the score is the cosine similarity, from -1 to 1; the closer to 1, the closer the meaning
    print(f"\nThe {TOP_K} closest chunks, with their scores, closest first:")
    for chunk, score in store.similarity_search_with_score_by_vector(question_vector, k=TOP_K):
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    # The retriever does both steps in one call (one more call to Gemini), without the scores
    chunks = make_retriever(store).invoke(question)
    print("\nThe retriever, embedding and searching in one call, found:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print("\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):")
    print(format_docs(chunks[:2]))
