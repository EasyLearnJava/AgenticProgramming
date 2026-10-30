"""
Tests for src/pipeline: the engine does nothing before build(), then holds the 10 articles' 28 chunks, embedded in one
call; index() embeds them once and saves their vectors, which a later build loads with no call to the model (the same
answers follow), unless they're for other chunks; it answers sync or async with up to 3 different sources; the model
gets the chunks found and the question; readiness; stats read from the parts; the parts config.yaml names
(factory.py), with the real Gemini classes running end to end against Google's client faked; and one question's log
lines, every one under its trace ID, stage by stage. The live tests build the real engine and ask the real Gemini.
"""
import asyncio
import logging

import pytest
from fakes import ANSWER, FakeGenaiClient, KeywordEmbeddings, gemini_answer
from fastapi.testclient import TestClient
from google.genai import errors
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from pydantic import SecretStr
from support import change, stand_in_engine

from src.api.app import create_app
from src.config.settings import PROJECT_DIR, load_api_key, load_settings
from src.exceptions import ConfigError, NotReadyError, UpstreamRateLimitError
from src.observability.tracing import trace_context
from src.pipeline.factory import create_engine
from src.pipeline.rag_engine import QueryResult

# --- Building ---

def test_nothing_is_read_or_called_before_build(settings):
    stand_in = KeywordEmbeddings()
    engine = stand_in_engine(settings, embedding_model=stand_in)
    assert stand_in.calls == [] and engine.stats()["documents"] == 0
    with pytest.raises(NotReadyError, match="build\\(\\) must run first"):
        engine.query("My VPN won't connect")


def test_build_embeds_the_28_chunks_in_one_call_and_stores_them(settings):
    stand_in = KeywordEmbeddings()
    engine = stand_in_engine(settings, embedding_model=stand_in)
    engine.build()
    assert (engine.stats()["documents"], engine.stats()["chunks"]) == (10, 28)
    assert stand_in.calls == [("documents", 28)]
    assert engine.check_ready() == 28


def test_building_again_starts_with_a_new_collection(engine):
    engine.build()
    assert engine.store.count() == 28


# --- The saved vectors ---

def test_index_embeds_the_chunks_once_and_saves_their_vectors(settings, logs):
    stand_in = KeywordEmbeddings()
    assert stand_in_engine(settings, embedding_model=stand_in).index() == 28
    assert stand_in.calls == [("documents", 28)]
    assert settings.embeddings.vector_file.exists()
    record = logs.find("pipeline.index ok")
    assert (record.documents, record.chunks) == (10, 28)


def test_a_build_loads_the_saved_vectors_and_calls_no_model(settings, logs):
    stand_in_engine(settings).index()
    stand_in = KeywordEmbeddings()
    engine = stand_in_engine(settings, embedding_model=stand_in)
    engine.build()
    assert stand_in.calls == [] and engine.check_ready() == 28        # stored, and no call: they came from the file
    assert logs.find("pipeline.build ok").vectors_from == "file"
    embedded = stand_in_engine(change(settings, embeddings={"vector_file": None}))
    embedded.build()
    assert engine.query("My VPN won't connect") == embedded.query("My VPN won't connect")    # the same answer, sources


def test_a_build_embeds_when_the_saved_vectors_are_for_other_chunks(settings, logs):
    stand_in_engine(settings).index()
    stand_in = KeywordEmbeddings()
    stand_in_engine(change(settings, chunking={"chunk_size": 1000}), embedding_model=stand_in).build()
    assert stand_in.calls == [("documents", 10)]                       # 1000 characters: one chunk per article
    assert logs.find("pipeline.build ok").vectors_from == "model"
    assert logs.messages(logging.WARNING) == [
        "The saved vectors aren't used: there's no saved vector for 10 of the 10 chunks (an article, the columns read "
        "or the chunking changed since they were saved). The chunks are embedded instead; python main.py index saves "
        "their vectors"]


def test_index_needs_a_vector_file(settings):
    with pytest.raises(ConfigError, match=r"embeddings\.vector_file in config\.yaml is null"):
        stand_in_engine(change(settings, embeddings={"vector_file": None})).index()


def test_stats_are_read_from_the_parts(settings):
    engine = stand_in_engine(change(settings, retrieval={"top_k": 2}, chunking={"chunk_size": 1000}))
    engine.build()
    stats = engine.stats()
    assert {key: stats[key] for key in ("chunks", "chunk_size", "top_k", "collection", "prompt_version")} == {
        "chunks": 10, "chunk_size": 1000, "top_k": 2, "collection": "it_knowledge_base",
        "prompt_version": "answer-v1"}
    assert (stats["embedding_model"], stats["chat_model"]) == ("KeywordEmbeddings", "FakeMessagesListChatModel")
    assert stats["built_at"].endswith("+00:00")


# --- Answering ---

def test_query_gives_the_answer_and_up_to_3_different_sources(engine):
    result = engine.query("My VPN won't connect")
    assert result.answer == ANSWER
    titles = [source.title for source in result.sources]
    assert 1 <= len(titles) <= 3 and len(set(titles)) == len(titles)
    first = result.sources[0]
    assert (first.title, first.system, first.category) == ("VPN Connection Timeout", "VPN", "Remote Access")
    assert first.snippet.startswith("Title: VPN Connection Timeout") and len(first.snippet) <= 203
    assert 0 < first.score <= 1 and first.chunk_id


