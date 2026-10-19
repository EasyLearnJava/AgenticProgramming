"""
Tests for vector_store.py: the collection, filling it with the 28 chunks under ids made from their text, searching
it, and the client for a Qdrant server. The plain tests use KeywordEmbeddings, a stand-in for Gemini
(tests/fakes.py), and Qdrant in memory: no server needed. The live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, QDRANT_URL, QUESTION, add_knowledge_base, chunk_id, make_client, make_vector_store


def test_a_new_store_has_an_empty_cosine_collection_of_the_right_size():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    params = store.client.get_collection(COLLECTION).config.params.vectors
    assert (params.size, params.distance) == (SIZE, Distance.COSINE)
    assert store.client.count(COLLECTION).count == 0


def test_adding_the_knowledge_base_stores_28_chunks_in_one_embedding_call():
    stand_in = KeywordEmbeddings()
    store = make_vector_store(stand_in, SIZE)
    chunks = add_knowledge_base(store)
    assert len(chunks) == 28
    assert store.client.count(COLLECTION).count == 28
    assert stand_in.calls == [("documents", 28)]


def test_a_search_gives_the_closest_chunks_with_their_scores_and_metadata():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    add_knowledge_base(store)
    results = store.similarity_search_with_score(QUESTION, k=5)
    assert results[0][0].metadata["title"] == "VPN Connection Timeout"
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)


def test_each_chunk_gets_its_own_id_and_always_the_same_one():
    chunks = split_documents(load_documents())
    ids = [chunk_id(chunk) for chunk in chunks]
    assert len(set(ids)) == 28                                                    # one each
    assert ids == [chunk_id(chunk) for chunk in split_documents(load_documents())]   # the same on every run


def test_adding_the_same_chunks_again_replaces_them_instead_of_adding_copies():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    add_knowledge_base(store)
    add_knowledge_base(store)
    assert store.client.count(COLLECTION).count == 28


def test_the_server_address_and_a_client_for_it_without_a_request():
    assert QDRANT_URL == "http://localhost:6333"      # nothing in .env or the environment changes it in the tests
    client = make_client("http://localhost:6399")     # no server there: making the client sends nothing yet
    assert isinstance(client, QdrantClient)


@pytest.mark.live
def test_live_the_vpn_question_finds_a_vpn_chunk_first():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    assert store.similarity_search(QUESTION, k=1)[0].metadata["title"] == "VPN Connection Timeout"
