"""
Tests for utils.py: what print_answer() prints for a prompt, an answer and its chunks, and what print_answer_alone()
prints. They use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory: no key, no network.
"""
from fakes import SIZE, KeywordEmbeddings

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from rag_chain import prompt
from retriever import QUESTIONS, format_docs, make_retriever
from utils import print_answer, print_answer_alone
from vector_store import make_vector_store, store_vectors

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def stand_in_retriever():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return make_retriever(store)


def test_print_answer_prints_the_question_the_prompt_the_answer_then_each_article_once(capsys):
    question = QUESTIONS[0]
    docs = stand_in_retriever().invoke(question)
    messages = prompt.format_messages(context=format_docs(docs), question=question)
    print_answer(question, messages, {"docs": docs, "question": question, "answer": "An answer."})
    titles = dict.fromkeys(doc.metadata["title"] for doc in docs)          # each title once, closest first
    assert capsys.readouterr().out == (
        f"Question: {question}\n\n"
        "What Gemini got: the chain's prompt, filled in with the 5 chunks found and the question\n"
        f"--- system message ---\n{messages[0].content}\n"
        f"--- human message ---\n{question}\n"
        "\nAnswer (Gemini's, asked to use only the chunks found):\nAn answer.\n"
        "\nSources (the articles of the chunks found, closest first):\n"
        + "".join(f"  {title}\n" for title in titles))


def test_print_answer_alone_prints_the_answer_under_its_heading(capsys):
    print_answer_alone("I don't know.")
    assert capsys.readouterr().out == ("\nFor comparison, the same question to Gemini alone, with no articles:\n"
                                       "I don't know.\n")
