"""
IT Knowledge Base: Prompt Templates
===================================

The prompt the model answers from, kept apart from the code that fills it in, with a version that goes on every
answer's log line: when an answer changes, the trace says whether the prompt did. It handles:
  1. The answer prompt: the rules and the chunks found, then the question
  2. Turning the chunks into one numbered, titled text for it

Change PROMPT_VERSION whenever you change the prompt's text.

Usage:
    messages = ANSWER_PROMPT.format_messages(context=format_context(chunks), question=question)
"""
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

PROMPT_VERSION = "answer-v1"

# "Only the articles below" asks the model to answer from the chunks found, not from what it learned in training.
# Models mostly do as asked, but nothing here checks it: RAG makes made-up answers rarer, not impossible.
ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an IT help-desk assistant. Answer the user's question using only the knowledge base articles below. "
     "If they don't cover the question, say that the knowledge base doesn't cover it. Keep the answer short and "
     "practical, and name the articles you used.\n\nArticles:\n{context}"),
    ("human", "{question}"),
])


def format_context(chunks: list[Document]) -> str:
    """The chunks as one text, each numbered and titled so an answer can name its article."""
    return "\n\n".join(f"[{number}] {chunk.metadata['title']}\n{chunk.page_content}"
                       for number, chunk in enumerate(chunks, 1))
