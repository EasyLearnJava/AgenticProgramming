"""
Tests for vector_store.py: the collection, filling it with the 28 chunks, and what each stored point holds. The plain
tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory; the live test asks the
real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, add_knowledge_base, make_vector_store


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


def test_each_point_holds_a_vector_the_chunks_text_and_its_labels():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    chunks = add_knowledge_base(store)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == SIZE for point in points)
    assert sorted(point.payload["page_content"] for point in points) == sorted(chunk.page_content for chunk in chunks)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(points[0].payload["metadata"])


def test_an_existing_collection_is_kept():
    client = QdrantClient(":memory:")
    add_knowledge_base(make_vector_store(KeywordEmbeddings(), SIZE, client))
    make_vector_store(KeywordEmbeddings(), SIZE, client)          # the same client again: the points are still there
    assert client.count(COLLECTION).count == 28


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)
