"""
Tests for pipeline.py: the steps it runs and what it prints, with KeywordEmbeddings, a stand-in for Gemini
(tests/fakes.py), and that it's the only file that runs anything. Without a key, it stops with a message instead:
test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, KeywordEmbeddings

from pipeline import main
from retriever import QUESTIONS

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def test_the_pipeline_embeds_the_chunks_then_the_question_by_hand_then_through_the_retriever(capsys):
    stand_in = KeywordEmbeddings()
    main(embeddings=stand_in, size=SIZE)
    printed = capsys.readouterr().out
    question = QUESTIONS[0]
    assert stand_in.calls == [("documents", 28), ("query", question), ("query", question)]
    assert printed.startswith("Step 1: Read the knowledge base: 10 documents\n"
                              "Step 2: Chunk: 28 chunks of at most 512 characters\n"
                              "Step 3: Embed and store: 28 points, in Qdrant in memory\n"
                              "Step 4: Retrieve\n"
                              f"Question: {question}\nThe question became {SIZE} numbers: [")
    assert "\n\nWhat a prompt gets, the 2 closest chunks as one text (format_docs):\n[1] " in printed


def test_a_question_of_your_own(capsys):
    stand_in = KeywordEmbeddings()
    main("my email bounced", embeddings=stand_in, size=SIZE)
    assert stand_in.calls[1:] == [("query", "my email bounced")] * 2
    assert "\nQuestion: my email bounced\n" in capsys.readouterr().out


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
