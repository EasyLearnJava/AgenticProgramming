"""
Tests for vector_store.py, on Qdrant in memory: the first load makes the collection behind the alias; writing the
same chunks twice keeps one point each; a changed article loses its old chunks' points and a removed one all of
its points; each label gets a payload index and a filter finds only its points; the sparse vector finds an exact
word; a wrong vector size writes nothing; a rebuild fills a new collection and moves the alias only when it passes
its checks, so a broken one leaves the live collection untouched; rollback moves it back; orphans are reported.
"""
from datetime import UTC, datetime
from unittest import mock

import pytest
from fakes import ScriptedEmbeddings
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from chunking import KBTextSplitter
from knowledge_base_loader import KB_FILE, SETTINGS_FILE, KBLoader
from settings import load_settings
from vector_store import (
    DENSE,
    INDEXED_LABELS,
    SPARSE,
    KBVectorStore,
    StoreError,
    make_client,
    point_id,
    sparse_vector,
)

SETTINGS = load_settings(SETTINGS_FILE)
SIZE = 8
EMBED = ScriptedEmbeddings(dimensions=SIZE)


def sample_chunks() -> list[Document]:
    docs = KBLoader(KB_FILE, settings=SETTINGS, clock=lambda: datetime(2026, 10, 30, tzinfo=UTC)).load()
    return KBTextSplitter().split_documents(docs)


def vectors_of(chunks: list[Document]) -> list[list[float]]:
    return [EMBED.vector(chunk.page_content) for chunk in chunks]


CHUNKS = sample_chunks()
VPN = CHUNKS[0].metadata["doc_id"]


@pytest.fixture
def store() -> KBVectorStore:
    return KBVectorStore(QdrantClient(":memory:"), dimensions=SIZE)


def loaded(store: KBVectorStore, chunks: list[Document] = CHUNKS) -> KBVectorStore:
    store.write(chunks, vectors_of(chunks))
    return store


def ids_of(store: KBVectorStore, doc_id: str) -> set[str]:
    return store._points_by_article(store.current()).get(doc_id, set())


# -------------------------------------------------
# The Collection Behind the Alias
# -------------------------------------------------

def test_the_first_load_makes_the_collection_behind_the_alias(store):
    report = store.write(CHUNKS, vectors_of(CHUNKS))
    assert (store.current(), report.collection, report.added, report.points) == ("it_kb_v1", "it_kb_v1", 39, 39)
    params = store.client.get_collection("it_kb").config.params
    assert (params.vectors[DENSE].size, params.vectors[DENSE].distance) == (SIZE, models.Distance.COSINE)
    assert params.sparse_vectors[SPARSE].modifier == models.Modifier.IDF


def test_each_label_gets_a_payload_index(store):
    with mock.patch.object(store.client, "create_payload_index", wraps=store.client.create_payload_index) as made:
        store.ensure()
    assert [call.kwargs["field_name"] for call in made.call_args_list] == [f"metadata.{label}"
                                                                           for label in INDEXED_LABELS]


def test_the_payload_is_langchains_layout_so_its_vector_store_can_read_it(store):
    loaded(store)
    payload = store.client.retrieve("it_kb", [point_id(CHUNKS[0].metadata["chunk_id"])])[0].payload
    assert (payload["page_content"], payload["metadata"]) == (CHUNKS[0].page_content, CHUNKS[0].metadata)
    langchain = QdrantVectorStore(client=store.client, collection_name="it_kb", vector_name=DENSE,
                                  embedding=DeterministicFakeEmbedding(size=SIZE))
    found = langchain.similarity_search_by_vector(vectors_of(CHUNKS[:1])[0], k=1)
    assert found[0].page_content == CHUNKS[0].page_content and found[0].metadata["chunk_id"] == \
        CHUNKS[0].metadata["chunk_id"]


# -------------------------------------------------
# Idempotent Writes and Deletes
# -------------------------------------------------

def test_writing_the_same_chunks_twice_keeps_one_point_each(store):
    loaded(store)
    again = store.write(CHUNKS, vectors_of(CHUNKS))
    assert (again.added, again.updated, again.points) == (0, 39, 39)


def test_a_point_id_comes_from_its_chunk_id():
    assert point_id("kb-a:problem:1") == point_id("kb-a:problem:1") != point_id("kb-a:problem:2")


def test_a_changed_article_loses_its_old_chunks_points(store):
    loaded(store)
    vpn = [chunk for chunk in CHUNKS if chunk.metadata["doc_id"] == VPN]
    edited = Document(page_content=vpn[1].page_content + " 7. Check the client's log.",
                      metadata={**vpn[1].metadata, "chunk_id": f"{VPN}:resolution:new"})
    report = store.write([vpn[0], edited, vpn[2]], vectors_of([vpn[0], edited, vpn[2]]))
    assert (report.added, report.updated, report.deleted_stale, report.points) == (1, 2, 1, 39)
    assert ids_of(store, VPN) == {point_id(chunk.metadata["chunk_id"]) for chunk in (vpn[0], edited, vpn[2])}


def test_a_removed_articles_points_are_all_deleted(store):
    loaded(store)
    report = store.write([], [], removed=[VPN])
    assert (report.deleted_removed, report.points, ids_of(store, VPN)) == (3, 36, set())


