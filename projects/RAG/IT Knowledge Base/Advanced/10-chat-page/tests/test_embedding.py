"""
Tests for embedding.py, against the stand-in service in tests/fakes.py: every chunk gets a vector of the right size,
labelled with its model; the cache means a second run makes no call and two models never mix; batches stay under
their limits and calls under the concurrency limit; a rate limit, a server error or a timeout is retried with
backoff, and a bad request or the day's quota isn't; vectors made before a failure are kept; nothing sensitive is
sent; and a wrong answer stops the run.
"""
import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fakes import ScriptedEmbeddings, daily_quota, google_error, rate_limit
from google.genai.types import HttpOptions
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai._common import GoogleGenerativeAIError
from pydantic import SecretStr

from chunking import KBTextSplitter
from embedding import (
    ChunkEmbedder,
    EmbeddingCache,
    EmbeddingError,
    is_daily_quota,
    is_retryable,
    make_embedding_model,
)
from knowledge_base_loader import KB_FILE, SETTINGS_FILE, KBLoader
from settings import load_settings

MODEL = "fake/test-model"
NOON = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
SETTINGS = load_settings(SETTINGS_FILE)


def sample_chunks() -> list[Document]:
    """The sample's 39 chunks, made fresh for each test (embed() adds to their metadata)."""
    docs = KBLoader(KB_FILE, settings=SETTINGS, clock=lambda: NOON).load()
    return KBTextSplitter().split_documents(docs)


def embedder(service: ScriptedEmbeddings, cache: EmbeddingCache | None = None, **limits) -> ChunkEmbedder:
    """A ChunkEmbedder on the stand-in service that never really waits: each wait is recorded in .waits."""
    waits: list[float] = []

    async def record(seconds: float) -> None:
        waits.append(seconds)

    made = ChunkEmbedder(service, model_name=MODEL, dimensions=service.dimensions, cache=cache, sleep=record,
                         rng=random.Random(7), clock=lambda: NOON, **limits)
    made.waits = waits
    return made


@pytest.fixture
def cache(tmp_path) -> EmbeddingCache:
    return EmbeddingCache(tmp_path / "cache.sqlite3", model=MODEL, dimensions=8)


# -------------------------------------------------
# Vectors
# -------------------------------------------------

def test_every_chunk_gets_its_vector_in_order():
    chunks, service = sample_chunks(), ScriptedEmbeddings()
    vectors = embedder(service).embed(chunks)
    assert vectors == [service.vector(chunk.page_content) for chunk in chunks]
    assert all(type(value) is float for vector in vectors for value in vector)


def test_each_chunk_records_the_model_its_size_and_when_its_vector_was_made():
    chunks = sample_chunks()
    embedder(ScriptedEmbeddings()).embed(chunks)
    assert {(chunk.metadata["embedding_model"], chunk.metadata["embedding_dimensions"],
             chunk.metadata["embedded_at"]) for chunk in chunks} == {(MODEL, 8, "2026-10-30T12:00:00+00:00")}


def test_the_report_counts_the_chunks_calls_and_tokens():
    made = embedder(ScriptedEmbeddings())
    made.embed(sample_chunks())
    report = made.report
    assert (report.chunks, report.from_cache, report.embedded, report.calls, report.retries) == (39, 0, 39, 1, 0)
    assert report.tokens == sum(chunk.metadata["token_count"] for chunk in sample_chunks())
    assert report.seconds > 0


# -------------------------------------------------
# The Cache
# -------------------------------------------------

def test_a_second_run_takes_every_vector_from_the_cache_and_makes_no_call(cache):
    first = embedder(ScriptedEmbeddings(), cache).embed(sample_chunks())
    service = ScriptedEmbeddings()
    second = embedder(service, cache)
    assert second.embed(sample_chunks()) == first
    assert (service.calls, second.report.from_cache, second.report.embedded) == ([], 39, 0)
    assert cache.count() == 39


def test_only_a_changed_chunk_is_embedded_again(cache):
    embedder(ScriptedEmbeddings(), cache).embed(sample_chunks())
    chunks = sample_chunks()
    chunks[5].page_content += " 8. Ask the user to restart."
    service = ScriptedEmbeddings()
    embedder(service, cache).embed(chunks)
    assert service.calls == [[chunks[5].page_content]]


