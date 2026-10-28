"""
Tests for utils.py: what print_points() prints for the 28 stored chunks. They use KeywordEmbeddings, a
stand-in for Gemini (tests/fakes.py), and Qdrant in memory: no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from pipeline import embed_chunks, load_documents, make_vector_store, split_documents, store_vectors
from utils import print_points

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def test_print_points_prints_the_collection_then_every_point(capsys):
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    print_points(store)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, compared by Cosine"
    assert lines[1] == "Each point holds an id, a vector and a payload with metadata, page_content"
    assert lines[3] == (f"Point 1 of 28: VPN Connection Timeout, from character 0: {SIZE} numbers, "
                        "457 characters of text, 7 labels")
    assert sum(line.startswith("Point ") for line in lines) == 28
