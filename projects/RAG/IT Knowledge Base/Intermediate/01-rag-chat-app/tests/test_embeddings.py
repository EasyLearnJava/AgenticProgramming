"""
Tests for src/embeddings: texts embedded in batches, in order, one vector each, every call in a span; vectors of the
wrong number or size refused; Gemini's model built with its timeout and attempts; a provider's failures (a rate
limit, a timeout, a refused key, a server error) each turned into the right UpstreamError, with the real LangChain
Gemini class running against Google's client faked, so nothing leaves the machine; and the vector file: saved
vectors load back exactly, found by their texts in any order, but only when every text has one from the same model
and size; a missing or broken file means embedding (a broken one with a warning saying why); and a file is written
whole or not at all.
"""
import asyncio
import logging

import httpx
import pytest
from fakes import SIZE, FakeGenaiClient, KeywordEmbeddings
from google.genai import errors
from pydantic import SecretStr

from src.config.settings import load_settings
from src.embeddings.embedder import Embedder, create_embedding_model
from src.embeddings.vector_file import VectorFile
from src.exceptions import UpstreamError, UpstreamRateLimitError, UpstreamTimeoutError, VectorFileError

TEXTS = [f"Text {number} about vpn" for number in range(25)]
VECTORS = [[0.1 + 0.2, 1 / 3, -2.5e-08], [1.0, 0.0, 0.5]]      # 0.30000000000000004 and the like must come back exact


def gemini_embedder(client: FakeGenaiClient) -> Embedder:
    """The real Gemini embeddings, as config.yaml makes them, with Google's client faked."""
    model = create_embedding_model(load_settings().embeddings, SecretStr("fake-key"))
    model.client = client
    return Embedder(model, dimensions=768, batch_size=100)


def google_error(code: int, status: str) -> errors.APIError:
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": f"A {code} from Google.", "status": status}})


def vector_file(path, **made_by) -> VectorFile:
    """A vector file for VECTORS' model and size, unless made_by says otherwise."""
    return VectorFile(path, **{"provider": "google", "model": "gemini-embedding-001", "dimensions": 3, **made_by})


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


# --- The vector file ---

def test_saved_vectors_load_back_exactly_for_the_same_texts(tmp_path, logs):
    vector_file(tmp_path / "vectors.json").save(["a", "b"], VECTORS)
    assert vector_file(tmp_path / "vectors.json").load(["a", "b"]) == VECTORS
    saved, loaded = logs.find("embeddings.save_vectors ok"), logs.find("embeddings.load_vectors ok")
    assert (saved.file, saved.vectors) == ("vectors.json", 2)
    assert (loaded.used, loaded.vectors) == (True, 2) and loaded.saved_at.endswith("+00:00")
    assert logs.messages(logging.WARNING) == []


def test_each_texts_vector_is_found_by_the_text_whatever_the_order(tmp_path):
    vector_file(tmp_path / "vectors.json").save(["a", "b"], VECTORS)
    assert vector_file(tmp_path / "vectors.json").load(["b", "a"]) == [VECTORS[1], VECTORS[0]]    # rows reordered
    assert vector_file(tmp_path / "vectors.json").load(["b"]) == [VECTORS[1]]                     # an article removed


@pytest.mark.parametrize("texts, made_by, reason", [
    (["a", "edited"], {}, "there's no saved vector for 1 of the 2 chunks (an article, the columns read or the "
                          "chunking changed since they were saved)"),
    (["a", "b", "new"], {}, "there's no saved vector for 1 of the 3 chunks"),
    (["a", "b"], {"model": "text-embedding-3-small"}, "they were made by google's gemini-embedding-001 at 3 numbers, "
                                                      "and the chunks are embedded by google's text-embedding-3-small"),
    (["a", "b"], {"dimensions": 768}, "and the chunks are embedded by google's gemini-embedding-001 at 768"),
], ids=["an edited text", "a text more", "another model", "another size"])
def test_saved_vectors_arent_used_for_other_texts_or_another_model(tmp_path, logs, texts, made_by, reason):
    vector_file(tmp_path / "vectors.json").save(["a", "b"], VECTORS)
    assert vector_file(tmp_path / "vectors.json", **made_by).load(texts) is None
    assert logs.find("embeddings.load_vectors ok").used is False
    [warning] = logs.messages(logging.WARNING)
    assert warning.startswith("The saved vectors aren't used: ") and reason in warning
    assert warning.endswith("The chunks are embedded instead; python main.py index saves their vectors")


def test_no_file_yet_means_embedding_and_isnt_a_warning(tmp_path, logs):
    assert vector_file(tmp_path / "vectors.json").load(["a"]) is None
    record = logs.find("embeddings.load_vectors ok")
    assert (record.used, record.reason) == (False, "there's no file: python main.py index makes it")
    assert logs.messages(logging.WARNING) == []


@pytest.mark.parametrize("content, reason", [
    (b'{"provider": "goo', "it doesn't hold saved vectors (the file: Invalid JSON: EOF while parsing a string"),
    (b'{"provider": "google"}', "it doesn't hold saved vectors (model: Field required)"),
    (b'\xff\xfe{}', "it doesn't hold saved vectors (the file: Invalid JSON"),
], ids=["cut short", "not this app's", "not UTF-8"])
def test_a_file_that_doesnt_hold_saved_vectors_isnt_used_and_says_why(tmp_path, logs, content, reason):
    (tmp_path / "vectors.json").write_bytes(content)
    assert vector_file(tmp_path / "vectors.json").load(["a"]) is None
    [warning] = logs.messages(logging.WARNING)
    assert warning.startswith(f"The saved vectors aren't used: {reason}")


def test_the_file_is_written_whole_or_not_at_all(tmp_path, logs):
    (tmp_path / "vectors.json").mkdir()               # a folder where the file should be: it can't be replaced
    with pytest.raises(VectorFileError, match=r"Couldn't save the vectors in .*vectors\.json: "):
        vector_file(tmp_path / "vectors.json").save(["a", "b"], VECTORS)
    assert [path.name for path in tmp_path.iterdir()] == ["vectors.json"]     # no half-written file left beside it
    assert logs.find("embeddings.save_vectors failed").error_type == "VectorFileError"
    with pytest.raises(VectorFileError, match="2 texts but 1 vectors: nothing was saved"):
        vector_file(tmp_path / "other.json").save(["a", "b"], VECTORS[:1])
    assert not (tmp_path / "other.json").exists()
