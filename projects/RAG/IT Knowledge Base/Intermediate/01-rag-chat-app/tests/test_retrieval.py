"""
Tests for src/retrieval/retriever.py: a LangChain retriever (invoke, ainvoke, batch) that finds the k closest chunks,
closest first, each with its score; the same chunks sync or async; and one span naming each chunk found, under the
question's trace ID even when the search runs in a worker thread.
"""
import asyncio

from fakes import SIZE, KeywordEmbeddings
from support import filled_store

from src.embeddings.embedder import Embedder
from src.observability.tracing import trace_context
from src.retrieval.retriever import KBRetriever


def make_retriever(k: int = 5) -> KBRetriever:
    return KBRetriever(embedder=Embedder(KeywordEmbeddings(), dimensions=SIZE, batch_size=100), store=filled_store(),
                       k=k)


def test_invoke_gives_the_k_closest_chunks_closest_first_with_scores():
    chunks = make_retriever().invoke("My VPN won't connect")
    assert len(chunks) == 5
    assert chunks[0].metadata["title"] == "VPN Connection Timeout"
    scores = [chunk.metadata["score"] for chunk in chunks]
    assert scores == sorted(scores, reverse=True)


def test_k_sets_how_many_come_back():
    assert len(make_retriever(k=2).invoke("My VPN won't connect")) == 2


def test_ainvoke_finds_the_same_chunks():
    retriever = make_retriever()
    sync = retriever.invoke("the printer is missing")
    assert [chunk.page_content for chunk in asyncio.run(retriever.ainvoke("the printer is missing"))] == [
        chunk.page_content for chunk in sync]


def test_batch_answers_each_question_in_order():
    results = make_retriever().batch(["my vpn drops", "the printer is missing"])
    assert [chunks[0].metadata["title"] for chunks in results] == ["VPN Connection Timeout", "Printer Not Found"]


def test_one_span_names_each_chunk_found_with_its_score(logs):
    chunks = make_retriever().invoke("My VPN won't connect")
    record = logs.find("retrieval.retrieve ok")
    assert record.found == [f"{chunk.metadata['doc_id']}#{chunk.metadata['chunk_index']}" for chunk in chunks]
    assert record.scores == [round(chunk.metadata["score"], 4) for chunk in chunks]
    found = [line for line in logs.records if line.getMessage() == "Chunk found"]       # DEBUG: one per chunk
    assert [line.title for line in found] == [chunk.metadata["title"] for chunk in chunks]


def test_the_async_search_logs_under_the_questions_trace_id(logs):
    retriever = make_retriever()
    with trace_context() as trace_id:
        asyncio.run(retriever.ainvoke("My VPN won't connect"))
    search = logs.find("vectordb.search ok")          # written in a worker thread
    assert search.trace_id == logs.find("retrieval.retrieve ok").trace_id == trace_id
