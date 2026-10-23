"""
Tests for pipeline.py: the steps it runs and what it prints, in memory and with a Qdrant server (QDRANT_URL), and that
it's the only file that runs anything. The tests use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and
Qdrant in memory, also standing in for the server: no Docker needed. Without a key, the pipeline stops with a message
instead: test_models.py checks that.
"""
from pathlib import Path

import pytest
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient

import pipeline
import utils
from vector_store import COLLECTION

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
STEPS = ("Step 1: Read the knowledge base: 10 documents\n"
         "Step 2: Chunk: 28 chunks of at most 512 characters\n"
         "Step 3: Embed and store\n")
DASHBOARD = ("See them in Qdrant's dashboard: http://localhost:6333/dashboard\n"
             "In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.\n")


def run(capsys, qdrant_url=""):
    """Runs the pipeline with the stand-in for Gemini, and gives back the stand-in and what the pipeline printed.
    qdrant_url is the Qdrant server's address: "" means Qdrant in memory."""
    stand_in = KeywordEmbeddings()
    pipeline.main(embeddings=stand_in, size=SIZE, qdrant_url=qdrant_url)
    return stand_in, capsys.readouterr().out


def test_the_pipeline_stores_the_chunks_in_memory_and_never_embeds_a_question(capsys):
    stand_in, printed = run(capsys)
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    assert printed.startswith(STEPS + "Qdrant: in memory, inside this script\n"
                              f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, "
                              "compared by Cosine\n")
    assert sum(line.startswith("Point ") for line in printed.splitlines()) == 28
    assert "dashboard" not in printed                         # no server, so no dashboard


def test_with_qdrant_url_it_uses_that_server_and_starts_fresh_on_each_run(monkeypatch, capsys):
    server = QdrantClient(":memory:")                         # stands in for the server: the same one on every run

    class TheServer(QdrantClient):
        """What connect() gets for QdrantClient(url=...): always the same in-memory client, `server`."""

        def __new__(cls, *args, **kwargs):
            return server

    monkeypatch.setattr(utils, "QdrantClient", TheServer)
    run(capsys, "http://localhost:6333")
    _, printed = run(capsys, "http://localhost:6333")
    assert server.count(COLLECTION).count == 28               # the second run replaced the first run's points
    assert printed.startswith(STEPS + "Qdrant: the server at http://localhost:6333\n"
                              "Collection 'it_knowledge_base': 28 points, ")
    assert printed.endswith("\n\n" + DASHBOARD)


def test_with_qdrant_url_but_no_server_it_stops_and_says_what_to_do(capsys):
    with pytest.raises(SystemExit) as stop:
        run(capsys, "http://localhost:6399")                  # nothing answers on that port
    assert str(stop.value) == ("Can't reach Qdrant at http://localhost:6399. Start it first, in this folder: "
                               "docker compose up -d (or remove QDRANT_URL from .env to run Qdrant in memory).")


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
