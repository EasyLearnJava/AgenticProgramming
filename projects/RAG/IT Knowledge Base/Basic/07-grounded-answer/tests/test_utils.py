"""
Tests for utils.py: what print_answer() prints for an answer and its chunks. They use KeywordEmbeddings, a
stand-in for Gemini (tests/fakes.py), and Qdrant in memory: no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from rag_chain import QUESTION
from retriever import make_retriever
from utils import print_answer
from vector_store import make_vector_store, store_vectors

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def stand_in_retriever():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return make_retriever(store)


def test_print_answer_prints_the_question_the_answer_then_each_article_once(capsys):
    docs = stand_in_retriever().invoke(QUESTION)
    print_answer(QUESTION, {"docs": docs, "question": QUESTION, "answer": "An answer."})
    titles = dict.fromkeys(doc.metadata["title"] for doc in docs)          # each title once, closest first
    assert capsys.readouterr().out == (f"Question: {QUESTION}\n\nAnswer (Gemini's, from the chunks found):\n"
                                       "An answer.\n\nSources (the articles of the chunks found, closest first):\n"
                                       + "".join(f"  {title}\n" for title in titles))