def test_aquery_gives_the_same_as_query(engine):
    assert asyncio.run(engine.aquery("My VPN won't connect")) == engine.query("My VPN won't connect")


def test_the_model_gets_the_chunks_found_and_the_question(settings):
    seen = []

    def stand_in_model(messages):                 # takes the model's place, and keeps what it was given
        seen.append(messages)
        return AIMessage(content="An answer.")

    engine = stand_in_engine(settings, chat_model=RunnableLambda(stand_in_model))
    engine.build()
    engine.query("My VPN won't connect")
    system, human = seen[0]
    assert "Articles:\n[1] VPN Connection Timeout\nTitle: VPN Connection Timeout" in system.content
    assert human.content == "My VPN won't connect"


def test_a_store_missing_chunks_is_not_ready(engine):
    engine.store.recreate(11)                      # emptied behind the engine's back
    with pytest.raises(NotReadyError, match="holds 0 chunks, but the build stored 28"):
        engine.check_ready()


# --- One question's trace ---

def test_every_line_of_a_question_carries_its_trace_id_stage_by_stage(engine, logs):
    with trace_context() as trace_id:
        asyncio.run(engine.aquery("My VPN won't connect"))
    lines = [record for record in logs.records if record.getMessage().endswith(" ok")]
    assert [record.getMessage() for record in lines] == [
        "embeddings.embed_query ok", "vectordb.search ok", "retrieval.retrieve ok", "prompts.build ok",
        "llm.generate ok", "pipeline.query ok"]
    assert {record.trace_id for record in logs.records} == {trace_id}
    query = logs.find("pipeline.query ok")
    assert (query.question_chars, query.sources, query.prompt_version) == (20, 3, "answer-v1")


def test_the_question_and_answer_text_are_logged_only_at_debug(engine, logs):
    engine.query("My VPN won't connect")
    texts = [record for record in logs.records if "VPN won't" in str(vars(record)) or ANSWER in str(vars(record))]
    assert texts and all(record.levelname == "DEBUG" for record in texts)


# --- The parts config.yaml names ---

def test_making_the_engine_is_a_stage_of_its_own(logs):
    create_engine(load_settings(), SecretStr("fake-key"))
    record = logs.find("pipeline.create ok")
    assert (record.embedding_model, record.chat_model) == ("gemini-embedding-001", "gemini-3.5-flash-lite")
    assert (record.embeddings, record.llm, record.vectordb) == ("google", "google", "qdrant")


def test_the_factory_wires_the_parts_config_yaml_names():
    engine = create_engine(load_settings(), SecretStr("fake-key"))      # nothing is read and no call is made
    stats = engine.stats()
    assert (stats["embedding_model"], stats["chat_model"]) == ("gemini-embedding-001", "gemini-3.5-flash-lite")
    assert (stats["chunk_size"], stats["top_k"], engine.embedder.dimensions) == (512, 5, 768)
    vector_file = engine.vector_file
    assert vector_file.path == PROJECT_DIR / "data" / "vectors.json"
    assert (vector_file.provider, vector_file.model, vector_file.dimensions) == ("google", "gemini-embedding-001", 768)


def test_the_real_gemini_classes_run_end_to_end_with_googles_client_faked():
    # No vector file, so the build embeds through the faked client, even when data/vectors.json has been saved
    engine = create_engine(change(load_settings(), embeddings={"vector_file": None}), SecretStr("fake-key"))
    fake = FakeGenaiClient(embed=lambda text: KeywordEmbeddings()._vector(text) + [0.0] * 757,
                           generate=gemini_answer("Open UDP ports 500 and 4500."))
    engine.embedder.model.client = engine.llm.model.client = fake
    engine.build()
    result = asyncio.run(engine.aquery("My VPN won't connect"))
    assert result.answer == "Open UDP ports 500 and 4500."
    assert result.sources[0].title == "VPN Connection Timeout"
    quota = {"error": {"code": 429, "message": "Quota.", "status": "RESOURCE_EXHAUSTED"}}
    fake.generate = errors.ClientError(429, quota)
    with pytest.raises(UpstreamRateLimitError):      # Google's 429, through LangChain, to the app's own error
        engine.query("My VPN won't connect")


# --- Live ---

@pytest.fixture(scope="module")
def live_engine():
    """The real engine, built once for the live tests: the 28 chunks embedded in one call, never loaded from a file."""
    engine = create_engine(change(load_settings(), embeddings={"vector_file": None}), load_api_key())
    engine.build()
    return engine


@pytest.mark.live
def test_live_the_vpn_question_finds_its_article_first_and_gets_an_answer(live_engine):
    result: QueryResult = live_engine.query("How do I fix VPN connection timeouts?")
    assert result.answer
    assert result.sources[0].title == "VPN Connection Timeout"


@pytest.mark.live
def test_live_the_api_answers(live_engine):
    with TestClient(create_app(load_settings(), live_engine)) as client:
        response = client.post("/api/v1/query", json={"question": "How do I fix VPN connection timeouts?"})
    assert response.status_code == 200
    assert response.json()["sources"][0]["title"] == "VPN Connection Timeout"
