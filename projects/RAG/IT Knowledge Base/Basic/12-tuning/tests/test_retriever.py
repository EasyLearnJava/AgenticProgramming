"""
Tests for retriever.py: the question's vector searched in the store, the retriever as a Runnable (invoke, batch, k),
and the chunks formatted for a prompt. The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py);
the live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from retriever import QUESTIONS, TOP_K, format_docs, make_retriever
from vector_store import make_vector_store, store_vectors

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def filled_store(stand_in=None):
    store = make_vector_store(stand_in or KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
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


@pytest.mark.live
def test_live_the_sample_questions_find_their_articles():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store_vectors(store, CHUNKS, embed_chunks(CHUNKS, embeddings))
    results = make_retriever(store).batch(QUESTIONS)
    assert [chunks[0].metadata["title"] for chunks in results] == [
        "VPN Connection Timeout", "MFA Setup Failure", "Laptop Performance Degradation"]
