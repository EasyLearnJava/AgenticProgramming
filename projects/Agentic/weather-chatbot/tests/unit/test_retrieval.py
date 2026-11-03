"""The playground explains the real retriever's scores, scope, limits and fallback without asking Gemini."""

import asyncio
import math
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.parks import ParkKnowledge
from tests.unit.test_parks import chunk, write_index


async def query_vector(_text: str) -> list[float]:
    """A known semantic direction so ranking assertions never depend on native model weights."""
    return [1.0, 0.0]


def scored_knowledge(tmp_path: Path) -> ParkKnowledge:
    """Keyword evidence, a semantic-only match and a below-threshold chunk in the same destination."""
    path = write_index(
        tmp_path / "scores.sqlite",
        [
            chunk("keyword", "Clothing", ["zion-narrows"]),
            chunk("meaning", "Attire", ["zion-narrows"]),
            chunk("irrelevant", "Restaurant", ["zion-narrows"]),
            chunk("other-park", "Clothing", ["yosemite"], park_id="yosemite"),
        ],
        [[0.0, 1.0], [1.0, 0.0], [0.6, 0.8], [1.0, 0.0]],
    )
    return ParkKnowledge(path, query_vector, "test-model")


def test_explanation_uses_the_actual_scores_order_and_selected_passages(tmp_path: Path) -> None:
    knowledge = scored_knowledge(tmp_path)
    normal = asyncio.run(knowledge.search("zion-narrows", "clothing"))
    explained = asyncio.run(knowledge.search("zion-narrows", "clothing", explain=True))
    diagnostics = explained.pop("diagnostics")
    assert explained == normal
    assert "diagnostics" not in normal
    assert [item["id"] for item in normal["passages"]] == ["meaning", "keyword"]
    assert diagnostics["candidate_count"] == 3
    rows = diagnostics["candidates"]
    assert [item["chunk"]["id"] for item in rows] == ["meaning", "keyword", "irrelevant"]
    assert [item["rank"] for item in rows] == [1, 2, None]
    assert rows[0]["keyword_score"] == 0
    assert rows[0]["semantic_score"] == pytest.approx(1)
    assert rows[0]["final_score"] == pytest.approx(1)
    # With equal-length passages and one term present in one of three, BM25 is ln(1 + 2.5 / 1.5).
    expected_keyword = math.log(1 + 2.5 / 1.5)
    assert rows[1]["keyword_score"] == pytest.approx(expected_keyword)
    assert rows[1]["keyword_component"] == pytest.approx(expected_keyword / (1 + expected_keyword))
    assert rows[1]["semantic_score"] == pytest.approx(0)
    assert rows[1]["final_score"] == pytest.approx(expected_keyword / (1 + expected_keyword))
    assert [item["selection"] for item in rows] == ["retrieved", "retrieved", "below_threshold"]
    assert rows[2]["semantic_score"] == pytest.approx(0.6)


def test_explanation_distinguishes_result_limits_from_the_context_budget(tmp_path: Path) -> None:
    passages = [chunk(f"item-{index}", "Clothing", ["zion-narrows"]) for index in range(6)]
    service = ParkKnowledge(write_index(tmp_path / "count.sqlite", passages))
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    assert len(result["passages"]) == 4
    assert [row["selection"] for row in result["diagnostics"]["candidates"]] == [
        "retrieved",
        "retrieved",
        "retrieved",
        "retrieved",
        "result_limit",
        "result_limit",
    ]
    long_passages = [chunk(f"long-{index}", "Clothing " * 880, ["zion-narrows"]) for index in range(3)]
    service = ParkKnowledge(write_index(tmp_path / "budget.sqlite", long_passages))
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    assert len(result["passages"]) == 1
    assert [row["selection"] for row in result["diagnostics"]["candidates"]] == [
        "retrieved",
        "context_limit",
        "context_limit",
    ]


def test_failed_embeddings_show_missing_semantic_scores_and_keep_keyword_ranking(tmp_path: Path) -> None:
    path = write_index(tmp_path / "fallback.sqlite", [chunk("item", "Clothing", ["zion"])], [[1.0, 0.0]])

    async def fail(_text: str) -> list[float]:
        """An unavailable local encoder, whose private error text must not appear in diagnostics or logs."""
        raise RuntimeError("private-model-error")

    with capture_logs() as lines:
        result = asyncio.run(ParkKnowledge(path, fail, "test-model").search("zion", "clothing", explain=True))
    row = result["diagnostics"]["candidates"][0]
    assert result["retrieval_mode"] == "lexical"
    assert row["semantic_score"] is None
    assert row["final_score"] == row["keyword_component"]
    assert "private-model-error" not in str(result) + str(lines)


