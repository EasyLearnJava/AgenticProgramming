"""
IT Knowledge Base: A Grounded Answer
====================================

Answers a question from the knowledge base only: the retriever's chunks and the question go into one prompt, and
Gemini answers from those chunks. That is RAG: retrieval first, then generation. It handles:
  1. The prompt: the rules and the chunks, then the question
  2. The chain: retriever, prompt, chat model and parser, keeping the chunks found as the sources

    question ──┬──> retriever ─────────────> docs ──┐
               └──> passed through ──────> question ┴─> prompt -> chat model -> parser -> answer

Usage (this file only defines these; pipeline.py runs the steps):
    chain = make_rag_chain(make_retriever(store), chat_model)   ->  question in, {"docs", "question", "answer"} out
"""
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import Runnable, RunnableParallel, RunnablePassthrough

from retriever import format_docs

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
