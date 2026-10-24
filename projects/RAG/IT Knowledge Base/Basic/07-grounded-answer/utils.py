"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing the prompt Gemini got, the answer, then the articles of the chunks found
  2. Printing Gemini's answer to the same question alone, with no articles

Usage (pipeline.py calls them; this file only defines them):
    print_answer(question, messages, chain.invoke(question))   ->  the prompt, the answer, then the articles
    print_answer_alone(answer)                                  ->  Gemini's answer with no articles
"""
from langchain_core.messages import BaseMessage


def print_answer(question: str, messages: list[BaseMessage], result: dict) -> None:
    """Print the question, the prompt's messages as Gemini got them, Gemini's answer, then the articles of the chunks
    found, each once, closest first."""
    print(f"Question: {question}\n")
    print(f"What Gemini got: the chain's prompt, filled in with the {len(result['docs'])} chunks found "
          "and the question")
    for message in messages:
        print(f"--- {message.type} message ---")
        print(message.content)
    print("\nAnswer (Gemini's, asked to use only the chunks found):")
    print(result["answer"])
    print("\nSources (the articles of the chunks found, closest first):")
    for title in dict.fromkeys(doc.metadata["title"] for doc in result["docs"]):   # each title once, in order
        print(f"  {title}")


def print_answer_alone(answer: str) -> None:
    """Print Gemini's answer to the same question, asked with no articles."""
    print("\nFor comparison, the same question to Gemini alone, with no articles:")
    print(answer)
