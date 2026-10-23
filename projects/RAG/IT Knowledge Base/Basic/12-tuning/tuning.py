"""
IT Knowledge Base: Tuning
=========================

Scores the search for different chunk sizes and numbers of chunks (k): for each of 10 test questions, does the search
find the article that answers it? It handles:
  1. The scores: one row per chunk size, counting the questions whose article is among the 1, 3 and 5 closest chunks
  2. The table of those scores, printed by print_table() (utils.py)
  3. With --answers, one question answered from 1 chunk and from 5, to compare the answers

Everything runs in memory apart from the calls to Gemini: the chunks in qdrant_data/ aren't used or changed.

Usage:
    python tuning.py              # the table (13 calls to Gemini's embedding model)
    python tuning.py --answers    # the table, then one question answered from 1 chunk and from 5
"""
import sys

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import make_retriever
from utils import print_table
from vector_store import make_vector_store

# Each question with the title of the article that answers it, avoiding the articles' own words where they can
# ("sluggish", not "slow"), so a good score means the search matched meanings, not words
EVAL_SET = [
    ("My VPN keeps dropping when I work from home", "VPN Connection Timeout"),
    ("The authenticator app on my phone won't finish setting up", "MFA Setup Failure"),
    ("Everything on my computer is really sluggish", "Laptop Performance Degradation"),
    ("I get access denied when I open Salesforce", "SaaS Access Permission Denied"),
    ("The wireless in the office keeps disconnecting", "WiFi Connectivity Issues Office"),
    ("I can't change my password", "Password Reset Failed"),
    ("My computer can't see the printer", "Printer Not Found"),
    ("My email bounced because the file was too big", "Email Attachment Size Limit"),
    ("Our app can't reach the database", "Database Connection Timeout"),
    ("Nobody can hear me in Teams calls", "Microsoft Teams Audio Issues"),
]
CHUNK_SIZES = [200, 512, 1000]       # small, the usual size, and big enough to keep every article whole
TOP_KS = [1, 3, 5]                   # how many chunks a search returns


def evaluate(embeddings: Embeddings, size: int, eval_set=EVAL_SET, chunk_sizes=CHUNK_SIZES,
             top_ks=TOP_KS) -> list[dict]:
    """One row of scores per chunk size, e.g. {"chunk_size": 200, "chunks": 49, "top_1": 8, "top_3": 10, ...}."""
    # The questions are embedded once and reused; each chunk size gets its own in-memory store (one call each)
    # embed_query() comes from LangChain's Embeddings (Gemini's, here): one text in, one vector out
    question_vectors = [embeddings.embed_query(question) for question, _ in eval_set]
    rows = []
    for chunk_size in chunk_sizes:
        chunks = split_documents(load_documents(), chunk_size, min(CHUNK_OVERLAP, chunk_size // 4))
        # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
        store = make_vector_store(embeddings, size, QdrantClient(":memory:"))
        # add_documents() comes from LangChain's VectorStore: it embeds the chunks, then stores them
        store.add_documents(chunks)
        # One search per question for the most chunks needed; its first 1, 3 and 5 are checked
        # similarity_search_by_vector() comes from langchain_qdrant's QdrantVectorStore: the k closest chunks
        found = [[doc.metadata["title"] for doc in store.similarity_search_by_vector(vector, k=max(top_ks))]
                 for vector in question_vectors]
        row = {"chunk_size": chunk_size, "chunks": len(chunks)}
        for k in top_ks:
            row[f"top_{k}"] = sum(expected in titles[:k] for (_, expected), titles in zip(eval_set, found))
        rows.append(row)
    return rows


def compare_top_k(question: str, top_ks=(1, 5)) -> dict[int, str]:
    """The same question answered once for each k: with 1 chunk the model may miss part of the fix."""
    # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
    store = make_vector_store(embeddings, EMBEDDING_SIZE, QdrantClient(":memory:"))
    # add_documents() comes from LangChain's VectorStore: it embeds the chunks, then stores them
    store.add_documents(split_documents(load_documents()))
    # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
    return {k: make_rag_chain(make_retriever(store, k), chat_model).invoke(question)["answer"] for k in top_ks}


if __name__ == "__main__":
    print(f"{len(EVAL_SET)} questions, each with the article that answers it.\n")
    print_table(evaluate(embeddings, EMBEDDING_SIZE), len(EVAL_SET))
    if "--answers" in sys.argv[1:]:
        question = EVAL_SET[0][0]
        for k, answer in compare_top_k(question).items():
            print(f"\n--- {question!r}, answered from {k} chunk{'s' if k > 1 else ''}:")
            print(answer)
