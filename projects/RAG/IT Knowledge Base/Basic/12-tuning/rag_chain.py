"""
IT Knowledge Base: A Grounded Answer
====================================

Answers a question from the knowledge base only: the retriever's chunks and the question go into one prompt, and
Gemini answers from those chunks. That is RAG: retrieval first, then generation. It handles:
  1. The prompt: the rules and the chunks, then the question
  2. The chain: retriever, prompt, chat model and parser, keeping the chunks found as the sources

    question ──┬──> retriever ─────────────> docs ──┐
               └──> passed through ──────> question ┴─> prompt -> chat model -> parser -> answer

Usage:
    python rag_chain.py                          # the answer to the VPN question, and its sources
    python rag_chain.py "my printer is missing"  # the answer to your question (3 calls to Gemini)
"""
import sys

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough

from models import EMBEDDING_SIZE, chat_model, embeddings
from retriever import format_docs, make_retriever
from vector_store import add_knowledge_base, make_vector_store

QUESTION = "How do I fix VPN connection timeouts?"

# "Only the articles below" keeps the answer grounded, instead of in what the model learned in training
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles below. "
     "If they don't cover the question, say that the knowledge base doesn't cover it. Keep the answer short and "
     "practical, and name the articles you used.\n\nArticles:\n{context}"),
    ("human", "{question}"),
])


def make_rag_chain(retriever: BaseRetriever, model: BaseChatModel) -> Runnable:
    """The chain: question -> {"docs": the chunks found, "question": ..., "answer": Gemini's answer}."""
    answer = (
        (lambda x: {"context": format_docs(x["docs"]), "question": x["question"]})
        | prompt
        | model
        | StrOutputParser()
    )
    # Retrieve and pass the question through side by side, then add the answer, keeping "docs" for the sources
    return RunnableParallel(docs=retriever, question=RunnablePassthrough()).assign(answer=answer)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or QUESTION
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    chain = make_rag_chain(make_retriever(store), chat_model)
    result = chain.invoke(question)                  # retrieval, prompt and answer, all in this one call
    print(f"Question: {question}\n")
    print("Answer (Gemini's, from the chunks found):")
    print(result["answer"])
    print("\nSources (the articles of the chunks found, closest first):")
    for title in dict.fromkeys(doc.metadata["title"] for doc in result["docs"]):   # each title once, in order
        print(f"  {title}")
