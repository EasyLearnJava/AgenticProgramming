"""
Tests for tuning.py: the test questions and their facts, the stores, the three searches and their scores, and the
answers for each k. The plain tests use stand-ins for Gemini (tests/fakes.py); the live test asks the real Gemini's
embedding model.
"""
import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings

import tuning
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from tuning import EVAL_SET, build_stores, evaluate, keyword_search, random_hit_chance, words

DOCS = {doc.metadata["title"]: doc for doc in load_documents()}
SMALL_SET = [("my vpn keeps dropping", "VPN Connection Timeout", "UDP 500 and 4500"),
             ("the printer is missing", "Printer Not Found", "10.50.3.25")]


def test_the_test_questions_cover_every_article_once():
    assert sorted(title for _, title, _ in EVAL_SET) == sorted(DOCS)


def test_each_fact_is_in_its_article_word_for_word():
    for _, title, fact in EVAL_SET:
        assert fact in DOCS[title].page_content


def test_no_question_uses_a_word_of_its_articles_title():
    for question, title, _ in EVAL_SET:
        assert not words(question) & words(title), question


def test_the_keyword_search_leaves_out_common_words():
    assert words("What's the IP address of the printer?") == {"ip", "address", "printer"}


def test_build_stores_embeds_each_chunk_size_once():
    stand_in = KeywordEmbeddings()
    stores = build_stores(stand_in, SIZE, chunk_sizes=[200, 1000])
    assert stand_in.calls == [("documents", 49), ("documents", 10)]
    assert {size: len(chunks) for size, (chunks, _) in stores.items()} == {200: 49, 1000: 10}


def test_evaluate_gives_three_searches_for_each_chunk_size_and_embeds_each_question_once():
    stand_in = KeywordEmbeddings()
    stores = build_stores(stand_in, SIZE, chunk_sizes=[200, 1000])
    rows = evaluate(stand_in, stores, eval_set=SMALL_SET, top_ks=[1, 3])
    assert [(row["chunk_size"], row["search"]) for row in rows] == [
        (200, "gemini"), (200, "keywords"), (200, "random"), (1000, "gemini"), (1000, "keywords"), (1000, "random")]
    assert stand_in.calls[2:] == [("query", "my vpn keeps dropping"), ("query", "the printer is missing")]
    for row in rows:
        assert 0 <= row["top_1"] <= row["top_3"] <= 2


def test_a_hit_needs_the_fact_not_just_the_article():
    stand_in = KeywordEmbeddings()
    stores = build_stores(stand_in, SIZE, chunk_sizes=[200])
    # A fact no chunk holds: the search can find the right article, and still never score
    rows = evaluate(stand_in, stores, eval_set=[("my vpn keeps dropping", "VPN Connection Timeout", "not there")],
                    top_ks=[5])
    assert [row["top_5"] for row in rows] == [0, 0, 0]
    # Its article is listed as missed, for Gemini's search
    assert [row.get("missed_in_top_1") for row in rows] == [["VPN Connection Timeout"], None, None]


def test_keyword_search_ranks_the_chunks_by_the_words_they_share_with_the_question():
    chunks, _ = build_stores(KeywordEmbeddings(), SIZE, chunk_sizes=[1000])[1000]
    assert keyword_search("ip address of the network printer", chunks, 1)[0].metadata["title"] == "Printer Not Found"


def test_random_hit_chance_is_the_share_of_chunks_luck_would_find():
    chunks, _ = build_stores(KeywordEmbeddings(), SIZE, chunk_sizes=[1000])[1000]   # 10 chunks, one per article
    assert random_hit_chance("10.50.3.25", chunks, 1) == pytest.approx(0.1)          # 1 chunk of 10 holds it
    assert random_hit_chance("10.50.3.25", chunks, 5) == pytest.approx(0.5)          # half of them: half the chance
    assert random_hit_chance("10.50.3.25", chunks, 10) == pytest.approx(1.0)


def test_compare_top_k_answers_the_question_once_for_each_k_from_the_same_store(monkeypatch):
    stand_in = KeywordEmbeddings()
    _, store = build_stores(stand_in, SIZE, chunk_sizes=[512])[512]
    monkeypatch.setattr(tuning, "chat_model", FakeListChatModel(responses=["the first answer", "the second answer"]))
    answers = tuning.compare_top_k("my vpn keeps dropping", store, top_ks=(1, 5))
    assert answers == {1: "the first answer", 5: "the second answer"}
    assert stand_in.calls[1:] == [("query", "my vpn keeps dropping")] * 2     # one search for each k, no new store


@pytest.mark.live
def test_live_at_512_gemini_beats_the_keywords_in_the_top_1_and_finds_most_facts_in_the_top_5():
    rows = evaluate(embeddings, build_stores(embeddings, EMBEDDING_SIZE, chunk_sizes=[512]))
    gemini, keywords = rows[0], rows[1]
    assert gemini["top_1"] > keywords["top_1"]
    assert gemini["top_5"] >= 8
