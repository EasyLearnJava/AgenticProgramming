"""
Tests for embed_chunks.py: the 28 chunks embedded in one call, one vector each, in order, from their text only, and
what print_vectors(), in utils.py, prints. The plain tests use KeywordEmbeddings, a stand-in for Gemini
(tests/fakes.py); the live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, embeddings
from utils import print_vectors

CHUNKS = split_documents(load_documents())


class RecordingEmbeddings(KeywordEmbeddings):
    """KeywordEmbeddings that also keeps the texts it was given."""

    def embed_documents(self, texts):
        self.texts = list(texts)
        return super().embed_documents(texts)


def test_the_28_chunks_are_embedded_in_one_call_one_vector_each():
    stand_in = KeywordEmbeddings()
    vectors = embed_chunks(CHUNKS, stand_in)
    assert len(vectors) == 28
    assert all(len(vector) == SIZE for vector in vectors)
    assert stand_in.calls == [("documents", 28)]


def test_only_the_chunks_text_is_sent_in_the_chunks_order():
    stand_in = RecordingEmbeddings()
    vectors = embed_chunks(CHUNKS, stand_in)
    assert stand_in.texts == [chunk.page_content for chunk in CHUNKS]               # the text, not the labels
    assert vectors == [KeywordEmbeddings().embed_documents([chunk.page_content])[0] for chunk in CHUNKS]


def test_print_vectors_prints_each_chunk_with_its_vectors_size_and_first_numbers(capsys):
    print_vectors(CHUNKS, embed_chunks(CHUNKS, KeywordEmbeddings()))
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "28 chunks -> 28 vectors (gemini-embedding-001)"
    assert lines[2].startswith(
        f"Chunk 1 of 28: VPN Connection Timeout, from character 0 to 457 -> converted to {SIZE} numbers: [")
    assert lines[3].startswith("Chunk 2 of 28: VPN Connection Timeout, from character 459 to 569 -> converted to ")
    assert lines[-1].startswith("Chunk 28 of 28: Microsoft Teams Audio Issues, from character 581 to 699 -> ")
    assert sum(line.startswith("Chunk ") for line in lines) == 28


@pytest.mark.live
def test_live_every_chunk_gets_768_numbers():
    vectors = embed_chunks(CHUNKS, embeddings)
    assert len(vectors) == 28
    assert all(len(vector) == EMBEDDING_SIZE for vector in vectors)
