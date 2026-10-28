"""
Tests for utils.py: cosine(), and what print_vectors() prints for the 28 chunks. They use KeywordEmbeddings, a
stand-in for Gemini (tests/fakes.py): no key, no network.
"""
import pytest
from fakes import SIZE, KeywordEmbeddings

from pipeline import EMBEDDING_MODEL, embed_chunks, load_documents, split_documents
from utils import cosine, print_vectors

CHUNKS = split_documents(load_documents())


def test_cosine_is_1_for_the_same_direction_0_at_right_angles_and_minus_1_for_opposite():
    assert cosine([3, 4], [6, 8]) == pytest.approx(1)        # twice as long, the same direction
    assert cosine([1, 0], [0, 5]) == pytest.approx(0)
    assert cosine([1, 2], [-1, -2]) == pytest.approx(-1)
    assert cosine([3, 4], [4, 3]) == pytest.approx(0.96)     # (3×4 + 4×3) / (5 × 5)


def test_print_vectors_prints_each_chunk_with_its_vectors_size_and_first_numbers(capsys):
    print_vectors(CHUNKS, embed_chunks(CHUNKS, KeywordEmbeddings()), EMBEDDING_MODEL)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "28 chunks -> 28 vectors (gemini-embedding-001)"
    assert lines[2].startswith(
        f"Chunk 1 of 28: VPN Connection Timeout, from character 0 to 457 -> converted to {SIZE} numbers: [")
    assert lines[3].startswith("Chunk 2 of 28: VPN Connection Timeout, from character 459 to 569 -> converted to ")
    assert lines[29].startswith("Chunk 28 of 28: Microsoft Teams Audio Issues, from character 581 to 699 -> ")
    assert sum(line.startswith("Chunk ") for line in lines) == 28


def test_print_vectors_then_prints_how_close_chunk_1_is_to_every_other_chunk_closest_first(capsys):
    vectors = embed_chunks(CHUNKS, KeywordEmbeddings())
    print_vectors(CHUNKS, vectors, EMBEDDING_MODEL)
    lines = capsys.readouterr().out.splitlines()
    assert lines[30:33] == ["",
                            "How close chunk 1 (VPN Connection Timeout) is to every other chunk, closest first",
                            "(cosine similarity: 1 is the same direction, 0 is at right angles):"]
    closeness = lines[33:]
    assert len(closeness) == 27                               # every chunk but chunk 1
    scores = [float(line.split()[0]) for line in closeness]
    assert scores == sorted(scores, reverse=True)
    # The stand-in counts keywords. The only other chunk that says "vpn" is chunk 6, from the Laptop article ("If
    # using VPN disconnect ..."), so it's the closest; chunk 2, the VPN article's notes, never says "vpn"
    assert closeness[0] == f"  {cosine(vectors[0], vectors[5]):.3f}  chunk 6: Laptop Performance Degradation"
