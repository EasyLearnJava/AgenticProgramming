"""
Tests for src/vectordb/vector_store.py: a new collection each time, of the right size, compared by cosine; the chunks
stored as points under their chunk_id, with their text and metadata, and none stored when the counts differ; the
closest chunks found, closest first, with their scores; Qdrant's failures turned into VectorStoreError; and the
store config.yaml names.
"""
import math

import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from support import chunks, filled_store

from src.config.settings import load_settings
from src.exceptions import VectorStoreError
from src.vectordb.vector_store import BaseVectorStore, QdrantStore, create_vector_store

CHUNKS = chunks()
VECTORS = KeywordEmbeddings().embed_documents([chunk.page_content for chunk in CHUNKS])


def test_a_new_collection_is_empty_of_the_right_size_and_cosine():
    store = QdrantStore(QdrantClient(":memory:"), "test_collection")
    store.recreate(SIZE)
    params = store.client.get_collection("test_collection").config.params.vectors
    assert (params.size, params.distance, store.count()) == (SIZE, Distance.COSINE, 0)


def test_recreating_deletes_the_old_points():
    store = filled_store()
    store.recreate(5)
    assert store.count() == 0
    assert store.client.get_collection("test_collection").config.params.vectors.size == 5


def test_each_chunk_is_a_point_under_its_chunk_id_with_its_text_and_metadata(logs):
    store = filled_store()
    assert store.count() == 28
    point = store.client.retrieve("test_collection", [CHUNKS[0].metadata["chunk_id"]], with_vectors=True)[0]
    assert point.payload == {"page_content": CHUNKS[0].page_content, "metadata": CHUNKS[0].metadata}
    length = math.sqrt(sum(number * number for number in VECTORS[0]))
    assert point.vector == pytest.approx([number / length for number in VECTORS[0]])   # cosine: stored at length 1
    assert logs.find("vectordb.upsert ok").points == 28


def test_storing_again_replaces_rather_than_adds():
    store = filled_store()
    store.upsert(CHUNKS, VECTORS)          # the same chunk_ids: the same 28 points, written again
    assert store.count() == 28


def test_a_chunk_without_a_vector_stores_nothing():
    store = QdrantStore(QdrantClient(":memory:"), "test_collection")
    store.recreate(SIZE)
    with pytest.raises(VectorStoreError, match="28 chunks but 27 vectors: nothing was stored"):
        store.upsert(CHUNKS, VECTORS[:27])
    assert store.count() == 0


def test_search_gives_the_k_closest_chunks_closest_first(logs):
    hits = filled_store().search(KeywordEmbeddings().embed_query("my vpn drops"), 5)
    assert len(hits) == 5
    assert hits[0].chunk.metadata["title"] == "VPN Connection Timeout"
    assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)
    record = logs.find("vectordb.search ok")
    assert (record.top_k, record.hits, record.top_score) == (5, 5, round(hits[0].score, 4))


def test_a_qdrant_failure_becomes_a_vector_store_error():
    store = QdrantStore(QdrantClient(":memory:"), "never_made")
    with pytest.raises(VectorStoreError, match="Couldn't search never_made"):
        store.search([0.0] * SIZE, 5)
    with pytest.raises(VectorStoreError, match="Couldn't count the points in never_made"):
        store.count()


def test_the_store_config_yaml_names():
    store = create_vector_store(load_settings().vectordb)
    assert isinstance(store, BaseVectorStore) and isinstance(store, QdrantStore)
    assert store.collection == "it_knowledge_base"
