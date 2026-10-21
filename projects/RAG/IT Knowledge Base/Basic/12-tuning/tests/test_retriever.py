"""
Tests for retriever.py: the question's vector searched in the store, the retriever as a Runnable (invoke, batch, k),
the chunks formatted for a prompt, and what the script does. The plain tests use KeywordEmbeddings, a stand-in for
Gemini (tests/fakes.py); the live test asks the real Gemini.
"""
import runpy
import sys
from pathlib import Path

import pytest
from fakes import SIZE, KeywordEmbeddings

import models
from models import EMBEDDING_SIZE, embeddings
from retriever import QUESTIONS, TOP_K, format_docs, make_retriever
from vector_store import add_knowledge_base, make_vector_store

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def filled_store(stand_in=None):
    store = make_vector_store(stand_in or KeywordEmbeddings(), SIZE)
    add_knowledge_base(store)
    return store


def test_searching_with_the_questions_vector_gives_the_closest_chunks_and_scores():
    stand_in = KeywordEmbeddings()
    store = filled_store(stand_in)
    question_vector = stand_in.embed_query("My VPN won't connect")
    results = store.similarity_search_with_score_by_vector(question_vector, k=TOP_K)
    assert len(results) == 5
    assert results[0][0].metadata["title"] == "VPN Connection Timeout"
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(results[0][0].metadata)


def test_invoke_gives_the_k_closest_chunks_closest_first():
    assert TOP_K == 5
    chunks = make_retriever(filled_store()).invoke("My VPN won't connect")
    assert len(chunks) == 5
    assert chunks[0].metadata["title"] == "VPN Connection Timeout"


def test_the_retriever_finds_the_same_chunks_as_the_search_by_hand():
    stand_in = KeywordEmbeddings()
    store = filled_store(stand_in)
    by_hand = store.similarity_search_with_score_by_vector(stand_in.embed_query("the printer is missing"), k=TOP_K)
    found = make_retriever(store).invoke("the printer is missing")
    assert [chunk.page_content for chunk in found] == [chunk.page_content for chunk, _ in by_hand]


def test_k_sets_how_many_chunks_come_back():
    assert len(make_retriever(filled_store(), k=2).invoke("My VPN won't connect")) == 2


def test_batch_answers_each_question_in_order_with_one_query_call_each():
    stand_in = KeywordEmbeddings()
    results = make_retriever(filled_store(stand_in)).batch(["my vpn drops", "the printer is missing"])
    assert [chunks[0].metadata["title"] for chunks in results] == ["VPN Connection Timeout", "Printer Not Found"]
    assert sorted(call for call in stand_in.calls if call[0] == "query") == [("query", "my vpn drops"),
                                                                            ("query", "the printer is missing")]


def test_format_docs_numbers_and_titles_each_chunk():
    chunks = make_retriever(filled_store()).invoke("My VPN won't connect")[:2]
    text = format_docs(chunks)
    assert text.startswith("[1] VPN Connection Timeout\n" + chunks[0].page_content)
    assert f"\n\n[2] {chunks[1].metadata['title']}\n{chunks[1].page_content}" in text


def test_running_it_embeds_the_chunks_then_the_question_by_hand_then_through_the_retriever(monkeypatch, capsys):
    stand_in = KeywordEmbeddings()
    monkeypatch.setattr(models, "embeddings", stand_in)       # the script's `from models import ...` gets these
    monkeypatch.setattr(models, "EMBEDDING_SIZE", SIZE)
    monkeypatch.setattr(sys, "argv", ["retriever.py"])
    runpy.run_path(str(FOLDER / "retriever.py"), run_name="__main__")
    printed = capsys.readouterr().out
    question = QUESTIONS[0]
    assert stand_in.calls == [("documents", 28), ("query", question), ("query", question)]
    assert printed.startswith(f"Question: {question}\nThe question became {SIZE} numbers: [")
    assert "\n\nThe 5 closest chunks, with their scores, closest first:\n" in printed
    assert "\n\nThe retriever, embedding and searching in one call, found:\n" in printed
    assert "\n\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):\n[1] " in printed


@pytest.mark.live
def test_live_the_sample_questions_find_their_articles():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    results = make_retriever(store).batch(QUESTIONS)
    assert [chunks[0].metadata["title"] for chunks in results] == [
        "VPN Connection Timeout", "MFA Setup Failure", "Laptop Performance Degradation"]
