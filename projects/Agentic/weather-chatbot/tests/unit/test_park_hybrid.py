"""Hybrid ranking preserves scope, seasons, source identity and truthful fallback without external services."""

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from nimbus.config import Settings
from nimbus.park_ranking import reciprocal_ranks, resolve_season
from nimbus.park_semantic import SemanticResult
from nimbus.parks import ParkKnowledge, make_park_knowledge
from tests.unit.test_parks import chunk, write_index


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What should I wear to hike The Narrows in spring?", ("spring", "query")),
        ("spring clothing what to wear Narrows", ("spring", "query")),
        ("clothing for autumn", ("fall", "query")),
        ("clothing in spring and winter", (None, "none")),
        ("Top of Nevada Fall slippery steps", (None, "none")),
        ("hike to Big Spring", (None, "none")),
        ("fall protection equipment", (None, "none")),
        ("What gear do I need for fall protection on Angels Landing?", (None, "none")),
        ("fall-protection equipment in spring", ("spring", "query")),
    ],
)
def test_season_words_only_filter_when_they_describe_one_visit_season(
    question: str, expected: tuple[str | None, str]
) -> None:
    assert resolve_season(question, None, None) == expected


def test_explicit_seasons_and_dates_agree_without_inventing_a_date() -> None:
    assert resolve_season("clothing", None, "spring") == ("spring", "explicit")
    assert resolve_season("clothing in winter", date(2027, 4, 1), None) == ("spring", "date")
    with pytest.raises(ValueError, match="disagree"):
        resolve_season("clothing", date(2027, 1, 1), "spring")


def test_rank_fusion_rewards_agreement_without_raw_score_scale_bias() -> None:
    first = reciprocal_ranks({"a": 100, "b": 20, "c": 0}, minimum=0, positive=True)
    second = reciprocal_ranks({"b": 0.95, "c": 0.9, "a": 0.1}, minimum=0.65)
    assert first == {"a": 1, "b": 2}
    assert second == {"b": 1, "c": 2}
    assert 1 / (60 + first["b"]) + 1 / (60 + second["b"]) > 1 / (60 + first["a"])
    assert reciprocal_ranks({"b": 2, "a": 2}, minimum=0) == {"a": 1, "b": 2}


class DenseProvider:
    """A remote provider stand-in; it records the exact candidate restrictions supplied by core retrieval."""

    provider = "qdrant"
    model = "synthetic-model"
    configured = True

    def __init__(self, scores: dict[str, float], status: str = "ready") -> None:
        self.scores = scores
        self.status = status
        self.calls: list[dict[str, Any]] = []

    async def search(self, query: str, **scope: Any) -> SemanticResult:
        self.calls.append(scope)
        return SemanticResult(self.status, self.scores)  # type: ignore[arg-type]


def test_hosted_semantics_and_bm25_share_exact_scope_and_preserve_public_text(tmp_path: Path) -> None:
    data = [
        chunk("keyword", "Clothing for the river.", ["zion-narrows"]),
        chunk("meaning", "Neoprene insulation.", ["zion-narrows"], seasons=["spring"]),
        chunk("winter", "Clothing for the river.", ["zion-narrows"], seasons=["winter"]),
        chunk("other", "Clothing.", ["yosemite"], park_id="yosemite"),
    ]
    dense = DenseProvider({"meaning": 0.95, "keyword": 0.7})
    service = ParkKnowledge(write_index(tmp_path / "index.sqlite", data), semantic_search=dense)
    result = asyncio.run(service.search("zion-narrows", "clothing in spring", explain=True))
    assert result["retrieval_mode"] == "hybrid"
    assert result["semantic_provider"] == "qdrant"
    assert set(dense.calls[0]["eligible"]) == {"keyword", "meaning"}
    assert dense.calls[0]["season"] == "spring"
    assert dense.calls[0]["index_version"] == "fixture-v1"
    assert {p["id"] for p in result["passages"]} == {"keyword", "meaning"}
    assert result["diagnostics"]["fusion"] == "rrf"
    assert result["diagnostics"]["season_source"] == "query"
    rows = {item["chunk"]["id"]: item for item in result["diagnostics"]["candidates"]}
    assert rows["meaning"]["semantic_component"] == pytest.approx(0.1 / 61)
    assert rows["keyword"]["final_score"] == pytest.approx(1 / 61 + 0.1 / 62)
    assert result["diagnostics"]["semantic_threshold"] == 0.3
    assert result["diagnostics"]["standalone_semantic_threshold"] == 0.55
    assert result["passages"][1]["text"] in {"Clothing for the river.", "Neoprene insulation."}


