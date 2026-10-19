"""
Tests for vector_store.py: the collection, filling it with the 28 chunks, what each stored point holds, that the
script stores without ever embedding a question, and the script with a Qdrant server (QDRANT_URL). The plain tests
use KeywordEmbeddings, a stand-in for Gemini (tests/fakes.py), and Qdrant in memory, also standing in for the
server: no Docker needed. The live test asks the real Gemini.
"""
import runpy
import sys
from pathlib import Path

import pytest
import qdrant_client
from fakes import SIZE, KeywordEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

import models
from models import EMBEDDING_SIZE, embeddings
from vector_store import COLLECTION, add_knowledge_base, make_vector_store

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DASHBOARD = ("See them in Qdrant's dashboard: http://localhost:6333/dashboard\n"
             "In GitHub Codespaces: open the Ports tab, open the address for port 6333, and add /dashboard to it.\n")


def run_script(monkeypatch, capsys, qdrant_url=""):
    """Runs vector_store.py as `python vector_store.py` does, with the stand-in for Gemini, and gives back the stand-in
    and what the script printed. qdrant_url is what QDRANT_URL is set to: "" means Qdrant in memory."""
    stand_in = KeywordEmbeddings()
    monkeypatch.setattr(models, "embeddings", stand_in)       # the script's `from models import ...` gets these
    monkeypatch.setattr(models, "EMBEDDING_SIZE", SIZE)
    monkeypatch.setenv("QDRANT_URL", qdrant_url)              # set, even to "", so a .env can't change it
    monkeypatch.setattr(sys, "argv", ["vector_store.py"])
    runpy.run_path(str(FOLDER / "vector_store.py"), run_name="__main__")
    return stand_in, capsys.readouterr().out


def test_a_new_store_has_an_empty_cosine_collection_of_the_right_size():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    params = store.client.get_collection(COLLECTION).config.params.vectors
    assert (params.size, params.distance) == (SIZE, Distance.COSINE)
    assert store.client.count(COLLECTION).count == 0


def test_adding_the_knowledge_base_stores_28_chunks_in_one_embedding_call():
    stand_in = KeywordEmbeddings()
    store = make_vector_store(stand_in, SIZE)
    chunks = add_knowledge_base(store)
    assert len(chunks) == 28
    assert store.client.count(COLLECTION).count == 28
    assert stand_in.calls == [("documents", 28)]


def test_each_point_holds_a_vector_the_chunks_text_and_its_labels():
    store = make_vector_store(KeywordEmbeddings(), SIZE)
    chunks = add_knowledge_base(store)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == SIZE for point in points)
    assert sorted(point.payload["page_content"] for point in points) == sorted(chunk.page_content for chunk in chunks)
    assert {"doc_id", "title", "system", "category", "start_index"} <= set(points[0].payload["metadata"])


def test_an_existing_collection_is_kept():
    client = QdrantClient(":memory:")
    add_knowledge_base(make_vector_store(KeywordEmbeddings(), SIZE, client))
    make_vector_store(KeywordEmbeddings(), SIZE, client)          # the same client again: the points are still there
    assert client.count(COLLECTION).count == 28


def test_running_it_stores_the_chunks_in_memory_and_never_embeds_a_question(monkeypatch, capsys):
    stand_in, printed = run_script(monkeypatch, capsys)
    lines = printed.splitlines()
    assert stand_in.calls == [("documents", 28)]              # one call for the chunks, and no embed_query: no question
    assert lines[0] == "Qdrant: in memory, inside this script"
    assert lines[1] == f"Collection 'it_knowledge_base': 28 points, vectors of {SIZE} numbers, compared by Cosine"
    assert lines[2] == "Each point holds an id, a vector and a payload with metadata, page_content"
    assert lines[4] == (f"Point 1 of 28: VPN Connection Timeout, from character 0: {SIZE} numbers, "
                        "457 characters of text, 7 labels")
    assert sum(line.startswith("Point ") for line in lines) == 28
    assert "dashboard" not in printed                         # no server, so no dashboard


def test_with_qdrant_url_it_uses_that_server_and_starts_fresh_on_each_run(monkeypatch, capsys):
    server = QdrantClient(":memory:")                         # stands in for the server: the same one on every run

    class TheServer(QdrantClient):
        """What the script gets for QdrantClient(url=...): always the same in-memory client, `server`."""

        def __new__(cls, *args, **kwargs):
            return server

    monkeypatch.setattr(qdrant_client, "QdrantClient", TheServer)
    run_script(monkeypatch, capsys, "http://localhost:6333")
    _, printed = run_script(monkeypatch, capsys, "http://localhost:6333")
    assert server.count(COLLECTION).count == 28               # the second run replaced the first run's points
    assert printed.startswith("Qdrant: the server at http://localhost:6333\n"
                              "Collection 'it_knowledge_base': 28 points, ")
    assert printed.endswith("\n\n" + DASHBOARD)


def test_with_qdrant_url_but_no_server_it_stops_and_says_what_to_do(monkeypatch, capsys):
    with pytest.raises(SystemExit) as stop:
        run_script(monkeypatch, capsys, "http://localhost:6399")       # nothing answers on that port
    assert str(stop.value) == ("Can't reach Qdrant at http://localhost:6399. Start it first, in this folder: "
                               "docker compose up -d (or remove QDRANT_URL from .env to run Qdrant in memory).")


@pytest.mark.live
def test_live_the_28_chunks_are_stored_with_768_number_vectors():
    store = make_vector_store(embeddings, EMBEDDING_SIZE)
    add_knowledge_base(store)
    points, _ = store.client.scroll(COLLECTION, limit=100, with_vectors=True)
    assert len(points) == 28
    assert all(len(point.vector) == EMBEDDING_SIZE for point in points)
