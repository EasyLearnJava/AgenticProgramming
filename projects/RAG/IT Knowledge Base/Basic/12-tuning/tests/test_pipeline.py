"""
Tests for pipeline.py: the steps it runs and what it prints, with an engine that uses stand-ins for Gemini
(tests/fakes.py) and Qdrant in memory, standing in for the server; what it says when no Qdrant server answers; and
that it's the only file that runs anything in the terminal. Without a key, it stops with a message instead:
test_models.py checks that.
"""
from pathlib import Path

import pytest
from fakes import SIZE, FakeListChatModel, KeywordEmbeddings
from qdrant_client import QdrantClient

from pipeline import main
from rag_engine import RAGEngine
from retriever import QUESTIONS
from vector_store import QDRANT_URL, make_client

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def stand_in_engine(client):
    return RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                     embedding_size=SIZE, client=client)


def test_the_pipeline_builds_the_engine_then_answers_each_question(capsys):
    engine = stand_in_engine(QdrantClient(":memory:"))
    main(QUESTIONS, engine)
    printed = capsys.readouterr().out
    assert engine.embeddings.calls[0] == ("documents", 28)    # the chunks, embedded once, in the build
    assert printed.startswith(f"Step 1: Build the engine: 10 articles, 28 chunks (embedded and stored) in Qdrant at "
                              f"{QDRANT_URL}\n"
                              "Step 2: Answer\n\n"
                              f"Q: {QUESTIONS[0]}\nA: An answer.\n"
                              "   source: VPN Connection Timeout (VPN, Remote Access)\n")
    assert [line for line in printed.splitlines() if line.startswith("Q: ")] == [f"Q: {q}" for q in QUESTIONS]


def test_a_second_run_reuses_the_stored_chunks(capsys):
    client = QdrantClient(":memory:")
    main(["printer not found"], stand_in_engine(client))
    capsys.readouterr()                                       # what the first run printed
    engine = stand_in_engine(client)
    main(["printer not found"], engine)
    assert capsys.readouterr().out.startswith("Step 1: Build the engine: 10 articles, 28 chunks (already stored, "
                                              "reused) in Qdrant at ")
    assert engine.embeddings.calls == [("query", "printer not found")]   # only the question: no chunk embedded again


def test_without_qdrant_it_stops_and_says_what_to_do():
    # Nothing answers on port 6399, so the build can't reach Qdrant.
    engine = stand_in_engine(make_client("http://localhost:6399"))
    with pytest.raises(SystemExit, match=r"Can't reach Qdrant at .*docker compose up -d"):
        main(QUESTIONS, engine)
    assert engine.embeddings.calls == []                      # nothing was embedded


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == sorted(name for name in ("pipeline.py", "tuning.py") if (FOLDER / name).exists())
