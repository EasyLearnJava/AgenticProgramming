"""
Tests for vector_store.py: the collection, filling it with the 28 chunks under ids made from their text, what each
stored point holds, and the client for a Qdrant server.
The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory: no server
needed. The live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, QDRANT_URL, chunk_id, make_client, make_vector_store

CHUNKS = split_documents(load_documents())


def test_a_new_store_has_an_empty_cosine_collection_of_the_right_size():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    params = store.client.get_collection(COLLECTION).config.params.vectors
    assert (params.size, params.distance) == (SIZE, Distance.COSINE)
    assert store.client.count(COLLECTION).count == 0


def test_storing_the_chunks_makes_28_points_in_one_embedding_call():
    stand_in = KeywordEmbeddings()
    store = make_vector_store(stand_in, SIZE)
    store.add_documents(CHUNKS)
    assert store.client.count(COLLECTION).count == 28
    assert stand_in.calls == [("documents", 28)]


def test_each_point_holds_a_vector_the_chunks_text_and_its_labels():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store.add_documents(CHUNKS)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == SIZE for point in points)
    assert sorted(point.payload["page_content"] for point in points) == sorted(chunk.page_content for chunk in CHUNKS)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(points[0].payload["metadata"])


def test_each_chunk_gets_its_own_id_and_always_the_same_one():
    ids = [chunk_id(chunk) for chunk in CHUNKS]
    assert len(set(ids)) == 28                                                    # one each
    assert ids == [chunk_id(chunk) for chunk in split_documents(load_documents())]   # the same on every run


def test_adding_the_same_chunks_again_replaces_them_instead_of_adding_copies():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    ids = [chunk_id(chunk) for chunk in CHUNKS]
    store.add_documents(CHUNKS, ids=ids)
    store.add_documents(CHUNKS, ids=ids)
    assert store.client.count(COLLECTION).count == 28


def test_the_server_address_and_a_client_for_it_without_a_request():
    assert QDRANT_URL == "http://localhost:6333"      # nothing in .env or the environment changes it in the tests
    client = make_client("http://localhost:6399")     # no server there: making the client sends nothing yet
    assert isinstance(client, QdrantClient)


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store.add_documents(CHUNKS)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)
