"""
Tests for src/chunking/chunker.py: 512 characters cut the 10 articles into 28 chunks, none too long, each keeping its
article's metadata and where it starts; and each chunk's chunk_index and chunk_id: a UUID that's the same every run,
different for every chunk, and new when the chunk's text changes.
"""
import uuid

import pytest
from support import articles

from src.chunking.chunker import Chunker, chunk_id

DOCS = articles()


def split(chunk_size: int = 512, chunk_overlap: int = 50):
    return Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap).split(DOCS)


def test_512_characters_cut_each_article_into_2_or_3_chunks():
    chunks = split()
    assert len(chunks) == 28
    per_article = [sum(chunk.metadata["doc_id"] == doc.metadata["doc_id"] for chunk in chunks) for doc in DOCS]
    assert set(per_article) == {2, 3}


@pytest.mark.parametrize("size", [200, 512, 1000])
def test_no_chunk_is_longer_than_the_chunk_size(size):
    assert all(len(chunk.page_content) <= size for chunk in split(chunk_size=size))


def test_each_chunk_keeps_its_articles_metadata_and_where_it_starts():
    by_id = {doc.metadata["doc_id"]: doc for doc in DOCS}
    for chunk in split():
        article = by_id[chunk.metadata["doc_id"]]
        start = chunk.metadata["start_index"]
        assert article.page_content[start:start + len(chunk.page_content)] == chunk.page_content
        assert article.metadata.items() <= chunk.metadata.items()


def test_chunk_index_counts_each_articles_chunks_from_0():
    chunks = split()
    first_article = [chunk.metadata["chunk_index"] for chunk in chunks if chunk.metadata["doc_id"] == "0"]
    assert first_article == list(range(len(first_article)))


def test_chunk_ids_are_uuids_the_same_every_run_and_all_different():
    first, second = split(), split()
    ids = [chunk.metadata["chunk_id"] for chunk in first]
    assert ids == [chunk.metadata["chunk_id"] for chunk in second]          # the same chunks, the same IDs
    assert len(set(ids)) == 28
    assert all(uuid.UUID(chunk_id_).version == 5 for chunk_id_ in ids)


def test_a_changed_chunk_gets_a_new_id():
    chunk = split()[0]
    before = chunk_id(chunk)
    chunk.page_content += " (edited)"
    assert chunk_id(chunk) != before


def test_the_articles_themselves_are_left_unchanged():
    split()
    assert set(DOCS[0].metadata) == {"doc_id", "source", "title", "system", "category", "priority", "tags"}


def test_the_split_is_logged_as_a_span(logs):
    split()
    record = logs.find("chunking.split ok")
    assert (record.documents, record.chunks, record.chunk_size) == (10, 28, 512)
    assert record.max_chars <= 512
