"""
Tests for utils.py: what print_retrieval() prints for a search. They use KeywordEmbeddings, a stand-in for
Gemini (tests/fakes.py), and Qdrant in memory: no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from pipeline import (QUESTIONS, embed_chunks, format_docs, load_documents, make_retriever, make_vector_store,
                      split_documents, store_vectors)
from utils import print_retrieval

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def filled_store(stand_in=None):
    store = make_vector_store(stand_in or KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return store


def test_print_retrieval_prints_the_question_the_retrievers_chunks_and_the_prompt(capsys):
    question = QUESTIONS[0]
    found = make_retriever(filled_store()).invoke(question)
    print_retrieval(question, found, format_docs(found[:2]))
    printed = capsys.readouterr().out
    lines = [f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}\n" for chunk in found]
    assert printed.startswith(f"Question: {question}\n\nThe 5 closest chunks the retriever found, closest first:\n"
                              + "".join(lines))
    assert printed.endswith("\n\nA sample of what a prompt gets: the first 2 of the 5 chunks, as one text "
                            "(format_docs):\n" + format_docs(found[:2]) + "\n")
