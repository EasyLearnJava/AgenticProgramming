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


def test_print_retrieval_prints_the_vector_the_scores_the_retrievers_chunks_and_the_prompt(capsys):
    store = filled_store()
    question = QUESTIONS[0]
    vector = KeywordEmbeddings().embed_query(question)
    scored = store.similarity_search_with_score_by_vector(vector, k=TOP_K)
    print_retrieval(question, vector, scored, make_retriever(store).invoke(question))
    printed = capsys.readouterr().out
    assert printed.startswith(f"Question: {question}\nThe question became {SIZE} numbers: [")
    assert "\n\nThe 5 closest chunks, with their scores, closest first:\n" in printed
    assert "\n\nThe retriever, embedding and searching in one call, found:\n" in printed
    assert "\n\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):\n[1] " in printed
