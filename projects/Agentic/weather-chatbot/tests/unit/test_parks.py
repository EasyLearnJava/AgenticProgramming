"""Tests for destination identity, bounded retrieval, provenance, and unavailable park knowledge."""

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from nimbus.parks import Destination, ParkChunk, ParkKnowledge


def destination(identity: str, name: str, aliases: list[str], park: str = "zion") -> dict[str, Any]:
    """A checked reference location used only in the test index."""
    return {
        "id": identity,
        "park_id": park,
        "name": name,
        "aliases": aliases,
        "latitude": 37.3,
        "longitude": -112.9,
        "time_zone": "America/Denver",
        "forecast_reference": "Test trailhead reference, not the whole trail",
        "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
    }


def chunk(identity: str, text: str, destinations: list[str], **changes: Any) -> dict[str, Any]:
    """A passage whose scope and provenance can be varied independently."""
    return {
        "id": identity,
        "document_id": "narrows-guide",
        "park_id": "zion",
        "destination_ids": destinations,
        "title": "Narrows guide",
        "section": "Preparation",
        "text": text,
        "source_url": "https://www.nps.gov/zion/planyourvisit/narrowssafety.htm",
        "source_updated_at": "2026-09-17",
        "fetched_at": "2026-11-02T12:00:00Z",
        "content_hash": "a" * 64,
        "seasons": ["all"],
        **changes,
    }


def write_index(path: Path, passages: list[dict[str, Any]], vectors: list[list[float]] | None = None) -> Path:
    """Build a small index independently of the production ingestion implementation."""
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE destinations (id TEXT PRIMARY KEY, json TEXT NOT NULL);"
            "CREATE TABLE chunks (id TEXT PRIMARY KEY, json TEXT NOT NULL, embedding TEXT);"
        )
        db.executemany(
            "INSERT INTO metadata VALUES (?, ?)",
            [
                ("schema_version", "1"),
                ("index_version", "fixture-v1"),
                ("embedding_model", "test-model" if vectors else ""),
                ("embedding_dimensions", "2" if vectors else "0"),
            ],
        )
        for item in [
            destination("zion", "Zion National Park", ["Zion"]),
            destination("zion-narrows", "The Narrows", ["Narrows", "Zion Narrows"]),
            destination("yosemite", "Yosemite National Park", ["Yosemite"], "yosemite"),
        ]:
            db.execute("INSERT INTO destinations VALUES (?, ?)", (item["id"], json.dumps(item)))
        for index, item in enumerate(passages):
            vector = json.dumps(vectors[index]) if vectors else None
            db.execute("INSERT INTO chunks VALUES (?, ?, ?)", (item["id"], json.dumps(item), vector))
    return path


def test_resolution_prefers_named_trail_and_preserves_ambiguity(tmp_path: Path) -> None:
    knowledge = ParkKnowledge(write_index(tmp_path / "parks.sqlite", []))
    assert knowledge.resolve("Zion Narrows tomorrow")["destination"]["id"] == "zion-narrows"
    assert knowledge.resolve("Zion or Yosemite")["status"] == "ambiguous"
    assert knowledge.resolve("Yellowstone")["status"] == "unsupported"
    assert knowledge.resolve("horizon")["status"] == "unsupported"


def test_scope_filters_precede_ranking_and_keep_source_metadata(tmp_path: Path) -> None:
    passages = [
        chunk("right", "Warm waterproof clothing and layers for cold water.", ["zion-narrows"]),
        chunk("wrong", "Warm clothing layers water waterproof clothing.", ["yosemite"], park_id="yosemite"),
        chunk("other-zion-scope", "Warm waterproof clothing and layers.", ["zion"]),
    ]
    knowledge = ParkKnowledge(write_index(tmp_path / "parks.sqlite", passages))
    result = asyncio.run(knowledge.search("zion-narrows", "What clothing should I pack?"))
    assert result["status"] == "found"
    assert [item["id"] for item in result["passages"]] == ["right"]
    assert result["passages"][0]["source_updated_at"] == "2026-09-17"
    assert result["index_version"] == "fixture-v1"
    assert result["retrieval_mode"] == "lexical"