def test_explanation_obeys_destination_and_season_before_scoring(tmp_path: Path) -> None:
    path = write_index(
        tmp_path / "season.sqlite",
        [
            chunk("summer", "Clothing", ["zion"], seasons=["summer"]),
            chunk("winter", "Clothing", ["zion"], seasons=["winter"]),
            chunk("trail-only", "Clothing", ["zion-narrows"]),
        ],
    )
    result = asyncio.run(ParkKnowledge(path).search("zion", "clothing", date(2026, 12, 1), explain=True))
    assert result["diagnostics"]["season"] == "winter"
    assert result["diagnostics"]["candidate_count"] == 1
    assert result["diagnostics"]["candidates"][0]["chunk"]["id"] == "winter"


def test_playground_is_linked_and_does_not_embed_until_a_question_is_submitted(client: TestClient) -> None:
    page = client.get("/knowledge/retrieval")
    assert page.status_code == 200
    assert 'href="/knowledge/retrieval" aria-current="page"' in page.text
    assert "Retrieval Playground" in page.text
    assert "Run retrieval" in page.text
    assert "No question run yet" in page.text
    assert 'id="retrieval-ranking"' not in page.text
    assert page.headers["cache-control"] == "no-store"


def test_playground_shows_real_hybrid_scores_and_links_without_gemini(client: TestClient, tmp_path: Path) -> None:
    app = cast(FastAPI, client.app)
    app.state.park_knowledge = scored_knowledge(tmp_path)
    app.state.chat_model = None
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion-narrows", "q": "clothing"})
    assert page.status_code == 200
    assert "Hybrid retrieval" in page.text
    assert 'data-chunk="meaning" data-selection="retrieved"' in page.text
    assert 'data-chunk="irrelevant" data-selection="below_threshold"' in page.text
    assert 'data-chunk="other-park"' not in page.text
    assert "0.6000" in page.text
    assert "1.0000" in page.text
    assert "Keyword score" in page.text
    assert "Semantic score" in page.text
    assert "Final score" in page.text
    assert "Below relevance threshold" in page.text
    assert "chunk=meaning" in page.text
    assert 'href="/knowledge/sources/narrows-guide"' in page.text


def test_playground_explains_lexical_fallback_and_no_matches(client: TestClient) -> None:
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion", "q": "zzzzunmatched"})
    assert page.status_code == 200
    assert "Keyword-only retrieval" in page.text
    assert "Semantic scoring was unavailable" in page.text
    assert "No chunks retrieved" in page.text
    assert "Not available" in page.text


@pytest.mark.parametrize(
    "params",
    [
        {"destination": "zion", "q": "x" * 1001},
        {"destination": "../zion", "q": "clothing"},
        {"destination": "unknown", "q": "clothing"},
        {"destination": "zion", "q": "clothing", "visit_date": "2026-02-30"},
        {"destination": "zion", "unknown": "x"},
        {"q": "clothing"},
    ],
)
def test_playground_validates_all_inputs(client: TestClient, params: dict[str, str]) -> None:
    assert client.post("/api/knowledge/retrieval", data=params).status_code == 400


def test_playground_escapes_questions_and_passages_and_retains_form_values(client: TestClient, tmp_path: Path) -> None:
    path = write_index(tmp_path / "escape.sqlite", [chunk("item", "<script>unsafe()</script> Clothing", ["zion"])])
    cast(FastAPI, client.app).state.park_knowledge = ParkKnowledge(path)
    page = client.post(
        "/api/knowledge/retrieval",
        data={"destination": "zion", "q": "<script>private()</script> clothing", "visit_date": "2026-12-01"},
    )
    assert page.status_code == 200
    assert "<script>" not in page.text
    assert "&lt;script&gt;" in page.text
    assert 'value="2026-12-01"' in page.text
    assert 'value="zion" selected' in page.text


def test_disabled_and_missing_indexes_have_explicit_states(client: TestClient, tmp_path: Path) -> None:
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(update={"parks_enabled": False})
    app.state.park_knowledge = None
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion", "q": "clothing"})
    assert page.status_code == 200
    assert "Retrieval is disabled" in page.text
    app.state.settings = app.state.settings.model_copy(update={"parks_enabled": True})
    app.state.park_knowledge = ParkKnowledge(tmp_path / "missing.sqlite")
    delattr(app.state, "knowledge_catalog")
    assert "Knowledge index unavailable" in client.get("/knowledge/retrieval").text
