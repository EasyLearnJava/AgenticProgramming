"""
Tests for pipeline.py: the steps it runs and what it prints, with an engine that uses stand-ins for Gemini
(tests/fakes.py), and that it's the only file that runs anything in the terminal. Without a key, it stops with a
message instead: test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, FakeListChatModel, KeywordEmbeddings

from pipeline import main
from rag_engine import RAGEngine
from retriever import QUESTIONS

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def stand_in_engine():
    return RAGEngine(embeddings=KeywordEmbeddings(), model=FakeListChatModel(responses=["An answer."]),
                     embedding_size=SIZE)


def test_the_pipeline_builds_the_engine_then_answers_each_question(capsys):
    engine = stand_in_engine()
    main(QUESTIONS, engine)
    printed = capsys.readouterr().out
    assert engine.embeddings.calls[0] == ("documents", 28)    # the chunks, embedded once, in the build
    assert printed.startswith("Step 1: Build the engine: 10 articles, 28 chunks\n"
                              "Step 2: Answer\n\n"
                              f"Q: {QUESTIONS[0]}\nA: An answer.\n"
                              "   source: VPN Connection Timeout (VPN, Remote Access)\n")
    assert [line for line in printed.splitlines() if line.startswith("Q: ")] == [f"Q: {q}" for q in QUESTIONS]


def test_a_question_of_your_own(capsys):
    main(["printer not found"], stand_in_engine())
    printed = capsys.readouterr().out
    assert [line for line in printed.splitlines() if line.startswith("Q: ")] == ["Q: printer not found"]


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
