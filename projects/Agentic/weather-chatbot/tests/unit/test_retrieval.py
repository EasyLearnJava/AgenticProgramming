"""The playground explains the real retriever's scores, scope, limits and fallback without asking Gemini."""

import asyncio
import re
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.park_semantic import PARK_MODEL
from nimbus.parks import ParkKnowledge
from tests.park_fakes import FakeParkStore, knowledge_for
from tests.unit.test_parks import chunk


def scored_knowledge(tmp_path: Path) -> ParkKnowledge:
    """Keyword evidence, a semantic-only match and a below-threshold chunk in the same destination."""
    return knowledge_for(
        tmp_path,
        [
            chunk("keyword", "Clothing", ["zion-narrows"]),
            chunk("meaning", "Attire", ["zion-narrows"]),
            chunk("irrelevant", "Restaurant", ["zion-narrows"]),
            chunk(
                "other-park",
                "Clothing",
                ["yosemite"],
                park_id="yosemite",
                document_id="yosemite-guide",
                title="Yosemite guide",
                source_url="https://www.nps.gov/yose/planyourvisit/safety.htm",
            ),
        ],
        keyword_scores={"keyword": 2.5},
        semantic_scores={"keyword": 0.0, "meaning": 1.0, "irrelevant": 0.2},
    )


def test_explanation_uses_the_actual_scores_order_and_selected_passages(tmp_path: Path) -> None:
    knowledge = scored_knowledge(tmp_path)
    normal = asyncio.run(knowledge.search("zion-narrows", "clothing"))
    explained = asyncio.run(knowledge.search("zion-narrows", "clothing", explain=True))
    diagnostics = explained.pop("diagnostics")
    assert explained == normal
    assert "diagnostics" not in normal
    assert [item["id"] for item in normal["passages"]] == ["keyword", "meaning"]
    assert diagnostics["candidate_count"] == 3
    rows = diagnostics["candidates"]
    assert [item["chunk"]["id"] for item in rows] == ["keyword", "meaning", "irrelevant"]
    assert [item["rank"] for item in rows] == [1, 2, None]
    assert diagnostics["fusion"] == "rrf"
    assert diagnostics["rrf_k"] == 60
    assert diagnostics["keyword_terms"] == ["clothing"]
    assert rows[1]["keyword_score"] == 0
    assert rows[1]["semantic_score"] == pytest.approx(1)
    assert rows[1]["semantic_rank"] == 1
    assert rows[1]["keyword_rank"] is None
    assert rows[1]["semantic_component"] == pytest.approx(0.1 / 61)
    assert rows[1]["final_score"] == pytest.approx(0.1 / 61)
    # The displayed raw score must come from the remote branch, not a second local BM25 computation.
    assert rows[0]["keyword_score"] == pytest.approx(2.5)
    assert rows[0]["keyword_rank"] == 1
    assert rows[0]["keyword_component"] == pytest.approx(1 / 61)
    assert rows[0]["semantic_score"] == pytest.approx(0)
    assert rows[0]["semantic_rank"] is None
    assert rows[0]["semantic_component"] == 0
    assert rows[0]["final_score"] == pytest.approx(1 / 61)
    assert [item["selection"] for item in rows] == ["retrieved", "retrieved", "below_threshold"]
    assert rows[2]["semantic_score"] == pytest.approx(0.2)


def test_explanation_distinguishes_result_limits_from_the_context_budget(tmp_path: Path) -> None:
    passages = [chunk(f"item-{index}", "Clothing", ["zion-narrows"]) for index in range(6)]
    service = knowledge_for(tmp_path, passages)
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
    service = knowledge_for(tmp_path, long_passages)
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    assert len(result["passages"]) == 1
    assert [row["selection"] for row in result["diagnostics"]["candidates"]] == [
        "retrieved",
        "context_limit",
        "context_limit",
    ]