def test_season_is_from_visit_date_and_year_round_guidance_is_retained(tmp_path: Path) -> None:
    passages = [
        chunk("winter", "Winter clothing layers drysuit.", ["zion-narrows"], seasons=["winter"]),
        chunk("summer", "Summer clothing layers.", ["zion-narrows"], seasons=["summer"]),
        chunk("always", "Clothing must stay dry in waterproof bags.", ["zion-narrows"]),
    ]
    knowledge = ParkKnowledge(write_index(tmp_path / "parks.sqlite", passages))
    result = asyncio.run(knowledge.search("zion-narrows", "clothing", date(2027, 1, 10)))
    assert {item["id"] for item in result["passages"]} == {"winter", "always"}


def test_irrelevant_or_unknown_queries_return_no_evidence(tmp_path: Path) -> None:
    knowledge = ParkKnowledge(
        write_index(
            tmp_path / "parks.sqlite",
            [
                chunk("pack", "Warm clothing and waterproof layers.", ["zion-narrows"]),
            ],
        )
    )
    assert asyncio.run(knowledge.search("zion-narrows", "Narrows restaurant reservation menu"))["status"] == "not_found"
    assert asyncio.run(knowledge.search("invented", "clothing"))["status"] == "unsupported"


def test_missing_corrupt_and_incompatible_indexes_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    assert ParkKnowledge(missing).resolve("Zion")["status"] == "unavailable"
    assert not missing.exists()
    missing.write_text("not a database", encoding="utf-8")
    assert asyncio.run(ParkKnowledge(missing).search("zion", "clothing"))["status"] == "unavailable"
    path = write_index(tmp_path / "future.sqlite", [])
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE metadata SET value='999' WHERE key='schema_version'")
    assert ParkKnowledge(path).resolve("Zion")["status"] == "unavailable"


def test_vectors_are_optional_and_embedding_failure_preserves_lexical_evidence(tmp_path: Path) -> None:
    path = write_index(
        tmp_path / "parks.sqlite",
        [
            chunk("pack", "Warm clothing and waterproof layers.", ["zion-narrows"]),
        ],
        [[1.0, 0.0]],
    )

    async def fail(_text: str) -> list[float]:
        """Stand in for a provider outage whose message must not be logged."""
        raise RuntimeError("private-query-marker")

    with capture_logs() as lines:
        result = asyncio.run(ParkKnowledge(path, fail, "test-model").search("zion-narrows", "clothing"))
    assert result["status"] == "found"
    assert result["retrieval_mode"] == "lexical"
    assert "private-query-marker" not in json.dumps(lines)


def test_semantic_matches_work_and_incompatible_models_never_mix(tmp_path: Path) -> None:
    path = write_index(
        tmp_path / "parks.sqlite",
        [
            chunk("pack", "Warm clothing and waterproof layers.", ["zion-narrows"]),
        ],
        [[1.0, 0.0]],
    )
    calls: list[str] = []

    async def embed(text: str) -> list[float]:
        """An exact known semantic vector, independent of any service."""
        calls.append(text)
        return [1.0, 0.0]

    result = asyncio.run(ParkKnowledge(path, embed, "test-model").search("zion-narrows", "attire"))
    assert result["status"] == "found"
    assert result["retrieval_mode"] == "hybrid"
    calls.clear()
    result = asyncio.run(ParkKnowledge(path, embed, "different-model").search("zion-narrows", "attire"))
    assert result["status"] == "not_found"
    assert calls == []


def test_cancellation_is_not_swallowed_as_a_provider_outage(tmp_path: Path) -> None:
    path = write_index(tmp_path / "parks.sqlite", [chunk("pack", "Clothing.", ["zion-narrows"])], [[1.0, 0.0]])

    async def cancel(_text: str) -> list[float]:
        """Simulate the request ending during embedding."""
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ParkKnowledge(path, cancel, "test-model").search("zion-narrows", "clothing"))


def test_passage_count_is_bounded(tmp_path: Path) -> None:
    passages = [
        chunk(f"pack-{index}", f"Clothing and warm layers number {index}.", ["zion-narrows"]) for index in range(12)
    ]
    result = asyncio.run(
        ParkKnowledge(write_index(tmp_path / "parks.sqlite", passages)).search("zion-narrows", "clothing")
    )
    assert 0 < len(result["passages"]) <= 4


def test_models_reject_unapproved_urls_and_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        ParkChunk.model_validate(chunk("bad", "Text", ["zion"], source_url="https://www.nps.gov.attacker.test/a"))
    with pytest.raises(ValidationError):
        Destination.model_validate({**destination("zion", "Zion", ["Zion"]), "latitude": 100})