def test_two_models_never_share_a_cached_vector(tmp_path):
    path = tmp_path / "cache.sqlite3"
    embedder(ScriptedEmbeddings(), EmbeddingCache(path, model=MODEL, dimensions=8)).embed(sample_chunks())
    other = ScriptedEmbeddings()
    made = ChunkEmbedder(other, model_name="fake/another-model", dimensions=8,
                         cache=EmbeddingCache(path, model="fake/another-model", dimensions=8))
    made.embed(sample_chunks())
    assert (made.report.from_cache, len(other.calls)) == (0, 1)


def test_the_same_text_twice_is_sent_once():
    chunks = [Document(page_content="Restart the router.", metadata={"chunk_id": f"c{n}"}) for n in range(3)]
    service = ScriptedEmbeddings()
    vectors = embedder(service).embed(chunks)
    assert service.calls == [["Restart the router."]] and vectors[0] == vectors[1] == vectors[2]


def test_a_broken_cache_file_says_to_delete_it(tmp_path):
    path = tmp_path / "cache.sqlite3"
    path.write_text("not a database", encoding="utf-8")
    with pytest.raises(EmbeddingError, match="embedding cache can't be used .*Delete it"):
        embedder(ScriptedEmbeddings(), EmbeddingCache(path, model=MODEL, dimensions=8)).embed(sample_chunks())


# -------------------------------------------------
# Batches and Concurrency
# -------------------------------------------------

def test_batches_stay_under_the_count_and_the_tokens():
    service = ScriptedEmbeddings()
    embedder(service, batch_size=10).embed(sample_chunks())
    assert [len(call) for call in service.calls] == [10, 10, 10, 9]
    service = ScriptedEmbeddings()
    made = embedder(service, batch_tokens=500)
    made.embed(sample_chunks())
    assert all(sum(made.length_function(text) for text in call) <= 500 for call in service.calls)
    assert len(service.calls) > 1


def test_no_more_calls_wait_at_once_than_the_limit():
    service = ScriptedEmbeddings()
    embedder(service, batch_size=5, max_concurrency=2).embed(sample_chunks())
    assert (len(service.calls), service.most_in_flight) == (8, 2)


# -------------------------------------------------
# Retries
# -------------------------------------------------

@pytest.mark.parametrize("failure", [rate_limit(), google_error(503, status="UNAVAILABLE"), "slow"],
                         ids=["rate limit", "server error", "timeout"])
def test_a_failure_worth_another_try_is_retried_after_a_wait(failure):
    service = ScriptedEmbeddings(script=[failure], delay=1.0)
    made = embedder(service, timeout_seconds=0.2)
    vectors = made.embed(sample_chunks())
    assert len(vectors) == 39
    assert (len(service.calls), made.report.calls, made.report.retries, made.report.failed_calls) == (2, 2, 1, 1)
    assert len(made.waits) == 1 and 0.5 <= made.waits[0] <= 1.0          # 1 s, half of it random


def test_the_wait_doubles_each_try_up_to_its_longest():
    service = ScriptedEmbeddings(script=[rate_limit()] * 3)
    made = embedder(service, backoff_seconds=1, backoff_max_seconds=3)
    made.embed(sample_chunks())
    ceilings = [1, 2, 3]                                                   # 1, 2, then 4 capped at 3
    assert all(ceiling / 2 <= wait <= ceiling for wait, ceiling in zip(made.waits, ceilings, strict=True))


def test_a_bad_request_fails_at_once_with_why():
    service = ScriptedEmbeddings(script=[google_error(400, "API key not valid.", "INVALID_ARGUMENT")])
    made = embedder(service)
    with pytest.raises(EmbeddingError, match=r"Embedding failed after 1 try \(ClientError: 400 INVALID_ARGUMENT"):
        made.embed(sample_chunks())
    assert (len(service.calls), made.waits) == (1, [])


def test_the_days_quota_used_up_isnt_retried():
    service = ScriptedEmbeddings(script=[daily_quota()])
    with pytest.raises(EmbeddingError, match="quota for today is used up .* midnight Pacific time"):
        embedder(service).embed(sample_chunks())
    assert len(service.calls) == 1


def test_retries_end_after_the_last_try():
    service = ScriptedEmbeddings(script=[google_error(503)] * 4)
    made = embedder(service, max_attempts=4)
    with pytest.raises(EmbeddingError, match=r"after 4 tries \(ServerError: 503"):
        made.embed(sample_chunks())
    assert (made.report.calls, made.report.retries) == (4, 3)


