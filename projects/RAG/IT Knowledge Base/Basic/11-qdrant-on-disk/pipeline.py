"""
IT Knowledge Base: The Pipeline
===============================

The file to run in the terminal: it calls the app's steps in order, and the other files define them. It handles:
  1. Step 1: building the engine: reading and chunking the articles, then reusing the chunks saved in qdrant_data/,
     or embedding and storing them (one call to Gemini)
  2. Step 2: answering each question with up to 3 sources (two calls each), then printing it

Usage:
    python pipeline.py                       # answers to the three sample questions
    python pipeline.py "printer not found"   # the answer to your question
"""
import sys

from rag_engine import RAGEngine
from retriever import QUESTIONS
from utils import print_result
from vector_store import QDRANT_PATH


# The tests pass an engine with stand-ins for Gemini
def main(questions: list[str] = QUESTIONS, engine: RAGEngine | None = None) -> None:
    """Run every step in order: the build in one line, then each answer in full."""
    engine = engine if engine is not None else RAGEngine()
    engine.build()
    stats = engine.stats()
    how = "already stored, reused" if stats["reused_stored_chunks"] else "embedded and stored"
    print(f"Step 1: Build the engine: {stats['documents']} articles, {stats['chunks']} chunks ({how}) "
          f"in {QDRANT_PATH.name}/")
    print("Step 2: Answer")
    print()
    for question in questions:
        print_result(question, engine.query(question))


if __name__ == "__main__":
    main([" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS)
