"""The knowledge browser exposes the actual public corpus, keeps filters scoped, and projects genuine vectors."""

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nimbus.knowledge import project_vectors
from nimbus.parks import ParkKnowledge


def test_sources_show_real_counts_links_and_the_knowledge_menu(client: TestClient) -> None:
    page = client.get("/knowledge/sources")
    assert page.status_code == 200
    assert "Source documents" in page.text
    assert 'aria-labelledby="menu-knowledge"' in page.text
    assert 'href="/knowledge/chunks"' in page.text
    assert "13 documents" in page.text
    assert "40 chunks" in page.text
    assert "narrowssafety.htm" in page.text
    assert "Indexed" in page.text


def test_source_filters_and_details_follow_the_index(client: TestClient) -> None:
    scoped = client.get("/knowledge/sources", params={"park": "zion"})
    assert 'data-park="yosemite"' not in scoped.text
    assert 'data-park="grand-canyon"' not in scoped.text
    filtered = client.get("/knowledge/sources", params={"park": "yosemite", "q": "lightning"})
    assert "1 of 13 documents" in filtered.text
    assert "Yosemite" in filtered.text
    detail = client.get("/knowledge/sources/zion-narrows-safety")
    assert detail.status_code == 200
    assert "Indexed passages" in detail.text
    assert "waterproof" in detail.text
    assert "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm" in detail.text
    assert client.get("/knowledge/sources/missing").status_code == 404


def test_chunk_page_shows_vectors_pca_and_source_provenance(client: TestClient) -> None:
    page = client.get("/knowledge/chunks")
    assert page.status_code == 200
    assert "Chunks &amp; vectors" in page.text
    assert "384 dimensions" in page.text
    assert 'id="embedding-map"' in page.text
    assert "PCA" in page.text
    assert "approximate" in page.text
    assert "Vector components" in page.text
    assert 'id="chunk-detail"' in page.text
    assert "all-MiniLM-L6-v2" in page.text
    assert page.headers["cache-control"] == "no-store"


def test_chunk_filters_do_not_show_other_parks_and_selection_is_checked(client: TestClient) -> None:
    page = client.get("/knowledge/chunks", params={"park": "yosemite", "q": "lightning"})
    assert page.status_code == 200
    assert "yosemite-lightning-" in page.text
    assert 'data-park="zion"' not in page.text
    assert client.get("/knowledge/chunks", params={"chunk": "missing"}).status_code == 404
    assert client.get("/knowledge/chunks", params={"document": "missing"}).status_code == 404


@pytest.mark.parametrize("params", [{"park": "other"}, {"q": "x" * 121}, {"unknown": "value"}])
def test_knowledge_filters_are_validated_at_the_edge(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/knowledge/sources", params=params).status_code == 400


def test_no_results_and_missing_index_have_explicit_empty_states(client: TestClient, tmp_path: Path) -> None:
    assert "No documents match" in client.get("/knowledge/sources?q=zzzzunmatched").text
    assert "No chunks match" in client.get("/knowledge/chunks?q=zzzzunmatched").text
    cast(FastAPI, client.app).state.knowledge_catalog = ParkKnowledge(tmp_path / "missing.sqlite").inspection()
    page = client.get("/knowledge/chunks")
    assert page.status_code == 200
    assert "Knowledge index unavailable" in page.text
    assert 'id="embedding-map"' not in page.text


def test_inspection_is_a_copy_and_never_modifies_the_live_index(client: TestClient) -> None:
    settings = cast(FastAPI, client.app).state.settings
    service = ParkKnowledge(settings.parks_index_path)
    original = settings.parks_index_path.read_bytes()
    snapshot = service.inspection()
    snapshot["chunks"][0]["text"] = "changed"
    assert service.inspection()["chunks"][0]["text"] != "changed"
    assert settings.parks_index_path.read_bytes() == original


def test_chunk_text_is_escaped_in_the_browser(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    catalog = ParkKnowledge(app.state.settings.parks_index_path).inspection()
    catalog["chunks"][0]["text"] = "<script>alert('unsafe')</script>"
    app.state.knowledge_catalog = catalog
    page = client.get("/knowledge/chunks")
    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_projection_is_deterministic_and_handles_missing_or_degenerate_vectors() -> None:
    vectors = (("a", (1.0, 0.0, 0.0)), ("b", (0.0, 1.0, 0.0)), ("c", (0.0, 0.0, 1.0)))
    first = project_vectors(vectors)
    assert first == project_vectors(vectors)
    assert len(first["points"]) == 3
    assert all(60 <= point["x"] <= 740 and 30 <= point["y"] <= 350 for point in first["points"])
    assert 99 <= sum(first["variance"]) <= 100.1
    assert project_vectors(())["points"] == []
    assert len(project_vectors((("a", (1.0, 0.0)),))["points"]) == 1