def test_vectors_made_before_a_failure_are_cached(cache):
    service = ScriptedEmbeddings(script=[None, google_error(400)])
    with pytest.raises(EmbeddingError):
        embedder(service, cache, batch_size=20, max_concurrency=1).embed(sample_chunks())
    assert cache.count() == 20                                             # the first batch: the rerun skips it


@pytest.mark.parametrize("error, retryable", [
    (rate_limit(), True), (daily_quota(), False), (google_error(500), True), (google_error(400), False),
    (google_error(403), False), (TimeoutError(), True), (httpx.ReadTimeout("slow"), True), (ValueError("x"), False),
], ids=["429", "429 per day", "500", "400", "403", "timeout", "httpx timeout", "other"])
def test_which_errors_are_worth_another_try(error, retryable):
    assert is_retryable(error) is retryable


def test_googles_error_is_found_inside_langchains():
    try:
        try:
            raise daily_quota()
        except Exception as err:
            raise GoogleGenerativeAIError("Error embedding content") from err
    except GoogleGenerativeAIError as wrapped:
        assert is_daily_quota(wrapped) and not is_retryable(wrapped)


# -------------------------------------------------
# The Gate and the Checks
# -------------------------------------------------

def test_no_sensitive_value_is_sent_and_each_one_is_counted():
    chunks = [Document(page_content="Mail jane.doe@example.com, card 4111 1111 1111 1111", metadata={"chunk_id": "c1"})]
    service = ScriptedEmbeddings()
    made = embedder(service)
    made.embed(chunks)
    assert service.calls == [["Mail [REDACTED:EMAIL], card [REDACTED:CARD]"]]
    assert made.report.redacted == ["c1: card number **** 1111", "c1: email address j***@example.com"]


@pytest.mark.parametrize("answer, message", [
    ("short", "a vector of 7 numbers, not 8"),
], ids=["wrong size"])
def test_a_wrong_answer_stops_the_run(answer, message):
    with pytest.raises(EmbeddingError, match=message):
        embedder(ScriptedEmbeddings(script=[answer])).embed(sample_chunks())


def test_a_wrong_count_or_a_value_that_isnt_a_number_stops_the_run():
    made = embedder(ScriptedEmbeddings())
    with pytest.raises(EmbeddingError, match="gave back 1 vectors for 2 texts"):
        made._check(["a", "b"], [[0.0] * 8])
    with pytest.raises(EmbeddingError, match="isn't a real number"):
        made._check(["a"], [[float("nan")] * 8])


def test_nothing_to_embed_makes_no_call():
    service = ScriptedEmbeddings()
    assert embedder(service).embed([]) == [] and service.calls == []


# -------------------------------------------------
# The Model
# -------------------------------------------------

def test_the_stand_in_model_needs_no_key():
    model = make_embedding_model(provider="fake", model="x", dimensions=16, timeout_seconds=1, api_key=None)
    assert isinstance(model, DeterministicFakeEmbedding) and len(model.embed_query("vpn")) == 16


def test_gemini_is_built_with_a_timeout_and_no_retries_of_its_own():
    model = make_embedding_model(provider="google", model="gemini-embedding-001", dimensions=768,
                                 timeout_seconds=30, api_key=SecretStr("fake-key"))
    assert isinstance(model, GoogleGenerativeAIEmbeddings)
    options: HttpOptions = model.client._api_client._http_options
    assert (options.timeout, options.retry_options.attempts) == (30_000, 1)   # ChunkEmbedder's retries: the only ones
    with pytest.raises(ValueError, match="needs an API key"):
        make_embedding_model(provider="google", model="m", dimensions=8, timeout_seconds=1, api_key=None)


def test_the_cache_is_one_file_with_each_vectors_model_size_and_date(cache):
    cache.put({"abc": [0.5] * 8}, "2026-10-30T12:00:00+00:00")
    assert cache.get(["abc", "missing"]) == {"abc": ([0.5] * 8, "2026-10-30T12:00:00+00:00")}
    assert EmbeddingCache(cache.path, model=MODEL, dimensions=16).get(["abc"]) == {}     # another size: not found
    assert Path(cache.path).is_file()


def test_async_code_can_await_it():
    service = ScriptedEmbeddings()
    assert len(asyncio.run(embedder(service).aembed(sample_chunks()))) == 39
