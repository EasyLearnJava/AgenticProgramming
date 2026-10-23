"""
Tests for rag_chain.py: the prompt, the chain's three results (the chunks, the question, the answer), and what
print_answer(), in utils.py, prints. The plain tests use stand-ins for Gemini (tests/fakes.py); the live test asks
the real Gemini.
"""
import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from chunking import split_documents
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import QUESTION, make_rag_chain, prompt
from retriever import make_retriever
from utils import print_answer
from vector_store import make_vector_store

CHUNKS = split_documents(load_documents())


def stand_in_retriever():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store.add_documents(CHUNKS)
    return make_retriever(store)


def test_the_prompt_has_the_rules_and_articles_then_the_question():
    system, human = prompt.invoke({"context": "[1] An article\nIts text", "question": "Why?"}).to_messages()
    assert system.type == "system" and human.type == "human"
    assert "using only the knowledge base articles below" in system.content
    assert system.content.endswith("Articles:\n[1] An article\nIts text")
    assert human.content == "Why?"


def test_the_chain_gives_the_chunks_the_question_and_the_answer():
    chain = make_rag_chain(stand_in_retriever(), FakeListChatModel(responses=["Open UDP ports 500 and 4500."]))
    result = chain.invoke("My VPN won't connect")
    assert set(result) == {"docs", "question", "answer"}
    assert result["question"] == "My VPN won't connect"
    assert result["answer"] == "Open UDP ports 500 and 4500."
    assert result["docs"][0].metadata["title"] == "VPN Connection Timeout"


def test_the_model_gets_the_chunks_it_found_as_the_articles():
    seen = []

    def stand_in_model(prompt_value):            # takes the model's place, and keeps what it was given
        seen.append(prompt_value.to_messages())
        return AIMessage(content="An answer.")

    make_rag_chain(stand_in_retriever(), RunnableLambda(stand_in_model)).invoke("My VPN won't connect")
    system, human = seen[0]
    assert "Articles:\n[1] VPN Connection Timeout\nTitle: VPN Connection Timeout" in system.content
    assert human.content == "My VPN won't connect"


def test_print_answer_prints_the_question_the_answer_then_each_article_once(capsys):
    docs = stand_in_retriever().invoke(QUESTION)
    print_answer(QUESTION, {"docs": docs, "question": QUESTION, "answer": "An answer."})
    titles = dict.fromkeys(doc.metadata["title"] for doc in docs)          # each title once, closest first
    assert capsys.readouterr().out == (f"Question: {QUESTION}\n\nAnswer (Gemini's, from the chunks found):\n"
                                       "An answer.\n\nSources (the articles of the chunks found, closest first):\n"
                                       + "".join(f"  {title}\n" for title in titles))


@pytest.mark.live
def test_live_the_vpn_answer_comes_from_the_vpn_article():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store.add_documents(CHUNKS)
    result = make_rag_chain(make_retriever(store), chat_model).invoke(QUESTION)
    assert result["answer"].strip()
    assert result["docs"][0].metadata["title"] == "VPN Connection Timeout"
