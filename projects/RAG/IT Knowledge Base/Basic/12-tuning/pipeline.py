"""
IT Knowledge Base: The Pipeline
===============================

The file to run in the terminal: it calls the app's steps in order, and the other files define them. It handles:
  1. Step 1: building the engine: reading and chunking the articles, then reusing the chunks the Qdrant server holds,
     or embedding and storing them (one call to Gemini)
  2. Step 2: answering each question with up to 3 sources (two calls each), then printing it

Usage (the Qdrant server must be running first: docker compose up -d):
    python pipeline.py                       # answers to the three sample questions
    python pipeline.py "printer not found"   # the answer to your question
"""
import sys

from qdrant_client.http.exceptions import ResponseHandlingException

from rag_engine import RAGEngine
from retriever import QUESTIONS
from utils import print_result
from vector_store import QDRANT_URL


# The tests pass an engine with stand-ins for Gemini
def main(questions: list[str] = QUESTIONS, engine: RAGEngine | None = None) -> None:
    """Run every step in order: the build in one line, then each answer in full."""
    engine = engine if engine is not None else RAGEngine()
    try:
        engine.build()
    except ResponseHandlingException as err:
        # No Qdrant server answered at QDRANT_URL: say what to do, instead of a stack trace
        sys.exit(f"Can't reach Qdrant at {QDRANT_URL} ({err}). "
                 "Start it first, in this folder:   docker compose up -d")
    stats = engine.stats()
    how = "already stored, reused" if stats["reused_stored_chunks"] else "embedded and stored"
    print(f"Step 1: Build the engine: {stats['documents']} articles, {stats['chunks']} chunks ({how}) "
          f"in Qdrant at {QDRANT_URL}")
    print("Step 2: Answer")
    print()
    for question in questions:
        print_result(question, engine.query(question))


if __name__ == "__main__":
    main([" ".join(sys.argv[1:])] if len(sys.argv) > 1 else QUESTIONS)
