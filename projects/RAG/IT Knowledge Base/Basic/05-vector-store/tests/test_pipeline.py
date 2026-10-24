"""
Tests for pipeline.py: the steps it runs and what it prints, with Qdrant in memory, and that it's the only file that
runs anything. The tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py). Without a key, the pipeline
stops with a message instead: test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, KeywordEmbeddings

import pipeline

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
STEPS = ("Step 1: Read the knowledge base: 10 documents\n"
         "Step 2: Chunk: 28 chunks of at most 512 characters\n"
         f"Step 3: Embed: 28 vectors of {SIZE} numbers\n"
         "Step 4: Store\n")


def test_the_pipeline_stores_the_chunks_in_memory_and_never_embeds_a_question(capsys):
    stand_in = KeywordEmbeddings()
    pipeline.main(embeddings=stand_in, size=SIZE)
    printed = capsys.readouterr().out
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    assert printed.startswith(STEPS + "Qdrant: in memory, inside this script: the points are gone when it ends\n"
                              f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, "
                              "compared by Cosine\n")
    assert sum(line.startswith("Point ") for line in printed.splitlines()) == 28


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
