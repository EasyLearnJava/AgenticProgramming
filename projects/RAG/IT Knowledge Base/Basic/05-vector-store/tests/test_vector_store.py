"""
Tests for vector_store.py: the collection, filling it with the 28 chunks, what each stored point holds, and Qdrant
on disk. The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory or in a
folder of the test's own; the live test asks the real Gemini.
"""
from pathlib import Path

import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, QDRANT_PATH, make_client, make_vector_store

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


def test_an_existing_collection_is_deleted_and_made_new():
    client = QdrantClient(":memory:")
    make_vector_store(KeywordEmbeddings(), SIZE, client).add_documents(CHUNKS)
    make_vector_store(KeywordEmbeddings(), 5, client)             # the same name again, with another vector size
    assert client.count(COLLECTION).count == 0                    # none of the old points are left
    assert client.get_collection(COLLECTION).config.params.vectors.size == 5      # and it has the new settings


def test_qdrant_on_disk_keeps_the_points_in_its_folder(tmp_path):
    assert QDRANT_PATH == Path(__file__).resolve().parent.parent / "qdrant_data"   # next to vector_store.py
    client = make_client(tmp_path)
    make_vector_store(KeywordEmbeddings(), SIZE, client).add_documents(CHUNKS)
    client.close()                                    # as when the script ends
    reopened = make_client(tmp_path)
    assert reopened.count(COLLECTION).count == 28     # still there
    reopened.close()


def test_on_disk_a_new_run_starts_with_none_of_the_old_points(tmp_path):
    client = make_client(tmp_path)
    make_vector_store(KeywordEmbeddings(), SIZE, client).add_documents(CHUNKS)
    client.close()
    client = make_client(tmp_path)                    # a new run, opening the same folder
    make_vector_store(KeywordEmbeddings(), SIZE, client)
    assert client.count(COLLECTION).count == 0        # deleting only the collection left the 28 old points (Windows)
    client.close()


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store.add_documents(CHUNKS)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)