def test_failed_semantic_branch_keeps_only_verified_keyword_ranking(tmp_path: Path) -> None:
    service = knowledge_for(
        tmp_path, [chunk("item", "Clothing", ["zion"])], semantic_status="unavailable", keyword_scores={"item": 2.0}
    )
    with capture_logs() as lines:
        result = asyncio.run(service.search("zion", "clothing private-preparation-question", explain=True))
    row = result["diagnostics"]["candidates"][0]
    assert result["retrieval_mode"] == "lexical"
    assert row["semantic_score"] is None
    assert row["final_score"] == row["keyword_component"]
    assert result["semantic_status"] == "unavailable"
    assert result["keyword_status"] == "ready"
    assert "private-preparation-question" not in str(lines)


def test_explanation_obeys_destination_and_season_before_scoring(tmp_path: Path) -> None:
    service = knowledge_for(
        tmp_path,
        [
            chunk("summer", "Clothing", ["zion"], seasons=["summer"]),
            chunk("winter", "Clothing", ["zion"], seasons=["winter"]),
            chunk("trail-only", "Clothing", ["zion-narrows"]),
        ],
    )
    result = asyncio.run(service.search("zion", "clothing", date(2026, 12, 1), explain=True))
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
    service = cast(ParkKnowledge, cast(FastAPI, client.app).state.park_knowledge)
    assert all(call["method"] == "catalog" for call in cast(FakeParkStore, service.store).calls)


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
    assert "0.2000" in page.text
    assert "1.0000" in page.text
    assert "Keyword score" in page.text
    assert "Semantic score" in page.text
    assert "Final score" in page.text
    assert "Semantic contribution" in page.text
    assert "Reciprocal Rank Fusion" in page.text
    assert "Keyword terms used:" in page.text
    assert "0.0164" in page.text
    assert "Below relevance threshold" in page.text
    assert "chunk=meaning" in page.text
    assert 'href="/knowledge/sources/narrows-guide"' in page.text


def test_playground_explains_lexical_fallback_and_no_matches(client: TestClient) -> None:
    service = cast(ParkKnowledge, cast(FastAPI, client.app).state.park_knowledge)
    cast(FakeParkStore, service.store).semantic_status = "unavailable"
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion", "q": "zzzzunmatched"})
    assert page.status_code == 200
    assert "Keyword-only retrieval" in page.text
    assert "verified Qdrant keyword results" in page.text
    assert "No chunks retrieved" in page.text
    assert "Not available" in page.text


def test_failed_keyword_branch_never_appears_as_successful_hybrid(client: TestClient, tmp_path: Path) -> None:
    """Failure of required Qdrant BM25 produces an explicit unavailable view and skips dense work."""
    service = knowledge_for(tmp_path, [chunk("item", "Clothing", ["zion"])], keyword_status="unavailable")
    cast(FastAPI, client.app).state.park_knowledge = service
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion", "q": "clothing"})
    assert page.status_code == 200
    assert "Retrieval unavailable" in page.text
    assert "Keyword search did not complete" in page.text
    assert "Hybrid retrieval" not in page.text
    assert 'id="retrieval-ranking"' not in page.text
    assert not any(call["method"] == "semantic" for call in cast(FakeParkStore, service.store).calls)


