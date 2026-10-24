"""
IT Knowledge Base: The Pipeline
===============================

The file to run in the terminal: it calls the app's steps in order, and the other files define them. It handles:
  1. Step 1: building the engine: reading, chunking, embedding and storing the articles (one call to Gemini)
  2. Step 2: answering each question with up to 3 sources (two calls each), then printing it

Usage:
    python pipeline.py                       # answers to the three sample questions
    python pipeline.py "printer not found"   # the answer to your question
"""
import sys

from rag_engine import RAGEngine
from retriever import QUESTIONS
from utils import print_result


# The tests pass an engine with stand-ins for Gemini
def main(questions: list[str] = QUESTIONS, engine: RAGEngine | None = None) -> None:
    """Run every step in order: the build in one line, then each answer in full."""
    engine = engine if engine is not None else RAGEngine()
    engine.build()
    stats = engine.stats()
    print(f"Step 1: Build the engine: {stats['documents']} articles, {stats['chunks']} chunks")
    print("Step 2: Answer")
    print()
    for question in questions:
        print_result(question, engine.query(question))


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()
    main([question] if question else QUESTIONS)     # no question, or only spaces: the sample questions
