"""
Tests for vector_store.py: the collection, filling it with the 28 chunks, what each stored point holds, and what
print_points() prints. The plain tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in
memory; the live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, make_vector_store, print_points

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


def test_an_existing_collection_is_kept():
    client = QdrantClient(":memory:")
    make_vector_store(KeywordEmbeddings(), SIZE, client).add_documents(CHUNKS)
    make_vector_store(KeywordEmbeddings(), SIZE, client)          # the same client again: the points are still there
    assert client.count(COLLECTION).count == 28


def test_print_points_prints_the_collection_then_every_point(capsys):
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store.add_documents(CHUNKS)
    print_points(store)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, compared by Cosine"
    assert lines[1] == "Each point holds an id, a vector and a payload with metadata, page_content"
    assert lines[3] == (f"Point 1 of 28: VPN Connection Timeout, from character 0: {SIZE} numbers, "
                        "457 characters of text, 7 labels")
    assert sum(line.startswith("Point ") for line in lines) == 28


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store.add_documents(CHUNKS)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)
