"""
Tests for rag_engine.py: nothing happens before build(), then answers with up to 3 different sources. The plain tests
use stand-ins for Gemini (tests/fakes.py) and Qdrant in memory; the live test asks the real Gemini.
"""
import asyncio

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings

from rag_engine import MAX_SOURCES, RAGEngine
from retriever import QUESTIONS


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


def test_aquery_gives_the_same_as_query():
    engine = stand_in_engine()
    engine.build()
    assert asyncio.run(engine.aquery("My VPN won't connect")) == engine.query("My VPN won't connect")


def test_other_sizes():
    engine = stand_in_engine(chunk_size=1000, top_k=2)
    engine.build()
    assert (engine.stats()["chunks"], engine.stats()["top_k"]) == (10, 2)
    assert len(engine.query("My VPN won't connect")["sources"]) <= 2


@pytest.mark.live
def test_live_a_sample_question_is_answered_from_its_article():
    engine = RAGEngine()
    engine.build()
    result = engine.query(QUESTIONS[0])
    assert result["answer"].strip()
    assert result["sources"][0]["title"] == "VPN Connection Timeout"
