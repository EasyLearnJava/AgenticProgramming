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

TOP_K = 5      # how many chunks each search returns
QUESTIONS = [  # the course app's sample questions
    "How do I fix VPN connection timeouts?",
    "I can't set up MFA on my mobile device",
    "My laptop is running very slow",
]


def make_retriever(store: QdrantVectorStore, k: int = TOP_K) -> VectorStoreRetriever:
    """A retriever whose every invoke() returns the k closest chunks."""
    # as_retriever() comes from LangChain's VectorStore: a retriever that searches this store
    return store.as_retriever(search_kwargs={"k": k})

    # Other ways to search, off for now: to try one, comment out the return above and uncomment one below.
    # None of them checks that a chunk answers the question: each only changes which close chunks come back.
    #
    # 1. A minimum score: drops chunks that aren't close enough, so a question the articles don't cover gets fewer
    #    than k chunks, or none. score_threshold isn't the cosine pipeline.py prints: LangChain turns the cosine
    #    into (cosine + 1) / 2, so 0.8 keeps chunks with a cosine of 0.6 or more.
    # return store.as_retriever(search_type="similarity_score_threshold",
    #                           search_kwargs={"k": k, "score_threshold": 0.8})
    #
    # 2. MMR (maximal marginal relevance): takes the 20 closest chunks, then picks k that are close to the question
    #    and different from each other, so near-copies don't fill every place. lambda_mult=1 is closeness only.
    # return store.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": 20, "lambda_mult": 0.5})
    #
    # 3. A filter: searches only the chunks with one label, here the "Remote Access" category. It needs
    #    `from qdrant_client import models`; each point keeps its labels under "metadata".
    # return store.as_retriever(search_kwargs={"k": k, "filter": models.Filter(must=[models.FieldCondition(
    #     key="metadata.category", match=models.MatchValue(value="Remote Access"))])})


def format_docs(docs: list[Document]) -> str:
    """The chunks as one text for a prompt, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {doc.metadata['title']}\n{doc.page_content}" for number, doc in enumerate(docs, 1))
