"""
Tests for vector_store.py: the collection, filling it with the 28 chunks, and searching it. The plain tests use
KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory; the live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, QUESTION, add_knowledge_base, make_vector_store


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
    assert len(results) == 5
    assert results[0][0].metadata["title"] == "VPN Connection Timeout"
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(results[0][0].metadata)


def test_an_existing_collection_is_kept():
    client = QdrantClient(":memory:")
    add_knowledge_base(make_vector_store(KeywordEmbeddings(), SIZE, client))
    make_vector_store(KeywordEmbeddings(), SIZE, client)          # the same client again: the points are still there
    assert client.count(COLLECTION).count == 28


@pytest.mark.live
def test_live_the_vpn_question_finds_a_vpn_chunk_first():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    assert store.similarity_search(QUESTION, k=1)[0].metadata["title"] == "VPN Connection Timeout"