def test_inspection_failure_does_not_hide_a_successful_retrieval(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A browser-catalog read can fail independently; the later search's verified evidence remains visible."""
    service = scored_knowledge(tmp_path)
    unavailable = asyncio.run(service.inspection())
    unavailable.update(available=False, status="timeout", chunks=[])
    monkeypatch.setattr(service, "inspection", AsyncMock(return_value=unavailable))
    cast(FastAPI, client.app).state.park_knowledge = service
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion-narrows", "q": "clothing"})
    assert page.status_code == 200
    assert "Knowledge index unavailable" in page.text
    assert "Hybrid retrieval" in page.text
    assert 'data-chunk="meaning" data-selection="retrieved"' in page.text


def test_hosted_playground_identifies_its_model_and_absent_dense_candidates(client: TestClient, tmp_path: Path) -> None:
    """Both branch scores come from Qdrant, and an absent semantic candidate is never displayed as zero."""
    service = scored_knowledge(tmp_path)
    cast(FakeParkStore, service.store).semantic_scores = {"meaning": 0.91}
    cast(FastAPI, client.app).state.park_knowledge = service
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion-narrows", "q": "clothing"})
    assert page.status_code == 200
    assert "Hybrid retrieval" in page.text
    assert "Qdrant Cloud MiniLM" in page.text
    assert PARK_MODEL in page.text
    assert "Keyword provider: Qdrant BM25" in page.text
    keyword_row = re.search(r'<tr data-chunk="keyword".*?</tr>', page.text, re.DOTALL)
    assert keyword_row is not None
    semantic_cell = re.findall(r'<td class="retrieval-score">(.*?)</td>', keyword_row.group(), re.DOTALL)[2]
    assert "Not returned" in semantic_cell
    assert "0.0000" not in semantic_cell
    assert "0.9100" in page.text
    assert "same hosted semantic vectors" in page.text
    assert "separately built local index" not in page.text
    assert "Inspect chunk &amp; vector" in page.text


@pytest.mark.parametrize(
    "params",
    [
        {"destination": "zion", "q": "x" * 1001},
        {"destination": "../zion", "q": "clothing"},
        {"destination": "unknown", "q": "clothing"},
        {"destination": "zion", "q": "clothing", "visit_date": "2026-02-30"},
        {"destination": "zion", "q": "clothing", "season": "monsoon"},
        {"destination": "zion", "q": "clothing", "season": "spring", "visit_date": "2027-12-01"},
        {"destination": "zion", "unknown": "x"},
        {"q": "clothing"},
    ],
)
def test_playground_validates_all_inputs(client: TestClient, params: dict[str, str]) -> None:
    assert client.post("/api/knowledge/retrieval", data=params).status_code == 400


@pytest.mark.parametrize("explicit", [False, True])
def test_spring_filter_keeps_year_round_guidance_and_excludes_winter(
    client: TestClient, tmp_path: Path, explicit: bool
) -> None:
    """An explicit season and a season in the question use the same shared filter without inventing a date."""
    service = knowledge_for(
        tmp_path,
        [
            chunk("spring-gear", "Clothing layers", ["zion-narrows"], seasons=["spring"]),
            chunk("year-round", "Clothing footwear", ["zion-narrows"]),
            chunk("winter-gear", "Clothing drysuit", ["zion-narrows"], seasons=["winter"]),
        ],
    )
    cast(FastAPI, client.app).state.park_knowledge = service
    data = {"destination": "zion-narrows", "q": "What clothing should I wear in spring?", "visit_date": ""}
    if explicit:
        data["season"] = "spring"
    page = client.post("/api/knowledge/retrieval", data=data)
    assert page.status_code == 200
    assert 'data-chunk="spring-gear"' in page.text
    assert 'data-chunk="year-round"' in page.text
    assert 'data-chunk="winter-gear"' not in page.text
    assert "Season: Spring" in page.text
    assert ("selected season" if explicit else "(question)") in page.text
    assert re.search(r'name="visit_date"\s+value=""', page.text)
    if explicit:
        assert 'value="spring" selected' in page.text


@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("disabled", "No semantic search was requested"),
        ("unavailable", "verified Qdrant keyword results"),
        ("timeout", "exceeded its time limit"),
    ],
)
def test_fallback_notice_explains_configuration_index_and_temporary_failures(
    client: TestClient, tmp_path: Path, status: str, message: str
) -> None:
    """Disabled inference and an unprepared index must not suggest a retry will activate semantic search."""
    service = knowledge_for(tmp_path, [chunk("item", "Clothing", ["zion"])], semantic_status=status)
    cast(FastAPI, client.app).state.park_knowledge = service
    page = client.post("/api/knowledge/retrieval", data={"destination": "zion", "q": "clothing"})
    assert page.status_code == 200
    assert message in page.text
    assert "try again shortly" not in page.text
    assert "local CPU embeddings" not in page.text


def test_playground_escapes_questions_and_passages_and_retains_form_values(client: TestClient, tmp_path: Path) -> None:
    cast(FastAPI, client.app).state.park_knowledge = knowledge_for(
        tmp_path, [chunk("item", "<script>unsafe()</script> Clothing", ["zion"])]
    )
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
    app.state.park_knowledge = ParkKnowledge(tmp_path / "missing.json")
    assert "Knowledge index unavailable" in client.get("/knowledge/retrieval").text
