"""Offline park-store doubles for app contracts; these do not measure Qdrant retrieval quality."""

import copy
import hashlib
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, cast

from nimbus.model import Tracer
from nimbus.park_ingest import load_prepared, write_index
from nimbus.park_models import Destination, ParkChunk
from nimbus.park_semantic import CatalogResult, SemanticResult, SemanticStatus
from nimbus.park_text import to_embedding_text
from nimbus.parks import ParkKnowledge, to_terms

ROOT = Path(__file__).resolve().parents[1]


class FakeParkStore:
    """Return controlled public records and scores without an HTTP or embedding call."""

    configured = True

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        *,
        keyword_scores: dict[str, float] | None = None,
        semantic_scores: dict[str, float] | None = None,
        semantic_status: str = "ready",
        keyword_status: str = "ready",
        catalog_status: str = "ready",
    ) -> None:
        """Capture immutable fixture records and independently adjustable branch outcomes."""
        self.chunks = copy.deepcopy(chunks)
        self.keyword_scores = keyword_scores
        self.semantic_scores = semantic_scores or {}
        self.semantic_status = semantic_status
        self.keyword_status = keyword_status
        self.catalog_status = catalog_status
        self.calls: list[dict[str, Any]] = []

    async def catalog(
        self,
        index_version: str,
        expected: Mapping[str, Mapping[str, Any]],
        *,
        with_vectors: bool = False,
    ) -> CatalogResult:
        """Return detached source text and optional synthetic vectors for UI contracts only."""
        self.calls.append({"method": "catalog", "with_vectors": with_vectors})
        if self.catalog_status != "ready":
            return CatalogResult(cast(SemanticStatus, self.catalog_status))
        records = []
        for index, chunk in enumerate(self.chunks):
            vector = [0.0] * 384
            vector[index % 384] = 1.0
            records.append({**copy.deepcopy(chunk), "embedding": vector if with_vectors else []})
        return CatalogResult("ready", records)

    async def search(
        self,
        query: str,
        *,
        index_version: str,
        park_id: str,
        destination_id: str,
        season: str | None,
        eligible: Mapping[str, str],
        method: Literal["semantic", "bm25"] = "semantic",
    ) -> SemanticResult:
        """Use supplied ranking scores, or simple term counts solely to exercise application integration."""
        self.calls.append({"method": method, "query": query, "eligible": dict(eligible), "season": season})
        status = self.keyword_status if method == "bm25" else self.semantic_status
        if status != "ready":
            return SemanticResult(cast(SemanticStatus, status))
        supplied = self.keyword_scores if method == "bm25" else self.semantic_scores
        if supplied is not None:
            return SemanticResult(
                "ready", {identity: score for identity, score in supplied.items() if identity in eligible}
            )
        scores = {}
        for chunk in self.chunks:
            if chunk["id"] in eligible:
                words = Counter(to_terms(f"{chunk['section']} {chunk['section']} {chunk['text']}"))
                value = sum(words[word] for word in query.split())
                if value:
                    scores[chunk["id"]] = float(value)
        return SemanticResult("ready", scores)

    async def health(self, index_version: str) -> str:
        """Report the configured catalog outcome without doing any search."""
        return self.catalog_status


def fixture_knowledge(
    path: Path | None = None,
    *,
    tracer: Tracer | None = None,
    mode: Literal["auto", "lexical", "hybrid"] = "hybrid",
) -> ParkKnowledge:
    """Load approved fixture input into a fake provider; production never reads prepared passage text."""
    catalog_path = path or ROOT / "data/parks/catalog.json"
    try:
        corpus = load_prepared(catalog_path.with_name("prepared.json"))
    except (OSError, ValueError):
        return ParkKnowledge(catalog_path, tracer=tracer, mode=mode)
    return ParkKnowledge(catalog_path, store=FakeParkStore(corpus["chunks"]), tracer=tracer, mode=mode)


def knowledge_for(
    tmp_path: Path,
    passages: list[dict[str, Any]],
    *,
    keyword_scores: dict[str, float] | None = None,
    semantic_scores: dict[str, float] | None = None,
    semantic_status: str = "ready",
    keyword_status: str = "ready",
    catalog_status: str = "ready",
    mode: Literal["auto", "lexical", "hybrid"] = "hybrid",
) -> ParkKnowledge:
    """Prepare integrity-valid test records and a controlled remote store for ranker assertions."""
    corpus = load_prepared(ROOT / "data/parks/prepared.json")
    chunks = []
    for item in passages:
        value = dict(item)
        value["content_hash"] = hashlib.sha256(
            to_embedding_text(value["title"], value["section"], value["text"]).encode()
        ).hexdigest()
        chunks.append(ParkChunk.model_validate(value))
    catalog = tmp_path / "catalog.json"
    write_index(
        tmp_path / "prepared.json",
        [Destination.model_validate(item) for item in corpus["destinations"]],
        chunks,
        catalog_path=catalog,
    )
    store = FakeParkStore(
        [chunk.model_dump() for chunk in chunks],
        keyword_scores=keyword_scores,
        semantic_scores=semantic_scores,
        semantic_status=semantic_status,
        keyword_status=keyword_status,
        catalog_status=catalog_status,
    )
    return ParkKnowledge(catalog, store=store, mode=mode)
