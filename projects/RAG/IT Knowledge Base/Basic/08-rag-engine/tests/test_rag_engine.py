"""
Tests for rag_engine.py: nothing happens before build(), then answers with up to 3 different sources; the data file,
the collection and the sizes can be set, by name only. The plain tests use stand-ins for Gemini (tests/fakes.py) and
Qdrant in memory; the live test asks the real Gemini.
"""
import csv

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from qdrant_client import QdrantClient

from knowledge_base import KB_FILE
from rag_engine import MAX_SOURCES, RAGEngine, print_result
from retriever import QUESTIONS
from vector_store import COLLECTION


def stand_in_engine(**settings):
    return RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                     embedding_size=SIZE, **settings)


def test_nothing_is_read_or_called_before_build():
    engine = stand_in_engine()
    assert engine.embeddings.calls == []
    assert engine.stats()["documents"] == 0
    with pytest.raises(RuntimeError, match="call build"):
        engine.query("My VPN won't connect")


def test_build_embeds_the_28_chunks_in_one_call():
    engine = stand_in_engine()
    engine.build()
    assert (engine.stats()["documents"], engine.stats()["chunks"]) == (10, 28)
    assert engine.embeddings.calls == [("documents", 28)]


def test_query_gives_the_answer_and_up_to_3_different_sources():
    engine = stand_in_engine()
    engine.build()
    result = engine.query("My VPN won't connect")
    assert result["answer"] == "An answer."
    titles = [source["title"] for source in result["sources"]]
    assert 1 <= len(titles) <= MAX_SOURCES == 3
    assert len(set(titles)) == len(titles)                  # each article at most once
    first = result["sources"][0]
    assert (first["title"], first["system"], first["category"]) == ("VPN Connection Timeout", "VPN", "Remote Access")
    assert first["snippet"].startswith("Title: VPN Connection Timeout")
    assert len(first["snippet"]) <= 203                    # 200 characters, plus "..." when the text is longer


def test_other_sizes():
    engine = stand_in_engine(chunk_size=1000, top_k=2)
    engine.build()
    assert (engine.stats()["chunks"], engine.stats()["top_k"]) == (10, 2)
    assert len(engine.query("My VPN won't connect")["sources"]) <= 2


def test_another_knowledge_base_file(tmp_path):
    with open(KB_FILE, encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    two_articles = tmp_path / "two_articles.csv"
    with open(two_articles, "w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(rows[:3])                # the header and the first 2 articles
    engine = stand_in_engine(data_path=str(two_articles))  # a str works as well as a Path
    engine.build()
    assert engine.data_path == two_articles
    assert engine.stats()["documents"] == 2
    assert {source["title"] for source in engine.query("My VPN won't connect")["sources"]} <= {
        "VPN Connection Timeout", "MFA Setup Failure"}


def test_engines_in_their_own_collections_keep_their_own_chunks():
    client = QdrantClient(":memory:")
    default = stand_in_engine(client=client)
    large = stand_in_engine(client=client, collection="it_kb_1000", chunk_size=1000)
    default.build()
    large.build()
    assert (client.count(COLLECTION).count, client.count("it_kb_1000").count) == (28, 10)
    assert (default.stats()["collection"], large.stats()["collection"]) == (COLLECTION, "it_kb_1000")


def test_settings_are_passed_by_name_only():
    with pytest.raises(TypeError):
        RAGEngine(KeywordEmbeddings())                     # a setting by position: refused


def test_print_result_prints_the_question_the_answer_and_each_source(capsys):
    source = {"title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access", "snippet": "Title: VPN"}
    print_result("My VPN won't connect", {"answer": "An answer.", "sources": [source]})
    assert capsys.readouterr().out == ("Q: My VPN won't connect\nA: An answer.\n"
                                       "   source: VPN Connection Timeout (VPN, Remote Access)\n\n")


@pytest.mark.live
def test_live_a_sample_question_is_answered_from_its_article():
    engine = RAGEngine()
    engine.build()
    result = engine.query(QUESTIONS[0])
    assert result["answer"].strip()
    assert result["sources"][0]["title"] == "VPN Connection Timeout"
