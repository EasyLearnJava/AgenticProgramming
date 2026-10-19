"""
Tests for similarity.py: cosine similarity, and the ranking of the articles for a question. The plain tests use
KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py); the live test asks the real Gemini.
"""
import pytest
from fakes import KeywordEmbeddings

from knowledge_base import load_documents
from models import embeddings
from similarity import QUESTION, cosine_similarity, rank

DOCS = load_documents()


@pytest.mark.parametrize("a, b, expected", [
    ([1.0, 0.0], [1.0, 0.0], 1.0),        # the same direction
    ([1.0, 2.0], [2.0, 4.0], 1.0),        # the same direction, twice as long: length doesn't count
    ([1.0, 0.0], [0.0, 1.0], 0.0),        # at right angles: unrelated
    ([1.0, 0.0], [-1.0, 0.0], -1.0),      # opposite directions
], ids=["same", "longer", "unrelated", "opposite"])
def test_cosine_similarity(a, b, expected):
    assert cosine_similarity(a, b) == pytest.approx(expected)


def test_rank_puts_the_closest_article_first_with_two_calls():
    stand_in = KeywordEmbeddings()
    ranking = rank(QUESTION, DOCS, stand_in)
    assert ranking[0][1] == "VPN Connection Timeout"
    assert len(ranking) == 10
    assert [score for score, _ in ranking] == sorted((score for score, _ in ranking), reverse=True)
    assert stand_in.calls == [("documents", 10), ("query", QUESTION)]    # every article in one call, then the question


@pytest.mark.live
def test_live_the_vpn_question_finds_the_vpn_article_first():
    assert rank(QUESTION, DOCS, embeddings)[0][1] == "VPN Connection Timeout"
