"""
Tests for tuning.py: the test questions, the scores for each chunk size, the table, and the answers for each k.
The plain tests use stand-ins for Gemini (tests/fakes.py); the live test asks the real Gemini's embedding model.
"""
import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings

import tuning
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from tuning import EVAL_SET, evaluate, print_table

SMALL_SET = [("my vpn keeps dropping", "VPN Connection Timeout"), ("the printer is missing", "Printer Not Found")]


def test_the_test_questions_cover_every_article_once():
    titles = [title for _, title in EVAL_SET]
    assert sorted(titles) == sorted(doc.metadata["title"] for doc in load_documents())


def test_evaluate_scores_each_chunk_size():
    rows = evaluate(KeywordEmbeddings(), SIZE, eval_set=SMALL_SET, chunk_sizes=[200, 1000], top_ks=[1, 3])
    assert [(row["chunk_size"], row["chunks"]) for row in rows] == [(200, 49), (1000, 10)]
    for row in rows:
        assert row["top_1"] <= row["top_3"] <= 2
        assert row["top_1"] == 2                    # with these keywords, both questions find their article first


def test_the_questions_are_embedded_once_and_each_chunk_size_once():
    stand_in = KeywordEmbeddings()
    evaluate(stand_in, SIZE, eval_set=SMALL_SET, chunk_sizes=[200, 1000], top_ks=[1, 3])
    assert stand_in.calls == [("query", "my vpn keeps dropping"), ("query", "the printer is missing"),
                              ("documents", 49), ("documents", 10)]


def test_the_table_has_a_line_per_chunk_size(capsys):
    print_table([{"chunk_size": 200, "chunks": 49, "top_1": 1, "top_3": 2},
                 {"chunk_size": 1000, "chunks": 10, "top_1": 2, "top_3": 2}], total=2)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "chunk size  chunks  found in top 1  found in top 3"
    assert lines[1].split() == ["200", "49", "1", "of", "2", "2", "of", "2"]
    assert lines[2].split() == ["1000", "10", "2", "of", "2", "2", "of", "2"]


def test_compare_top_k_answers_the_question_once_for_each_k(monkeypatch):
    stand_in = KeywordEmbeddings()
    monkeypatch.setattr(tuning, "embeddings", stand_in)
    monkeypatch.setattr(tuning, "EMBEDDING_SIZE", SIZE)
    monkeypatch.setattr(tuning, "chat_model", FakeListChatModel(responses=["the first answer", "the second answer"]))
    answers = tuning.compare_top_k("my vpn keeps dropping", top_ks=(1, 5))
    assert answers == {1: "the first answer", 5: "the second answer"}
    assert stand_in.calls.count(("query", "my vpn keeps dropping")) == 2          # one search for each k


@pytest.mark.live
def test_live_the_default_chunk_size_finds_most_articles_in_the_top_5():
    rows = evaluate(embeddings, EMBEDDING_SIZE, chunk_sizes=[512], top_ks=[5])
    assert rows[0]["top_5"] >= 8
