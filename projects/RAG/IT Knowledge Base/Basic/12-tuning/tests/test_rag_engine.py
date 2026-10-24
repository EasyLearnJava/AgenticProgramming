"""
Tests for rag_engine.py: nothing happens before build(), answers with up to 3 different sources, and a Qdrant store
that keeps its points: a second build on the same chunks reuses them without embedding again, and engines in
collections of their own keep their own chunks. The plain tests use stand-ins for Gemini (tests/fakes.py) and Qdrant
in memory, or in a folder of the test's own; the live test needs the real Gemini, and saves its chunks in
qdrant_data/.
"""
import asyncio
import csv

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from qdrant_client import QdrantClient

import rag_engine
from knowledge_base import KB_FILE
from rag_engine import MAX_SOURCES, RAGEngine
from retriever import QUESTIONS
from vector_store import COLLECTION


def stand_in_engine(client, **settings):
    return RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                     embedding_size=SIZE, client=client, **settings)


def test_without_a_client_build_opens_qdrant_on_disk(monkeypatch):
    stands_in_for_the_folder = QdrantClient(":memory:")
    monkeypatch.setattr(rag_engine, "make_client", lambda: stands_in_for_the_folder)
    engine = RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["x"]), embedding_size=SIZE)
    assert engine.client is None                    # making the engine connects to nothing
    engine.build()
    assert engine.client is stands_in_for_the_folder


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
    # QdrantClient(path=...) saves the points in a folder, as make_client() does: close it and open it again,
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


def test_another_embedding_model_embeds_the_chunks_again_instead_of_reusing_them():
    class OtherEmbeddings(KeywordEmbeddings):                 # another model: its vectors can't be compared
        pass

    client = QdrantClient(":memory:")
    stand_in_engine(client).build()
    engine = RAGEngine(embeddings=OtherEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                       embedding_size=SIZE, client=client)
    engine.build()
    assert engine.embeddings.calls == [("documents", 28)]     # embedded again, with the new model
    assert engine.stats()["reused_stored_chunks"] is False
    assert engine.stats()["embedding_model"] == "OtherEmbeddings"
    assert client.count(COLLECTION).count == 28               # the new model's points only


def test_a_failed_embedding_leaves_the_stored_chunks_as_they_were():
    client = QdrantClient(":memory:")
    stand_in_engine(client).build()                            # 28 chunks of 512
    engine = stand_in_engine(client, chunk_size=1000)

    def gemini_fails(texts):
        raise RuntimeError("Gemini is down")

    engine.embeddings.embed_documents = gemini_fails
    with pytest.raises(RuntimeError, match="Gemini is down"):
        engine.build()
    assert client.count(COLLECTION).count == 28                # embedded first: the old collection was never deleted


def test_engines_in_their_own_collections_keep_their_own_chunks():
    client = QdrantClient(":memory:")
    stand_in_engine(client).build()                            # 28 chunks of 512, in the default collection
    large = stand_in_engine(client, collection="it_kb_1000", chunk_size=1000)
    large.build()
    assert (client.count(COLLECTION).count, client.count("it_kb_1000").count) == (28, 10)   # both kept
    again = stand_in_engine(client)
    again.build()
    assert again.stats()["reused_stored_chunks"] is True       # the 512 chunks were still there: nothing embedded
    assert again.embeddings.calls == []
    assert large.stats()["collection"] == "it_kb_1000"


def test_another_knowledge_base_file(tmp_path):
    with open(KB_FILE, encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))
    two_articles = tmp_path / "two_articles.csv"
    with open(two_articles, "w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(rows[:3])                    # the header and the first 2 articles
    engine = stand_in_engine(QdrantClient(":memory:"), data_path=str(two_articles))   # a str works as well as a Path
    engine.build()
    assert engine.data_path == two_articles
    assert engine.stats()["documents"] == 2


def test_stats_names_the_engines_own_models():
    stand_in = stand_in_engine(None)
    assert (stand_in.stats()["embedding_model"], stand_in.stats()["chat_model"]) == (
        "KeywordEmbeddings", "FakeListChatModel")                    # stand-ins go by their class names
    default = RAGEngine()                                            # Gemini's models: nothing is read or called
    assert (default.stats()["embedding_model"], default.stats()["chat_model"]) == (
        "gemini-embedding-001", "gemini-3.5-flash-lite")


def test_settings_are_passed_by_name_only():
    with pytest.raises(TypeError):
        RAGEngine(KeywordEmbeddings())                         # a setting by position: refused


def test_query_gives_the_answer_and_up_to_3_different_sources():
    engine = stand_in_engine(QdrantClient(":memory:"))
    engine.build()
    result = engine.query("My VPN won't connect")
    titles = [source["title"] for source in result["sources"]]
    assert result["answer"] == "An answer."
    assert 1 <= len(titles) <= MAX_SOURCES and len(set(titles)) == len(titles)
    assert result["sources"][0]["snippet"].startswith("Title: VPN Connection Timeout")
    assert asyncio.run(engine.aquery("My VPN won't connect")) == result


@pytest.mark.live
def test_live_a_sample_question_finds_its_article_first_and_gets_an_answer():
    engine = RAGEngine()
    try:
        engine.build()
        result = engine.query(QUESTIONS[0])
        assert result["answer"].strip()
        assert result["sources"][0]["title"] == "VPN Connection Timeout"
    finally:
        if engine.client is not None:
            engine.client.close()                              # frees qdrant_data/ for later tests, even on a failure
