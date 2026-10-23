"""
Tests for pipeline.py: the steps it runs and what it prints, with stand-ins for Gemini (tests/fakes.py), and that
it's the only file that runs anything. Without a key, it stops with a message instead: test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, FakeListChatModel, KeywordEmbeddings

from pipeline import main
from rag_chain import QUESTION

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def test_the_pipeline_retrieves_then_answers_from_the_chunks_found(capsys):
    stand_in = KeywordEmbeddings()
    main(embeddings=stand_in, model=FakeListChatModel(responses=["Open UDP ports 500 and 4500."]), size=SIZE)
    printed = capsys.readouterr().out
    assert stand_in.calls == [("documents", 28), ("query", QUESTION)]    # the chunks, then the question, once each
    assert printed.startswith("Step 1: Read the knowledge base: 10 documents\n"
                              "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                              f"Step 3: Embed: 28 vectors of {SIZE} numbers\n"
                              "Step 4: Store: 28 points, in Qdrant in memory\n"
                              "Step 5: Retrieve and answer\n"
                              f"Question: {QUESTION}\n\n"
                              "Answer (Gemini's, from the chunks found):\nOpen UDP ports 500 and 4500.\n\n"
                              "Sources (the articles of the chunks found, closest first):\n  VPN Connection Timeout\n")


def test_a_question_of_your_own(capsys):
    stand_in = KeywordEmbeddings()
    main("my printer is missing", embeddings=stand_in, model=FakeListChatModel(responses=["x"]), size=SIZE)
    assert stand_in.calls[1:] == [("query", "my printer is missing")]
    assert "\nQuestion: my printer is missing\n" in capsys.readouterr().out


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