def test_a_wrong_vector_size_writes_nothing(store):
    loaded(store)
    with pytest.raises(StoreError, match="A vector of 7 numbers, not 8: nothing written"):
        store.write(CHUNKS[:1], [[0.5] * 7])
    with pytest.raises(StoreError, match="1 chunks but 0 vectors"):
        store.write(CHUNKS[:1], [])
    assert store.client.count("it_kb").count == 39


def test_a_collection_of_another_size_stops_the_write_and_says_to_rebuild(store):
    loaded(store)
    bigger = KBVectorStore(store.client, dimensions=16)
    with pytest.raises(StoreError, match="holds vectors of 8 numbers, but the embedding model makes 16.*--rebuild"):
        bigger.write(CHUNKS[:1], [[0.5] * 16])


# -------------------------------------------------
# Searching: Filters and the Sparse Vector
# -------------------------------------------------

def test_a_filter_finds_only_its_labels_points(store):
    loaded(store)
    vpn_only = models.Filter(must=[models.FieldCondition(key="metadata.system", match=models.MatchValue(value="VPN"))])
    found = store.client.query_points("it_kb", query=vectors_of(CHUNKS[5:6])[0], using=DENSE, query_filter=vpn_only,
                                      limit=10).points
    assert {point.payload["metadata"]["system"] for point in found} == {"VPN"} and len(found) == 3


def test_the_sparse_vector_finds_an_exact_word(store):
    loaded(store)
    found = store.client.query_points("it_kb", query=sparse_vector("0x80070005"), using=SPARSE, limit=1).points
    assert "0x80070005" in found[0].payload["page_content"]


def test_a_sparse_vector_counts_each_word_the_same_on_every_run():
    first, again = sparse_vector("VPN vpn timeout"), sparse_vector("VPN vpn timeout")
    assert first == again and sorted(first.values) == [1.0, 2.0] and first.indices == sorted(first.indices)


# -------------------------------------------------
# Checks
# -------------------------------------------------

def test_the_check_finds_an_article_missing_points(store):
    loaded(store)
    store.client.delete("it_kb", points_selector=models.PointIdsList(points=[point_id(CHUNKS[0].metadata["chunk_id"])]))
    assert store.check("it_kb", CHUNKS) == [f"article {VPN} holds 2 points, not its 3 chunks"]


def test_points_of_an_article_not_in_the_knowledge_base_are_reported_not_deleted(store):
    loaded(store)
    report = store.write([], [], current={chunk.metadata["doc_id"] for chunk in CHUNKS[3:]})
    assert (report.orphans, report.points) == ([VPN], 39)


# -------------------------------------------------
# Rebuilding and Rolling Back
# -------------------------------------------------

def test_a_rebuild_fills_a_new_collection_then_moves_the_alias(store):
    loaded(store)
    fewer = CHUNKS[3:]
    report = store.rebuild(fewer, vectors_of(fewer))
    assert (report.collection, report.rebuilt, report.rebuilt_from, report.points) == ("it_kb_v2", True, "it_kb_v1",
                                                                                       36)
    assert (store.current(), store.client.count("it_kb").count, store.client.count("it_kb_v1").count) == \
        ("it_kb_v2", 36, 39)                                               # the old one kept, for rollback


def test_a_rebuild_that_fails_its_checks_leaves_the_live_collection_untouched(store):
    loaded(store)
    real_upsert = store.client.upsert

    def drop_the_last_point(collection, points, **options):                # a broken load: one point missing
        return real_upsert(collection, points=points[:-1], **options)

    with mock.patch.object(store.client, "upsert", drop_the_last_point), \
            pytest.raises(StoreError, match="the alias it_kb still points at it_kb_v1"):
        store.rebuild(CHUNKS, vectors_of(CHUNKS))
    assert (store.current(), store.client.count("it_kb").count) == ("it_kb_v1", 39)
    assert not store.client.collection_exists("it_kb_v2")


def test_a_third_rebuild_deletes_the_oldest_collection(store):
    loaded(store)
    store.rebuild(CHUNKS, vectors_of(CHUNKS))
    store.rebuild(CHUNKS, vectors_of(CHUNKS))
    assert [found.name for found in store.client.get_collections().collections] == ["it_kb_v2", "it_kb_v3"]


def test_rollback_moves_the_alias_back(store):
    loaded(store)
    store.rebuild(CHUNKS[3:], vectors_of(CHUNKS[3:]))
    assert store.rollback() == "it_kb_v1"
    assert (store.current(), store.client.count("it_kb").count) == ("it_kb_v1", 39)
    with pytest.raises(StoreError, match="no collection before it_kb_v1"):
        store.rollback()


# -------------------------------------------------
# The Client
# -------------------------------------------------

def test_a_client_for_each_kind_of_location(tmp_path):
    assert make_client(":memory:", folder=tmp_path).get_collections().collections == []
    on_disk = make_client("data/qdrant", folder=tmp_path)
    on_disk.create_collection("x", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    on_disk.close()
    assert (tmp_path / "data" / "qdrant").is_dir()
    server = make_client("https://qdrant.example:6333", folder=tmp_path, api_key="a-key")   # no call made yet
    assert server._client.rest_uri.startswith("https://qdrant.example:6333")


def test_a_folder_open_in_another_process_says_what_to_do(tmp_path):
    busy = RuntimeError("Storage folder is already accessed by another instance of Qdrant client")
    with mock.patch("vector_store.QdrantClient", side_effect=busy), \
            pytest.raises(StoreError, match="open in another process .* Close that one, or use a Qdrant server"):
        make_client("data/qdrant", folder=tmp_path)
