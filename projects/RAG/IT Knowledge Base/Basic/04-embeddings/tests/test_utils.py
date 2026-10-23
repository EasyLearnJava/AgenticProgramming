"""
Tests for utils.py: what print_vectors() prints for the 28 chunks. They use KeywordEmbeddings, a stand-in
for Gemini (tests/fakes.py): no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from utils import print_vectors

CHUNKS = split_documents(load_documents())


def test_print_vectors_prints_each_chunk_with_its_vectors_size_and_first_numbers(capsys):
    print_vectors(CHUNKS, embed_chunks(CHUNKS, KeywordEmbeddings()))
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "28 chunks -> 28 vectors (gemini-embedding-001)"
    assert lines[2].startswith(
        f"Chunk 1 of 28: VPN Connection Timeout, from character 0 to 457 -> converted to {SIZE} numbers: [")
    assert lines[3].startswith("Chunk 2 of 28: VPN Connection Timeout, from character 459 to 569 -> converted to ")
    assert lines[-1].startswith("Chunk 28 of 28: Microsoft Teams Audio Issues, from character 581 to 699 -> ")
    assert sum(line.startswith("Chunk ") for line in lines) == 28
