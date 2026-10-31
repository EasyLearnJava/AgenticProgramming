"""
Tests for retriever.py, on Qdrant in memory with the sample's 39 chunks and a stand-in model whose vectors mean
something (tests/fakes.py KeywordEmbeddings): the question cleaned and its filters read; a filter keeps the search to
its label; hybrid search finds an error code and a meaning; an off-topic question gets "no match" below the
threshold; no more chunks from one article than allowed; a re-ranker reorders; a repeated question's vector comes
from the cache; rewrites are each searched and fused; and it plugs into LangChain as a retriever.
"""
import sys

import pytest
from fakes import KeywordEmbeddings
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from support import SPELLINGS
from support import keyword_retriever as retriever

from embedding import EmbeddingCache
from retriever import (
    CrossEncoderReranker,
    RetrievalError,
    WordOverlapReranker,
    clean_question,
    read_filters,
)


def titles(result) -> list[str]:
    return [doc.metadata["title"] for doc in result.docs]


# -------------------------------------------------
# The Question
# -------------------------------------------------

def test_a_question_is_cleaned_of_extra_spaces_and_repeated_marks():
    assert clean_question("  vpn   wont   work??? !!") == "vpn wont work? !"


@pytest.mark.parametrize("question, filters", [
    ("VPN problems with High priority", {"system": "VPN", "priority": "High"}),
    ("Wi-Fi drops in the meeting room", {"system": "WiFi"}),
    ("Can't change my Active Directory password", {"system": "Active Directory"}),
    ("priority: critical, the database is down", {"system": "Database", "priority": "Critical"}),
    ("VPN on my laptop keeps dropping", {}),                       # two systems named: neither is used
    ("High CPU usage makes everything lag", {}),                   # "high", but not next to "priority"
    ("I can't find the network printer", {"system": "Printer"}),   # categories ("Network") are never read
], ids=["system and priority", "another spelling", "two words", "priority first", "two systems", "not a priority",
        "no category"])
def test_filters_are_read_from_the_question(question, filters):
    assert read_filters(question, SPELLINGS) == filters


# -------------------------------------------------
# Searching
# -------------------------------------------------

def test_it_is_a_langchain_retriever():
    found = retriever(k=3)
    assert isinstance(found, BaseRetriever)
    docs = found.invoke("My VPN keeps timing out")             # filtered on VPN: 3 chunks, at most 2 from one article
    assert len(docs) == 2 and isinstance(docs[0], Document) and docs[0].metadata["title"] == "VPN Connection Timeout"


def test_a_filter_read_from_the_question_keeps_the_search_to_its_label():
    result = retriever().search("VPN problems with High priority")
    assert result.filters == {"system": "VPN", "priority": "High"}
    assert set(titles(result)) == {"VPN Connection Timeout"} and result.candidates == 3


def test_filters_passed_in_are_used_instead():
    result = retriever().search("my laptop is slow", filters={"system": "WiFi"})
    assert set(titles(result)) == {"WiFi Connectivity Issues Office"}


def test_hybrid_search_finds_an_exact_error_code_that_dense_search_misses():
    # The keyword stand-in knows nothing of the code, as a meaning-based model may not: the sparse search brings it
    assert "Password Reset Failed" not in titles(retriever(mode="dense").search("I get error 0x80070005"))
    found = [doc for doc in retriever().search("I get error 0x80070005").docs
             if doc.metadata["title"] == "Password Reset Failed"]
    assert found and found[0].metadata["score_sparse"] > 0


def test_dense_search_finds_by_the_vectors_alone():
    result = retriever(mode="dense").search("database timeout in the morning")
    assert titles(result)[0] == "Database Connection Timeout"
    assert all(doc.metadata["score_sparse"] is None for doc in result.docs)


def test_sparse_search_makes_no_call_to_the_model():
    model = KeywordEmbeddings()
    result = retriever(mode="sparse", embeddings=model).search("Outlook says Message Size Exceeded")
    assert titles(result)[0] == "Email Attachment Size Limit" and model.calls == []


def test_an_off_topic_question_gets_no_match_below_the_threshold():
    strict = retriever(min_score=0.3)
    off_topic = strict.search("What's on the cafeteria menu today?")
    assert off_topic.no_match and off_topic.docs == [] and off_topic.best_score < 0.3
    on_topic = strict.search("My VPN keeps timing out")
    assert not on_topic.no_match and on_topic.best_score >= 0.3


def test_a_question_sharing_no_word_with_any_chunk_finds_nothing_in_sparse_mode():
    result = retriever(mode="sparse").search("Kiwi smoothie recipes?")
    assert result.no_match and result.candidates == 0


def test_no_more_chunks_from_one_article_than_allowed():
    result = retriever(k=5, max_per_article=1).search("timeout")
    doc_ids = [doc.metadata["doc_id"] for doc in result.docs]
    assert len(doc_ids) == len(set(doc_ids))
    two = retriever(k=5, max_per_article=2).search("timeout")
    assert max(map([doc.metadata["doc_id"] for doc in two.docs].count, set(doc_ids))) <= 2


def test_only_the_k_best_are_returned_each_with_its_scores():
    result = retriever(k=2).search("My VPN keeps timing out")
    assert len(result.docs) == 2
    assert {"score_dense", "score_sparse", "score_fused", "score_rerank"} <= set(result.docs[0].metadata)


# -------------------------------------------------
# Re-ranking
# -------------------------------------------------

class PreferNotes:
    """A stand-in re-ranker: a chunk of the Notes section first."""
    name = "prefer-notes"

    def build(self) -> None:
        pass

    def score(self, question, texts):
        return [1.0 if "\nNotes: " in text else 0.0 for text in texts]


def test_a_reranker_reorders_the_candidates():
    result = retriever(reranker=PreferNotes()).search("My VPN keeps timing out")
    assert result.docs[0].metadata["section"] == "notes" and result.docs[0].metadata["score_rerank"] == 1.0


def test_the_word_overlap_reranker_scores_shared_rare_words_higher():
    scores = WordOverlapReranker().score("printer reimaging", ["the printer after reimaging", "the printer", "audio"])
    assert scores[0] > scores[1] > scores[2] == 0


def test_the_cross_encoder_says_how_to_install_it_when_its_package_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)     # the import fails, as if not installed
    with pytest.raises(RetrievalError, match="pip install sentence-transformers"):
        retriever(reranker=CrossEncoderReranker()).build()


# -------------------------------------------------
# The Question Cache and Rewrites
# -------------------------------------------------

def test_a_repeated_question_takes_its_vector_from_the_cache(tmp_path):
    model = KeywordEmbeddings()
    cache = EmbeddingCache(tmp_path / "cache.sqlite3", model="fake/keywords#query", dimensions=model.dimensions)
    first = retriever(embeddings=model, query_cache=cache).search("My VPN keeps timing out")
    again = retriever(embeddings=model, query_cache=cache).search("My  VPN keeps timing out")   # cleaned: the same
    assert (first.cached_query, again.cached_query, len(model.calls)) == (False, True, 1)
    assert titles(first) == titles(again)


def test_each_rewrite_is_searched_and_the_lists_fused():
    model = KeywordEmbeddings()
    result = retriever(embeddings=model, rewrite=lambda question: ["virtual private network vpn timeout"]).search(
        "it keeps dropping")
    assert result.queries == ["it keeps dropping", "virtual private network vpn timeout"]
    assert model.calls == result.queries and titles(result)[0] == "VPN Connection Timeout"
