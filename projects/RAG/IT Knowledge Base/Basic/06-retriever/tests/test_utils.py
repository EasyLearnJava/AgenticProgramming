"""
Tests for utils.py: what print_retrieval() prints for a search. They use KeywordEmbeddings, a stand-in for
Gemini (tests/fakes.py), and Qdrant in memory: no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from retriever import QUESTIONS, TOP_K, make_retriever
from utils import print_retrieval
from vector_store import make_vector_store, store_vectors

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def filled_store(stand_in=None):
    store = make_vector_store(stand_in or KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return store


def top_vector(store, scored):
    """The top chunk's vector, read back from Qdrant by its point's id, as pipeline.py does."""
    return store.client.retrieve(store.collection_name, [scored[0][0].metadata["_id"]], with_vectors=True)[0].vector


def test_print_retrieval_prints_the_vector_the_scores_the_retrievers_chunks_and_the_prompt(capsys):
    store = filled_store()
    question = QUESTIONS[0]
    vector = KeywordEmbeddings().embed_query(question)
    scored = store.similarity_search_with_score_by_vector(vector, k=TOP_K)
    print_retrieval(question, vector, scored, make_retriever(store).invoke(question), top_vector(store, scored))
    printed = capsys.readouterr().out
    assert printed.startswith(f"Question: {question}\nThe question became {SIZE} numbers: [")
    assert "\n\nThe 5 closest chunks, with their scores, closest first:\n" in printed
    assert "\n\nThe retriever, embedding and searching in one call, found:\n" in printed
    assert ("\n\nA sample of what a prompt gets: the first 2 of the 5 chunks, as one text (format_docs):\n[1] "
            in printed)


def test_the_top_score_worked_out_by_hand_is_qdrants_score(capsys):
    store = filled_store()
    vector = KeywordEmbeddings().embed_query(QUESTIONS[0])
    scored = store.similarity_search_with_score_by_vector(vector, k=TOP_K)
    print_retrieval(QUESTIONS[0], vector, scored, [], top_vector(store, scored))
    lines = capsys.readouterr().out.splitlines()
    by_hand = lines.index(
        "The top score, worked out by hand from the question's vector and the top chunk's stored one:")
    assert lines[by_hand + 2].endswith(", 1.0000 (the chunk's, as Qdrant keeps it)")   # cosine: kept at length 1
    worked_out, qdrant = lines[by_hand + 3].split(" = ")[1].split(", and Qdrant's score: ")
    assert worked_out == qdrant == f"{scored[0][1]:.3f}"
