"""
Tests for rag_engine.py: nothing happens before build(), answers with up to 3 different sources, and a Qdrant store
that keeps its points: a second build on the same chunks reuses them without embedding again. The plain tests use
stand-ins for Gemini (tests/fakes.py) and Qdrant inside this process ("local mode": in memory, or saved in a folder,
which stands in for the server); the live test needs the real Gemini and a running Qdrant server.
"""
import asyncio

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from qdrant_client import QdrantClient

import rag_engine
from rag_engine import MAX_SOURCES, RAGEngine
from retriever import QUESTIONS
from vector_store import COLLECTION, QDRANT_URL


def stand_in_engine(client, **settings):
    return RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                     embedding_size=SIZE, client=client, **settings)


def test_without_a_client_build_connects_to_the_qdrant_server(monkeypatch):
    stands_in_for_the_server = QdrantClient(":memory:")
    monkeypatch.setattr(rag_engine, "make_client", lambda: stands_in_for_the_server)
    engine = RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["x"]), embedding_size=SIZE)
    assert engine.client is None                    # making the engine connects to nothing
    engine.build()
    assert engine.client is stands_in_for_the_server


def test_nothing_is_read_or_called_before_build():
    engine = stand_in_engine(QdrantClient(":memory:"))
    assert engine.embeddings.calls == []
    with pytest.raises(RuntimeError, match="call build"):
        engine.query("My VPN won't connect")


def test_the_first_build_embeds_and_stores_the_28_chunks():
    engine = stand_in_engine(QdrantClient(":memory:"))
    engine.build()
    assert engine.embeddings.calls == [("documents", 28)]
    assert engine.client.count(COLLECTION).count == 28
    assert engine.stats()["reused_stored_chunks"] is False


def test_a_later_build_finds_the_same_chunks_stored_and_embeds_nothing(tmp_path):
    # QdrantClient(path=...) saves the points in a folder, like the server keeps them: close it and open it again,
    # as a new run of the app would.
    first_run = QdrantClient(path=str(tmp_path))
    stand_in_engine(first_run).build()
    first_run.close()
    second_run = QdrantClient(path=str(tmp_path))
    engine = stand_in_engine(second_run)
    engine.build()
    assert engine.embeddings.calls == []                       # nothing embedded: the chunks were already stored
    assert engine.stats()["reused_stored_chunks"] is True
    assert second_run.count(COLLECTION).count == 28            # no copies
    assert engine.query("My VPN won't connect")["sources"][0]["title"] == "VPN Connection Timeout"
    second_run.close()


def test_other_chunk_sizes_replace_the_stored_chunks():
    client = QdrantClient(":memory:")
    stand_in_engine(client).build()                            # 28 chunks of 512
    engine = stand_in_engine(client, chunk_size=1000)
    engine.build()
    assert engine.stats()["reused_stored_chunks"] is False
    assert client.count(COLLECTION).count == 10                # the 1000-character chunks only


def test_query_gives_the_answer_and_up_to_3_different_sources():
    engine = stand_in_engine(QdrantClient(":memory:"))
    engine.build()
    result = engine.query("My VPN won't connect")
    titles = [source["title"] for source in result["sources"]]
    assert result["answer"] == "An answer."
    assert 1 <= len(titles) <= MAX_SOURCES and len(set(titles)) == len(titles)
    assert result["sources"][0]["snippet"].startswith("Title: VPN Connection Timeout")
    assert asyncio.run(engine.aquery("My VPN won't connect")) == result


def qdrant_server_answers() -> bool:
    try:
        QdrantClient(url=QDRANT_URL, check_compatibility=False, timeout=2).get_collections()
        return True
    except Exception:
        return False


@pytest.mark.live
@pytest.mark.skipif(not qdrant_server_answers(), reason="needs the Qdrant server: docker compose up -d")
def test_live_a_sample_question_is_answered_from_its_article():
    engine = RAGEngine()
    engine.build()
    result = engine.query(QUESTIONS[0])
    assert result["answer"].strip()
    assert result["sources"][0]["title"] == "VPN Connection Timeout"
