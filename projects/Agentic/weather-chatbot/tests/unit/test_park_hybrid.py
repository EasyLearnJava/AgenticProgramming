"""Hybrid ranking preserves scope, seasons, source identity and truthful fallback without external services."""

import asyncio
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from nimbus.config import Settings
from nimbus.park_ranking import reciprocal_ranks, resolve_season
from nimbus.parks import make_park_knowledge
from tests.park_fakes import FakeParkStore, fixture_knowledge, knowledge_for
from tests.unit.test_parks import chunk


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
        ("What do I wear in the fall?", ("fall", "query")),
        # The verb, a waterfall, a month beside a season, and a season joined to a word name no visit season.
        ("How do I avoid a fall hiking South Kaibab in the July heat?", (None, "none")),
        ("What if I fall hiking the Narrows in the heat?", (None, "none")),
        ("Lower Yosemite Fall hike", (None, "none")),
        ("Bridalveil Fall trip", (None, "none")),
        ("What winter gear do I need for my July trip to the Narrows?", (None, "none")),
        ("Are there swimming spots in the spring-fed pools?", (None, "none")),
        # A joined season never cancels a named one, nor does the verb "may"...
        ("Are the spring-fed pools cold in summer?", ("summer", "query")),
        ("What layers may I need in winter?", ("winter", "query")),
        ("Clothing for late fall", ("fall", "query")),
        # ...but a "fall" that may be the verb, a waterfall or a second season leaves every season in.
        ("summer and fall hiking gear", (None, "none")),
        ("clothing for summer and fall", (None, "none")),
        ("How do I avoid a fall on icy trails in winter?", (None, "none")),
        ("Lower Yosemite Fall in winter", (None, "none")),
        ("What should I pack for a trip in May?", (None, "none")),
        ("Narrows hike on May 12", (None, "none")),
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


def test_hosted_semantics_and_bm25_share_exact_scope_and_preserve_public_text(tmp_path: Path) -> None:
    data = [
        chunk("keyword", "Clothing for the river.", ["zion-narrows"]),
        chunk("meaning", "Neoprene insulation.", ["zion-narrows"], seasons=["spring"]),
        chunk("winter", "Clothing for the river.", ["zion-narrows"], seasons=["winter"]),
        chunk("other", "Clothing.", ["yosemite"], park_id="yosemite", document_id="yosemite-guide"),
    ]
    service = knowledge_for(tmp_path, data, semantic_scores={"meaning": 0.95, "keyword": 0.7})
    result = asyncio.run(service.search("zion-narrows", "clothing in spring", explain=True))
    assert result["retrieval_mode"] == "hybrid"
    assert result["semantic_provider"] == "qdrant"
    calls = cast(FakeParkStore, service.store).calls
    assert all(set(call["eligible"]) == {"keyword", "meaning"} for call in calls if "eligible" in call)
    assert all(call["season"] == "spring" for call in calls if "eligible" in call)
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
    service = knowledge_for(
        tmp_path,
        [chunk("right", "Warm clothing", ["zion-narrows"])],
        semantic_status="timeout",
    )
    result = asyncio.run(service.search("zion-narrows", "clothing", explain=True))
    assert result["semantic_status"] == "timeout"
    assert result["retrieval_mode"] == "lexical"
    assert [p["id"] for p in result["passages"]] == ["right"]
    assert result["diagnostics"]["candidates"][0]["semantic_score"] is None


def test_spring_wear_regression_retrieves_seasonal_evidence_and_excludes_winter() -> None:
    service = fixture_knowledge()
    result = asyncio.run(service.search("zion-narrows", "spring clothing what to wear Narrows", explain=True))
    assert result["passages"][0]["section"] == "Spring and Fall"
    assert all("all" in p["seasons"] or "spring" in p["seasons"] for p in result["passages"])
    assert not any(p["section"] == "Winter" for p in result["passages"])
    assert set(result["diagnostics"]["keyword_terms"]) == {"spring", "clothing", "wear", "footwear", "layer"}


def test_hosted_factory_never_attaches_local_inference_on_vercel() -> None:
    settings = Settings(_env_file=None, is_vercel=True, parks_semantic_provider="qdrant", parks_retrieval_mode="auto")
    service = make_park_knowledge(settings)
    assert service is not None
    assert not hasattr(service, "_embed_query")
    assert service.semantic_provider == "qdrant"
    result = asyncio.run(service.search("zion-narrows", "clothing"))
    assert result["retrieval_mode"] == "none"
    assert result["semantic_status"] == "unconfigured"


@pytest.mark.parametrize(
    ("score", "keyword", "included"), [(0.3, False, False), (0.55, False, True), (0.3, True, True)]
)
def test_weak_dense_matches_need_keyword_support(tmp_path: Path, score: float, keyword: bool, included: bool) -> None:
    """Low-confidence dense evidence can rerank keyword matches but cannot invent an unrelated answer."""
    text = "Clothing protects you." if keyword else "Unrelated document."
    service = knowledge_for(
        tmp_path,
        [chunk("candidate", text, ["zion-narrows"])],
        semantic_scores={"candidate": score},
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
    service = fixture_knowledge()
    result = asyncio.run(service.search("zion", question))
    assert result["status"] == "not_found"
    assert service.keyword_terms("backup clothes", service._destinations["zion"]) == {"backup", "clothe", "clothing"}
