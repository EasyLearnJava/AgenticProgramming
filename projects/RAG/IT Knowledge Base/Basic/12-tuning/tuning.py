"""
IT Knowledge Base: Tuning
=========================

Scores the search for different chunk sizes and numbers of chunks (k): for each of 10 test questions, do the chunks
found hold the fact a good answer needs? Gemini's search races two that make no calls, so its scores mean something.
It handles:
  1. The stores: for each chunk size, the chunks embedded (one call to Gemini) and stored in memory
  2. The scores: for each chunk size, the questions whose fact is in the 1, 3 and 5 chunks found, by three searches:
     Gemini's embeddings, the question's own words (keywords), and a random order (what luck finds, on average)
  3. The table of those scores, printed by print_table() (utils.py)
  4. With --answers, one question answered from 1 chunk and from 5, to compare the answers

Everything runs in memory apart from the calls to Gemini: the chunks in qdrant_data/ aren't used or changed.

Usage:
    python tuning.py              # the table (13 calls to Gemini, embedding 97 texts)
    python tuning.py --answers    # the table, then one question answered from 1 chunk and from 5 (17 calls, 99 texts)
"""
import math
import re
import sys

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import make_retriever
from utils import print_table
from vector_store import make_vector_store, store_vectors

# Each question, the title of the article that answers it, and the fact a good answer needs, word for word as the
# article has it. No question uses a word of its article's title, so a good score means the search matched meanings,
# not words. Two are near-misses: VPN and Database both have "Connection Timeout" in their titles and "peak hours"
# in their text.
EVAL_SET = [
    ("Which ports must be open for me to reach the office network from home?", "VPN Connection Timeout",
     "UDP 500 and 4500"),
    ("The sign-in code app on my phone won't finish enrolling: what's the usual cause?", "MFA Setup Failure",
     "Time synchronization"),
    ("My new computer is crawling and programs keep hanging: how much free disk space does it need?",
     "Laptop Performance Degradation", "15% free"),
    ("After my job changed I'm locked out of our CRM: how long until it works?", "SaaS Access Permission Denied",
     "30 minutes"),
    ("When are the wireless hubs in Building C being replaced?", "WiFi Connectivity Issues Office", "upgrade Q2"),
    ("How long must a new sign-in passphrase be?", "Password Reset Failed", "12 chars"),
    ("What's the IP address of the colour device on floor 3?", "Printer Not Found", "10.50.3.25"),
    ("What's the largest file I can send to someone outside the company?", "Email Attachment Size Limit", "25MB"),
    ("When are the busiest hours for our production data server?", "Database Connection Timeout", "9-11 AM"),
    ("Nobody can hear me on video calls since an update: which cache folder should I clear?",
     "Microsoft Teams Audio Issues", "%appdata%"),
]
CHUNK_SIZES = [200, 512, 1000]       # small, the usual size, and big enough to keep every article whole
TOP_KS = [1, 3, 5]                   # how many chunks a search returns
SEARCHES = ["gemini", "keywords", "random"]


def build_stores(embeddings: Embeddings, size: int,
                 chunk_sizes=CHUNK_SIZES) -> dict[int, tuple[list[Document], QdrantVectorStore]]:
    """For each chunk size, its chunks, embedded (one call to Gemini) and stored in their own in-memory store."""
    stores = {}
    for chunk_size in chunk_sizes:
        chunks = split_documents(load_documents(), chunk_size, min(CHUNK_OVERLAP, chunk_size // 4))
        vectors = embed_chunks(chunks, embeddings)                # one call to Gemini: every chunk's embedding
        # QdrantClient comes from qdrant_client: ":memory:" runs Qdrant inside this program, in memory
        store = make_vector_store(embeddings, size, QdrantClient(":memory:"))
        store_vectors(store, chunks, vectors)
        stores[chunk_size] = (chunks, store)
    return stores


def words(text: str) -> set[str]:
    """A text's words, in lower case: what the keyword search compares."""
    # findall() comes from Python's re module: every run of letters and digits in the text
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def keyword_search(question: str, chunks: list[Document], k: int) -> list[Document]:
    """The k chunks that share the most words with the question: a search with no embeddings and no calls."""
    # sorted() keeps the chunks' own order among equal counts, so the result is the same every time
    return sorted(chunks, key=lambda chunk: len(words(question) & words(chunk.page_content)), reverse=True)[:k]


def random_hit_chance(fact: str, chunks: list[Document], k: int) -> float:
    """The chance that k chunks picked at random include one holding the fact: what luck alone finds, on average."""
    holding = sum(fact in chunk.page_content for chunk in chunks)
    # comb() comes from Python's math module: how many ways to pick k of n. The chance of missing every chunk that
    # holds the fact is the ways to pick k from the others, divided by all the ways to pick k.
    return 1 - math.comb(len(chunks) - holding, k) / math.comb(len(chunks), k)


def evaluate(embeddings: Embeddings, stores: dict, eval_set=EVAL_SET, top_ks=TOP_KS) -> list[dict]:
    """Three rows of scores per chunk size, one for each search, e.g. {"chunk_size": 512, "chunks": 28,
    "search": "gemini", "top_1": 6, "top_3": 8, "top_5": 9}: the questions whose fact is in the k chunks found."""
    # The questions are embedded once and reused for every chunk size
    # embed_query() comes from LangChain's Embeddings (Gemini's, here): one text in, one vector out
    question_vectors = [embeddings.embed_query(question) for question, _, _ in eval_set]
    rows = []
    for chunk_size, (chunks, store) in stores.items():
        # One search per question for the most chunks needed; its first 1, 3 and 5 are checked
        # similarity_search_by_vector() comes from langchain_qdrant's QdrantVectorStore: the k closest chunks
        found = {"gemini": [store.similarity_search_by_vector(vector, k=max(top_ks)) for vector in question_vectors],
                 "keywords": [keyword_search(question, chunks, max(top_ks)) for question, _, _ in eval_set]}
        for search in SEARCHES:
            row = {"chunk_size": chunk_size, "chunks": len(chunks), "search": search}
            for k in top_ks:
                if search == "random":
                    row[f"top_{k}"] = round(sum(random_hit_chance(fact, chunks, k) for _, _, fact in eval_set), 1)
                else:
                    row[f"top_{k}"] = sum(any(fact in chunk.page_content for chunk in results[:k])
                                          for (_, _, fact), results in zip(eval_set, found[search]))
            rows.append(row)
    return rows


def compare_top_k(question: str, store: QdrantVectorStore, top_ks=(1, 5)) -> dict[int, str]:
    """The same question answered once for each k, from the same store: with 1 chunk the model may miss the fact."""
    # invoke() comes from LangChain's Runnable: it runs the whole chain on one input
    return {k: make_rag_chain(make_retriever(store, k), chat_model).invoke(question)["answer"] for k in top_ks}


if __name__ == "__main__":
    print(f"{len(EVAL_SET)} questions, each with the fact a good answer needs.\n")
    stores = build_stores(embeddings, EMBEDDING_SIZE)
    print_table(evaluate(embeddings, stores), len(EVAL_SET))
    if "--answers" in sys.argv[1:]:
        question = EVAL_SET[1][0]          # MFA: the cause is in the notes, after the fix's 7 steps
        for k, answer in compare_top_k(question, stores[512][1]).items():
            print(f"\n--- {question!r}, answered from {k} chunk{'s' if k > 1 else ''}:")
            print(answer)
