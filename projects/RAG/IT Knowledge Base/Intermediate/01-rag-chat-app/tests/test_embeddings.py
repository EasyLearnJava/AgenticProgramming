"""
Tests for src/embeddings/embedder.py: texts embedded in batches, in order, one vector each, every call in a span;
vectors of the wrong number or size refused; Gemini's model built with its timeout and attempts; and a provider's
failures (a rate limit, a timeout, a refused key, a server error) each turned into the right UpstreamError, with the
real LangChain Gemini class running against Google's client faked, so nothing leaves the machine.
"""
import asyncio

import httpx
import pytest
from fakes import SIZE, FakeGenaiClient, KeywordEmbeddings
from google.genai import errors
from pydantic import SecretStr

from src.config.settings import load_settings
from src.embeddings.embedder import Embedder, create_embedding_model
from src.exceptions import UpstreamError, UpstreamRateLimitError, UpstreamTimeoutError

TEXTS = [f"Text {number} about vpn" for number in range(25)]


def gemini_embedder(client: FakeGenaiClient) -> Embedder:
    """The real Gemini embeddings, as config.yaml makes them, with Google's client faked."""
    model = create_embedding_model(load_settings().embeddings, SecretStr("fake-key"))
    model.client = client
    return Embedder(model, dimensions=768, batch_size=100)


def google_error(code: int, status: str) -> errors.APIError:
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": f"A {code} from Google.", "status": status}})


# --- Embedding ---

def test_texts_are_embedded_in_batches_in_order_one_vector_each(logs):
    stand_in = KeywordEmbeddings()
    vectors = Embedder(stand_in, dimensions=SIZE, batch_size=10).embed_documents(TEXTS)
    assert stand_in.calls == [("documents", 10), ("documents", 10), ("documents", 5)]
    assert vectors == KeywordEmbeddings().embed_documents(TEXTS)
    record = logs.find("embeddings.embed_documents ok")
    assert (record.model, record.texts, record.batches) == ("KeywordEmbeddings", 25, 3)


def test_a_question_is_embedded_on_its_own_sync_or_async(logs):
    embedder = Embedder(KeywordEmbeddings(), dimensions=SIZE, batch_size=100)
    assert asyncio.run(embedder.aembed_query("my vpn")) == embedder.embed_query("my vpn")
    assert logs.messages().count("embeddings.embed_query ok") == 2


def test_vectors_of_the_wrong_size_are_refused():
    embedder = Embedder(KeywordEmbeddings(), dimensions=768, batch_size=100)
    with pytest.raises(UpstreamError, match=r"vectors of 11 numbers came back, but embeddings\.dimensions in "
                                            r"config\.yaml is 768"):
        embedder.embed_documents(TEXTS)


def test_a_missing_vector_is_refused():
    class OneShort(KeywordEmbeddings):
        def embed_documents(self, texts):
            return super().embed_documents(texts)[:-1]

    with pytest.raises(UpstreamError, match="25 texts were sent, but 24 vectors came back"):
        Embedder(OneShort(), dimensions=SIZE, batch_size=100).embed_documents(TEXTS)


# --- Gemini's model ---

def test_gemini_is_built_with_the_settings_timeout_and_attempts():
    settings = load_settings().embeddings
    model = create_embedding_model(settings, SecretStr("fake-key"))
    assert (model.model, model.output_dimensionality) == ("gemini-embedding-001", 768)
    http_options = model.client._api_client._http_options          # Google's client, as the builder set it up
    assert http_options.timeout == settings.timeout_seconds * 1000 == 30000
    assert http_options.retry_options.attempts == settings.max_attempts == 3


def test_the_real_gemini_class_runs_end_to_end_with_googles_client_faked():
    embedder = gemini_embedder(FakeGenaiClient(embed=lambda text: [0.1] * 768))
    assert len(embedder.embed_documents(["a", "b"])) == 2
    assert len(asyncio.run(embedder.aembed_query("q"))) == 768


@pytest.mark.parametrize("error, expected, retryable", [
    (google_error(429, "RESOURCE_EXHAUSTED"), UpstreamRateLimitError, True),
    (httpx.ReadTimeout("The read operation timed out"), UpstreamTimeoutError, True),
    (google_error(503, "UNAVAILABLE"), UpstreamError, True),
    (google_error(400, "INVALID_ARGUMENT"), UpstreamError, False),
], ids=["rate limit", "timeout", "server error", "bad key"])
def test_each_provider_failure_becomes_the_right_upstream_error(error, expected, retryable, logs):
    embedder = gemini_embedder(FakeGenaiClient(embed=error))
    with pytest.raises(UpstreamError) as caught:
        embedder.embed_documents(["a"])
    assert type(caught.value) is expected
    assert (caught.value.service, caught.value.retryable) == ("embeddings", retryable)
    assert str(caught.value).startswith("embeddings: GoogleGenerativeAIError: Error embedding content")
    assert caught.value.__cause__ is not None                      # the provider's own error, kept for the traceback
    assert logs.find("embeddings.embed_documents failed").error_type == expected.__name__
