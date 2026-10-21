"""
Tests for chunking.py: the 10 articles cut into chunks, each no longer than the chunk size, each keeping its
article's metadata and where in the article it starts. No key, no network.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from chunking import CHUNK_OVERLAP, CHUNK_SIZE, split_documents
from knowledge_base import load_documents

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DOCS = load_documents()


def test_512_characters_cut_each_article_into_2_or_3_chunks():
    assert (CHUNK_SIZE, CHUNK_OVERLAP) == (512, 50)
    chunks = split_documents(DOCS)
    assert len(chunks) == 28
    per_article = [sum(c.metadata["doc_id"] == d.metadata["doc_id"] for c in chunks) for d in DOCS]
    assert set(per_article) == {2, 3}


@pytest.mark.parametrize("size", [200, 512, 1000])
def test_no_chunk_is_longer_than_the_chunk_size(size):
    assert all(len(chunk.page_content) <= size for chunk in split_documents(DOCS, chunk_size=size))


def test_each_chunk_keeps_its_articles_metadata_and_where_it_starts():
    by_id = {doc.metadata["doc_id"]: doc for doc in DOCS}
    for chunk in split_documents(DOCS):
        article = by_id[chunk.metadata["doc_id"]]
        start = chunk.metadata["start_index"]
        assert {k: v for k, v in chunk.metadata.items() if k != "start_index"} == article.metadata
        assert article.page_content[start:start + len(chunk.page_content)] == chunk.page_content


def test_chunks_break_between_sections_first():
    # The empty lines between Title, Problem, Resolution and Notes are the first places the splitter tries.
    for chunk in split_documents(DOCS):
        assert chunk.page_content.split(": ", 1)[0] in {"Title", "Problem", "Resolution", "Notes"}


def test_1000_characters_keep_every_article_whole():
    chunks = split_documents(DOCS, chunk_size=1000)
    assert [chunk.page_content for chunk in chunks] == [doc.page_content for doc in DOCS]


def test_running_it_prints_the_counts_then_every_articles_chunks():
    printed = subprocess.run([sys.executable, str(FOLDER / "chunking.py")], cwd=FOLDER, capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
    lines = printed.splitlines()
    assert printed.startswith("10 articles -> 28 chunks of at most 512 characters\n"
                              "  2 from VPN Connection Timeout (569 characters)\n")
    assert ("\n\nArticle 1 of 10: VPN Connection Timeout, cut into 2 chunks\n\n"
            "Chunk 1 of 2, from character 0 (") in printed
    articles = [line for line in lines if line.startswith("Article ")]
    assert len(articles) == 10
    assert articles[-1] == "Article 10 of 10: Microsoft Teams Audio Issues, cut into 3 chunks"
    assert sum(line.startswith("Chunk ") for line in lines) == 28
    assert "\n\n\n" not in printed                  # never more than one blank line in a row