def test_provider_outage_leaves_keyword_answer_and_reports_actual_mode(tmp_path: Path) -> None:
    dense = DenseProvider({}, "timeout")
    service = ParkKnowledge(
        write_index(tmp_path / "index.sqlite", [chunk("right", "Warm clothing", ["zion-narrows"])]),
        semantic_search=dense,
    )
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    assert result["semantic_status"] == "timeout"
    assert result["retrieval_mode"] == "lexical"
    assert [p["id"] for p in result["passages"]] == ["right"]
    assert result["diagnostics"]["candidates"][0]["semantic_score"] is None


def test_spring_wear_regression_retrieves_seasonal_evidence_and_excludes_winter() -> None:
    service = ParkKnowledge(Path("data/parks/index.sqlite"))
    result = asyncio.run(service.search("zion-narrows", "spring clothing what to wear Narrows", explain=True))
    assert result["passages"][0]["section"] == "Spring and Fall"
    assert all("all" in p["seasons"] or "spring" in p["seasons"] for p in result["passages"])
    assert not any(p["section"] == "Winter" for p in result["passages"])
    assert set(result["diagnostics"]["keyword_terms"]) == {"spring", "clothing", "wear", "footwear", "layer"}


def test_hosted_factory_never_attaches_local_inference_on_vercel() -> None:
    settings = Settings(_env_file=None, is_vercel=True, parks_semantic_provider="qdrant", parks_retrieval_mode="auto")
    service = make_park_knowledge(settings)
    assert service is not None
    assert service._embed_query is None
    assert service.semantic_provider == "qdrant"
    result = asyncio.run(service.search("zion-narrows", "clothing"))
    assert result["retrieval_mode"] == "lexical"
    assert result["semantic_status"] == "unconfigured"


@pytest.mark.parametrize(
    ("score", "keyword", "included"), [(0.3, False, False), (0.55, False, True), (0.3, True, True)]
)
def test_weak_dense_matches_need_keyword_support(tmp_path: Path, score: float, keyword: bool, included: bool) -> None:
    """Low-confidence dense evidence can rerank keyword matches but cannot invent an unrelated answer."""
    text = "Clothing protects you." if keyword else "Unrelated document."
    service = ParkKnowledge(
        write_index(tmp_path / "gated.sqlite", [chunk("candidate", text, ["zion-narrows"])]),
        semantic_search=DenseProvider({"candidate": score}),
    )
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    row = result["diagnostics"]["candidates"][0]
    assert bool(result["passages"]) is included
    assert (row["semantic_component"] > 0) is included
    assert row["semantic_score"] == score
    assert row["semantic_rank"] == 1
    if not included:
        assert row["selection"] == "needs_keyword_support"


@pytest.mark.parametrize(
    "question",
    ["Where can I find free Wi-Fi?", "Does the trail have public Wi-Fi?", "Is there a pizza restaurant by the trail?"],
)
def test_generic_search_words_do_not_create_wifi_evidence(question: str) -> None:
    """A query's generic search verb is not evidence about its unsupported subject."""
    service = ParkKnowledge(Path("data/parks/index.sqlite"))
    result = asyncio.run(service.search("zion", question))
    assert result["status"] == "not_found"
    assert service.keyword_terms("backup clothes", service._destinations["zion"]) == {"backup", "clothe", "clothing"}
