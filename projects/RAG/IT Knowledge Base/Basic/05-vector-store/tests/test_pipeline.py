"""
Tests for pipeline.py: the steps it runs and what it prints, with Qdrant in local mode saving its points in a folder
of the test's own, and that it's the only file that runs anything. The tests use KeywordEmbeddings, a stand-in for
Gemini (tests/fakes.py). Without a key, the pipeline stops with a message instead: test_models.py checks that.
"""
from pathlib import Path

from fakes import SIZE, KeywordEmbeddings

import pipeline
from vector_store import COLLECTION, make_client

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
STEPS = ("Step 1: Read the knowledge base: 10 documents\n"
         "Step 2: Chunk: 28 chunks of at most 512 characters\n"
         f"Step 3: Embed: 28 vectors of {SIZE} numbers\n"
         "Step 4: Store\n")


def run(capsys, qdrant_path):
    """Runs the pipeline with the stand-in for Gemini and its points saved in the folder qdrant_path, and gives back
    the stand-in and what the pipeline printed."""
    stand_in = KeywordEmbeddings()
    pipeline.main(embeddings=stand_in, size=SIZE, qdrant_path=qdrant_path)
    return stand_in, capsys.readouterr().out


def test_the_pipeline_stores_the_chunks_on_disk_and_never_embeds_a_question(tmp_path, capsys):
    stand_in, printed = run(capsys, tmp_path)
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    assert printed.startswith(STEPS + "Qdrant: local mode, inside this script, saving its points in "
                              f"{tmp_path.name}/\n"
                              f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, "
                              "compared by Cosine\n")
    assert sum(line.startswith("Point ") for line in printed.splitlines()) == 28


def test_the_points_stay_in_the_folder_and_each_run_starts_fresh(tmp_path, capsys):
    run(capsys, tmp_path)
    run(capsys, tmp_path)                                     # a second run, on the same folder
    client = make_client(tmp_path)                            # opened again, as another program would after the run
    assert client.count(COLLECTION).count == 28               # the second run replaced the first run's points
    client.close()


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
