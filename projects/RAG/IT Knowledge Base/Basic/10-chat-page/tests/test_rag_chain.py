"""
Tests for rag_chain.py: the prompt, and the chain's three results (the chunks, the question, the answer). The plain
tests use stand-ins for Gemini (tests/fakes.py); the live test asks the real Gemini.
"""
import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from chunking import split_documents
from embed_chunks import embed_chunks
from knowledge_base import load_documents
from models import EMBEDDING_SIZE, chat_model, embeddings
from rag_chain import make_rag_chain, prompt
from retriever import QUESTIONS, make_retriever
from vector_store import make_vector_store, store_vectors

CHUNKS = split_documents(load_documents())
VECTORS = embed_chunks(CHUNKS, KeywordEmbeddings())     # a stand-in vector for each chunk, in order


def stand_in_retriever():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    store_vectors(store, CHUNKS, VECTORS)
    return make_retriever(store)


def test_the_prompt_has_the_rules_and_articles_then_the_question():
    system, human = prompt.invoke({"context": "[1] An article\nIts text", "question": "Why?"}).to_messages()
    assert system.type == "system" and human.type == "human"
    assert "using only the knowledge base articles below" in system.content
    assert "say that the knowledge base doesn't cover it" in system.content
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


@pytest.fixture(scope="module")
def live_chain():
    """The chain on the real Gemini, built once for the two live tests below: the 28 chunks embedded in one call."""
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    store_vectors(store, CHUNKS, embed_chunks(CHUNKS, embeddings))
    return make_rag_chain(make_retriever(store), chat_model)


@pytest.mark.live
def test_live_the_vpn_question_finds_the_vpn_article_first_and_gets_an_answer(live_chain):
    result = live_chain.invoke(QUESTIONS[0])
    assert result["docs"][0].metadata["title"] == "VPN Connection Timeout"
    assert result["answer"].strip()


@pytest.mark.live
def test_live_an_off_topic_question_is_answered_as_not_covered(live_chain):
    # The prompt asks for "the knowledge base doesn't cover it". A model mostly does as it's asked, not always.
    answer = live_chain.invoke("How do I bake bread?")["answer"].lower()
    assert "cover" in answer
    assert "flour" not in answer and "yeast" not in answer        # and no recipe from what Gemini knows
