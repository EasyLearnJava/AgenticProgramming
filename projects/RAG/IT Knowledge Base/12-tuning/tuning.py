"""
Tuning: the same questions searched with different chunk sizes and numbers of chunks (k), scored by whether the
search finds the article that answers each question. Then, with --answers, one question answered with 1 chunk and with
5 chunks as its articles, to see what the number of chunks does to the answer.

    evaluate(embeddings, EMBEDDING_SIZE)
        ->  one row per chunk size: {"chunk_size": 200, "chunks": 49, "top_1": 8, "top_3": 10, "top_5": 10}
            top_3 = how many of the 10 questions found their article among the 3 closest chunks
            (made-up numbers: Gemini's embeddings decide the real ones)

Run it on its own:   python tuning.py             ->   the table: 13 calls to Gemini's embedding model
                     python tuning.py --answers   ->   the table, then one question answered with 1 chunk and with 5:
                                                       2 calls to the chat model, and 3 more to the embedding model
                                                       (the chunks once, the question for each answer)
Everything here runs in memory, apart from the calls to Gemini: the Qdrant server isn't used or changed.
"""
import sys

from langchain_core.embeddings import Embeddings
from qdrant_client import QdrantClient

from chunking import CHUNK_OVERLAP, split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain
from retriever import make_retriever
from vector_store import make_vector_store

# ① The test questions, each with the title of the article that answers it. They avoid the articles' own words where
#    they can ("sluggish", not "slow"), so a good score means the search matched meanings, not words.
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
CHUNK_SIZES = [200, 512, 1000]       # small, step 03's size, and big enough to keep every article whole
TOP_KS = [1, 3, 5]                   # how many chunks a search returns


# ② The scores for each chunk size. The questions are embedded once (10 calls) and their vectors reused; each chunk
#    size gets its own in-memory store, filled with that size's chunks (one call each). Each question then searches
#    once for the most chunks needed (5), and the first 1, 3 and 5 of them are checked for the right article.
def evaluate(embeddings: Embeddings, size: int, eval_set=EVAL_SET, chunk_sizes=CHUNK_SIZES,
             top_ks=TOP_KS) -> list[dict]:
    question_vectors = [embeddings.embed_query(question) for question, _ in eval_set]
    rows = []
    for chunk_size in chunk_sizes:
        chunks = split_documents(load_documents(), chunk_size, min(CHUNK_OVERLAP, chunk_size // 4))
        store = make_vector_store(embeddings, size, QdrantClient(":memory:"))
        store.add_documents(chunks)
        found = [[doc.metadata["title"] for doc in store.similarity_search_by_vector(vector, k=max(top_ks))]
                 for vector in question_vectors]
        row = {"chunk_size": chunk_size, "chunks": len(chunks)}
        for k in top_ks:
            row[f"top_{k}"] = sum(expected in titles[:k] for (_, expected), titles in zip(eval_set, found))
        rows.append(row)
    return rows


# ③ The table, one line per chunk size.
def print_table(rows: list[dict], total: int) -> None:
    keys = [key for key in rows[0] if key.startswith("top_")]
    print("chunk size  chunks  " + "  ".join(f"found in {key.replace('_', ' ')}" for key in keys))
    for row in rows:
        cells = "  ".join(f"{row[key]:>2} of {total:<6}" for key in keys)
        print(f"{row['chunk_size']:>10}  {row['chunks']:>6}  {cells}")


# ④ The number of chunks the model gets: the same question answered once for each k, with step 03's chunk size. With
#    1 chunk the model may miss part of the fix; with more, it has more to go on, and more to sort through.
def compare_top_k(question: str, top_ks=(1, 5)) -> dict[int, str]:
    store = make_vector_store(embeddings, EMBEDDING_SIZE, QdrantClient(":memory:"))
    store.add_documents(split_documents(load_documents()))
    return {k: make_rag_chain(make_retriever(store, k), chat_model).invoke(question)["answer"] for k in top_ks}


if __name__ == "__main__":
    print(f"{len(EVAL_SET)} questions, each with the article that answers it.\n")
    print_table(evaluate(embeddings, EMBEDDING_SIZE), len(EVAL_SET))
    if "--answers" in sys.argv[1:]:
        question = EVAL_SET[0][0]
        for k, answer in compare_top_k(question).items():
            print(f"\n--- {question!r}, answered from {k} chunk{'s' if k > 1 else ''}:")
            print(answer)
