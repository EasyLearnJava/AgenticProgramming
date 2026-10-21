"""
IT Knowledge Base: The Retriever
================================

Finds the chunks closest to a question: the question is embedded with the same model as the chunks, and Qdrant
gives back the closest ones. It handles:
  1. Making a retriever that embeds and searches in one call, and returns TOP_K chunks
  2. Turning the chunks into one numbered, titled text for a prompt
  3. Printing a search: the question's vector, the closest chunks with their scores, and what a prompt gets

Usage (this file only defines these; pipeline.py runs the steps):
    retriever = make_retriever(store)   ->  a Runnable: retriever.invoke(question) gives the TOP_K closest chunks
    format_docs(chunks)                 ->  the chunks as one text for a prompt, each numbered and titled
"""
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_qdrant import QdrantVectorStore

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


def print_retrieval(question: str, question_vector: list[float], scored: list[tuple[Document, float]],
                    chunks: list[Document]) -> None:
    """Print the question's vector, the closest chunks with their scores, the retriever's chunks, and the prompt."""
    print(f"Question: {question}")
    start = ", ".join(f"{x:.4f}" for x in question_vector[:5])
    print(f"The question became {len(question_vector)} numbers: [{start}, ...]")
    # The score is the cosine similarity, from -1 to 1; the closer to 1, the closer the meaning
    print(f"\nThe {len(scored)} closest chunks, with their scores, closest first:")
    for chunk, score in scored:
        print(f"  {score:.3f}  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print("\nThe retriever, embedding and searching in one call, found:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print("\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):")
    print(format_docs(chunks[:2]))
