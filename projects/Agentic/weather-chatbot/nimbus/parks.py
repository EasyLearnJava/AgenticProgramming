"""Qdrant-backed park guidance with scoped BM25, semantic search and private, explainable rank fusion.

The bundled catalog contains destination and integrity metadata only. All runtime passages and vectors come from
Qdrant; no SQLite, local embedding model or local keyword-search fallback is used.
"""

import asyncio
import math
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import structlog
from pydantic import ValidationError

from nimbus.config import Settings
from nimbus.model import Tracer
from nimbus.park_ingest import load_catalog
from nimbus.park_models import Destination as Destination
from nimbus.park_models import ParkChunk as ParkChunk
from nimbus.park_models import Season as Season
from nimbus.park_ranking import RRF_K, SEMANTIC_WEIGHT, VisitSeason, reciprocal_ranks, resolve_season
from nimbus.park_semantic import PARK_DIMENSIONS, PARK_MODEL, CatalogResult, QdrantParkSearch, SemanticResult
from nimbus.park_text import record_hash
from nimbus.park_tracing import ParkTrace, park_retrieval_trace

log = structlog.get_logger()
MAX_PASSAGES: Final = 4
MAX_CONTEXT_CHARS: Final = 10000
HOSTED_MIN_SEMANTIC_SCORE: Final = 0.3
HOSTED_STANDALONE_SEMANTIC_SCORE: Final = 0.55
# Leave response construction time before the chat tool's six-second deadline.
RETRIEVAL_SECONDS: Final = 5.5
GUIDANCE_SCOPE: Final = (
    "Published preparation guidance, not a live status check. Closures, warnings, river levels and drinking-water "
    "availability have not been verified. A reference-point forecast does not cover every part of a trail."
)
STOP_WORDS: Final = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "given",
        "has",
        "have",
        "getting",
        "find",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "should",
        "the",
        "there",
        "this",
        "to",
        "tomorrow",
        "today",
        "visiting",
        "visit",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "will",
        "with",
        "would",
        "you",
        "your",
        "national",
        "park",
        "trail",
        "hike",
        "hiking",
    ]
)
QUERY_EXPANSIONS: Final = {
    "pack": ("equipment", "clothing", "water", "food"),
    "packing": ("equipment", "clothing", "water", "food"),
    "prepare": ("preparation", "equipment", "clothing"),
    "preparation": ("equipment", "clothing", "water", "weather"),
    "wear": ("clothing", "footwear", "layers"),
    "clothe": ("clothing",),
    "rain": ("rain", "rainfall", "precipitation", "waterproof"),
    "hot": ("heat", "summer", "shade"),
    "cold": ("cold", "warm", "winter"),
}
DESTINATION_CONTEXT_TERMS: Final = STOP_WORDS | frozenset(
    [
        "please",
        "tell",
        "about",
        "weather",
        "preparation",
        "guidance",
        "conditions",
        "now",
        "next",
        "week",
        "month",
        "year",
        "tomorrow",
        "today",
        "spring",
        "summer",
        "fall",
        "winter",
        "autumn",
        "clothing",
        "pack",
        "carry",
        "bring",
        "water",
        "rain",
        "snow",
        "cold",
        "hot",
        "river",
        "equipment",
        "forecast",
        "temperature",
        "going",
        "plan",
        "planning",
        "trip",
        "need",
        "near",
        "at",
        "into",
        "day",
        "days",
        "morning",
        "afternoon",
        "tonight",
    ]
)


def to_normal_name(text: str) -> str:
    """Case and punctuation normalized for whole-name alias matching."""
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def to_terms(text: str) -> list[str]:
    """Lowercase lexical terms, with light plural normalization and conversational stop words removed."""
    return [
        word[:-1] if len(word) > 4 and word.endswith("s") else word
        for word in re.findall(r"[a-z]+", text.casefold())
        if word not in STOP_WORDS
    ]


def to_season(visit_date: date) -> Season:
    """The meteorological season for the three supported northern-hemisphere parks."""
    return ("winter", "spring", "summer", "fall")[(visit_date.month % 12) // 3]


class ParkStore(Protocol):
    """Remote public corpus and two ranked search methods; tests provide recorded implementations."""

    @property
    def configured(self) -> bool: ...

    async def catalog(
        self,
        index_version: str,
        expected: Mapping[str, Mapping[str, Any]],
        *,
        with_vectors: bool = False,
    ) -> CatalogResult: ...

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
    ) -> SemanticResult: ...

    async def health(self, index_version: str) -> str: ...


class ParkKnowledge:
    """Destination metadata stays local; public source text and all scoring live in Qdrant."""

    def __init__(
        self,
        index_path: Path,
        *,
        store: ParkStore | None = None,
        tracer: Tracer | None = None,
        mode: Literal["auto", "lexical", "hybrid"] = "hybrid",
    ) -> None:
        """Validate only a bounded metadata catalog; startup performs no network or model work."""
        self.index_version = "unavailable"
        self.available = False
        self._destinations: dict[str, Destination] = {}
        self._expected: dict[str, dict[str, Any]] = {}
        self.store = store
        self.tracer = tracer
        self.mode = mode
        self.embedding_model = PARK_MODEL
        self.embedding_dimensions = PARK_DIMENSIONS
        try:
            catalog = load_catalog(index_path)
            self.index_version = str(catalog["index_version"])
            self._destinations = {item["id"]: Destination.model_validate(item) for item in catalog["destinations"]}
            self._expected = {item["id"]: dict(item) for item in catalog["chunks"]}
            self.available = True
        except (OSError, ValueError, TypeError, KeyError, ValidationError) as error:
            log.warning("park.index.unavailable", errorType=type(error).__name__)

    @property
    def semantic_provider(self) -> str:
        """The only park search backend, independent of the weather answer cache collection."""
        return "qdrant"

    @property
    def semantic_model(self) -> str:
        """The hosted dense embedding model, used once per published chunk and for semantic queries."""
        return PARK_MODEL

    @property
    def semantic_status(self) -> str:
        """Configuration readiness only; actual publication and availability are checked during requests."""
        if self.mode == "lexical":
            return "disabled"
        return "ready" if self.store and self.store.configured else "unconfigured"

    async def health(self) -> str:
        """Check the published Qdrant index without inference or retrieving private requests."""
        if not self.available:
            return "index_mismatch"
        if self.store is None or not self.store.configured:
            return "unconfigured"
        return await self.store.health(self.index_version)

    async def _catalog(self, *, with_vectors: bool = False) -> CatalogResult:
        """Reject missing, substituted or altered provider records before using any public source text."""
        if not self.available:
            return CatalogResult("index_mismatch")
        if self.store is None or not self.store.configured:
            return CatalogResult("unconfigured")
        try:
            result = await self.store.catalog(self.index_version, self._expected, with_vectors=with_vectors)
            if result.status != "ready":
                return result
            seen: set[str] = set()
            for item in result.chunks:
                chunk = ParkChunk.model_validate({key: value for key, value in item.items() if key != "embedding"})
                expected = self._expected.get(chunk.id)
                if expected is None or chunk.id in seen or record_hash(chunk) != expected["record_hash"]:
                    return CatalogResult("invalid_response")
                seen.add(chunk.id)
            if seen != self._expected.keys():
                return CatalogResult("index_mismatch")
            return result
        except (ValueError, TypeError, KeyError, ValidationError):
            return CatalogResult("invalid_response")
        except Exception:
            return CatalogResult("unavailable")

    async def inspection(self, *, with_vectors: bool = True) -> dict[str, Any]:
        """Read actual hosted texts and vectors; unavailable Qdrant is never disguised as an empty index."""
        base: dict[str, Any] = {
            "available": False,
            "provider": "qdrant",
            "status": "unavailable",
            "index_version": self.index_version,
            "embedding_model": PARK_MODEL,
            "dimensions": PARK_DIMENSIONS,
            "destinations": [item.model_dump() for item in self._destinations.values()],
            "chunks": [],
        }
        result = await self._catalog(with_vectors=with_vectors)
        return {**base, "available": result.status == "ready", "status": result.status, "chunks": result.chunks}

    def resolve(self, query: str) -> dict[str, Any]:
        """Resolve supported names without silently substituting a nearby city or another park."""
        if not self.available:
            return {"status": "unavailable", "candidates": [], "scope_note": GUIDANCE_SCOPE}
        normalized = f" {to_normal_name(query[:500])} "
        matches = [
            item
            for item in self._destinations.values()
            if any(f" {to_normal_name(alias)} " in normalized for alias in [item.name, *item.aliases])
        ]
        # Unknown place qualifiers cannot be silently stripped from a longer place name.
        remainder = normalized
        aliases = sorted(
            {to_normal_name(alias) for item in matches for alias in [item.name, *item.aliases]},
            key=len,
            reverse=True,
        )
        for alias in aliases:
            remainder = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", " ", remainder)
        if any(word not in DESTINATION_CONTEXT_TERMS and not word.isdecimal() for word in remainder.split()):
            matches = []
        # ① A named trail is more specific than its own park; other named parks remain ambiguous.
        trail_parents = {item.park_id for item in matches if item.id != item.park_id}
        matches = [item for item in matches if item.id not in trail_parents]
        status = "resolved" if len(matches) == 1 else "ambiguous" if matches else "unsupported"
        return {
            "status": status,
            "destination": matches[0].model_dump() if len(matches) == 1 else None,
            "candidates": [item.model_dump() for item in matches],
            "supported_destinations": [{"id": item.id, "name": item.name} for item in self._destinations.values()],
            "index_version": self.index_version,
            "scope_note": GUIDANCE_SCOPE,
        }

    def keyword_terms(self, query: str, destination: Destination) -> set[str]:
        """The actual expanded ranking terms, excluding destination names already enforced by scope."""
        terms = set(to_terms(query))
        for word in list(terms):
            terms.update(to_terms(" ".join(QUERY_EXPANSIONS.get(word, ()))))
        identity_terms = set(to_terms(" ".join([destination.name, *destination.aliases])))
        terms.difference_update(identity_terms)
        return terms

    async def _scores(
        self,
        query: str,
        destination: Destination,
        chunks: list[ParkChunk],
        season: VisitSeason | None,
        method: Literal["semantic", "bm25"],
    ) -> SemanticResult:
        """Validate each hosted ranker independently and keep cancellation visible to its caller."""
        if not chunks or not query.strip():
            return SemanticResult("ready")
        if self.store is None or not self.store.configured:
            return SemanticResult("unconfigured")
        try:
            result = await self.store.search(
                query,
                index_version=self.index_version,
                park_id=destination.park_id,
                destination_id=destination.id,
                season=season,
                eligible={chunk.id: chunk.content_hash for chunk in chunks},
                method=method,
            )
            if result.status != "ready":
                return result
            allowed = {chunk.id for chunk in chunks}
            if any(
                identity not in allowed
                or isinstance(score, bool)
                or not isinstance(score, (float, int))
                or not math.isfinite(score)
                or (not -1 <= score <= 1 if method == "semantic" else score < 0)
                for identity, score in result.scores.items()
            ):
                return SemanticResult("invalid_response")
            return result
        except Exception:
            return SemanticResult("unavailable")

    async def search(
        self,
        destination_id: str,
        query: str,
        visit_date: date | None = None,
        *,
        explain: bool = False,
        season: VisitSeason | None = None,
    ) -> dict[str, Any]:
        """Use one scoped and traced Qdrant retrieval path for chat, planner and Playground."""
        selected_season, season_source = resolve_season(query, visit_date, season)
        with park_retrieval_trace(self.tracer) as trace:
            result = await self._search(destination_id, query, selected_season, season_source, explain, trace)
            if trace.trace_id is not None:
                result["trace_id"] = str(trace.trace_id)
            return result

    async def _search(
        self,
        destination_id: str,
        query: str,
        season: VisitSeason | None,
        season_source: str,
        explain: bool,
        trace: ParkTrace,
    ) -> dict[str, Any]:
        """Read verified remote text, rank it remotely twice, then apply shared context and citation limits."""
        deadline = asyncio.get_running_loop().time() + RETRIEVAL_SECONDS
        base: dict[str, Any] = {
            "passages": [],
            "index_version": self.index_version,
            "retrieval_mode": "none",
            "keyword_status": "not_needed",
            "keyword_provider": "qdrant",
            "semantic_status": self.semantic_status,
            "semantic_provider": "qdrant",
            "semantic_model": PARK_MODEL,
            "scope_note": GUIDANCE_SCOPE,
        }
        if not self.available:
            trace.outcome("unavailable", provider="qdrant")
            return {**base, "status": "unavailable"}
        destination = self._destinations.get(destination_id)
        if destination is None:
            trace.outcome("unsupported", provider="qdrant")
            return {**base, "status": "unsupported"}
        # ① Publication and complete approved source records are checked before either scoring call.
        with trace.step("catalog") as step:
            catalog = await self._catalog()
            step.outcome(catalog.status, provider="qdrant", candidate_count=len(catalog.chunks))
        if catalog.status != "ready":
            trace.outcome(catalog.status, provider="qdrant")
            return {
                **base,
                "status": "unavailable",
                "keyword_status": catalog.status,
                "semantic_status": catalog.status,
            }
        chunks = [
            ParkChunk.model_validate({key: value for key, value in item.items() if key != "embedding"})
            for item in catalog.chunks
            if destination_id in item["destination_ids"]
            and item["park_id"] == destination.park_id
            and (season is None or "all" in item["seasons"] or season in item["seasons"])
        ]
        bounded_query = query[:2000]
        # ② Keyword ranking and semantic ranking both run in Qdrant with exactly the same hard scope.
        with trace.step("bm25") as step:
            keyword = await self._scores(
                " ".join(sorted(self.keyword_terms(bounded_query, destination))), destination, chunks, season, "bm25"
            )
            step.outcome(
                keyword.status,
                provider="qdrant",
                mode="lexical",
                candidate_count=len(keyword.scores),
                season_source=season_source,
            )
        base["keyword_status"] = keyword.status
        if keyword.status != "ready":
            trace.outcome(keyword.status, provider="qdrant")
            return {**base, "status": "unavailable"}
        lexical = [keyword.scores.get(chunk.id, 0.0) for chunk in chunks]
        with trace.step("semantic") as step:
            dense = SemanticResult("disabled")
            if self.mode != "lexical":
                # A slow optional ranker must not discard BM25 evidence already read and verified.
                try:
                    async with asyncio.timeout_at(deadline):
                        dense = await self._scores(bounded_query, destination, chunks, season, "semantic")
                except TimeoutError:
                    dense = SemanticResult("timeout")
            semantic, semantic_status = dense.scores, dense.status
            mode = "hybrid" if semantic_status == "ready" else "lexical"
            step.outcome(semantic_status, provider="qdrant", mode=mode, candidate_count=len(semantic))
        base.update(retrieval_mode=mode, semantic_status=semantic_status)
        diagnostics: dict[str, dict[str, Any]] = {}
        with trace.step("fusion") as step:
            keyword_ranks = reciprocal_ranks(
                {chunk.id: score for chunk, score in zip(chunks, lexical, strict=True)}, minimum=0, positive=True
            )
            threshold = HOSTED_MIN_SEMANTIC_SCORE
            standalone_threshold = HOSTED_STANDALONE_SEMANTIC_SCORE
            semantic_ranks = reciprocal_ranks(semantic, minimum=threshold)
            ranked: list[tuple[float, ParkChunk]] = []
            for chunk, score in zip(chunks, lexical, strict=True):
                keyword_rank, semantic_rank = keyword_ranks.get(chunk.id), semantic_ranks.get(chunk.id)
                keyword_part = 1 / (RRF_K + keyword_rank) if keyword_rank is not None else 0.0
                semantic_eligible = keyword_rank is not None or semantic.get(chunk.id, -1) >= standalone_threshold
                semantic_part = (
                    SEMANTIC_WEIGHT / (RRF_K + semantic_rank)
                    if semantic_rank is not None and semantic_eligible
                    else 0.0
                )
                rank = keyword_part + semantic_part
                if explain:
                    diagnostics[chunk.id] = {
                        "chunk": chunk.model_dump(),
                        "keyword_score": score,
                        "keyword_rank": keyword_rank,
                        "keyword_component": keyword_part,
                        "semantic_score": semantic.get(chunk.id),
                        "semantic_rank": semantic_rank,
                        "semantic_component": semantic_part,
                        "final_score": rank,
                        "rank": None,
                        "selection": (
                            "needs_keyword_support"
                            if semantic_rank is not None and not semantic_eligible
                            else "below_threshold"
                        ),
                    }
                if rank > 0:
                    ranked.append((rank, chunk))
            ranked.sort(key=lambda item: (-item[0], item[1].id))
            if explain:
                for position, (_, chunk) in enumerate(ranked, start=1):
                    diagnostics[chunk.id].update(rank=position, selection="result_limit")
            # ③ Only Qdrant text verified against the approved catalog can become context or a citation.
            passages: list[dict[str, Any]] = []
            used = 0
            for _, chunk in ranked:
                if len(passages) >= MAX_PASSAGES:
                    break
                if used + len(chunk.text) > MAX_CONTEXT_CHARS:
                    if explain:
                        diagnostics[chunk.id]["selection"] = "context_limit"
                    continue
                passages.append(chunk.model_dump())
                used += len(chunk.text)
                if explain:
                    diagnostics[chunk.id]["selection"] = "retrieved"
            step.outcome("completed", mode=mode, candidate_count=len(ranked), selected_count=len(passages))
        if explain:
            base["diagnostics"] = {
                "candidate_count": len(chunks),
                "season": season,
                "season_source": season_source,
                "keyword_terms": sorted(self.keyword_terms(bounded_query, destination)),
                "fusion": "rrf",
                "rrf_k": RRF_K,
                "keyword_weight": 1.0,
                "semantic_weight": SEMANTIC_WEIGHT,
                "context_chars": used,
                "max_passages": MAX_PASSAGES,
                "max_context_chars": MAX_CONTEXT_CHARS,
                "semantic_threshold": threshold,
                "standalone_semantic_threshold": standalone_threshold,
                "candidates": sorted(
                    diagnostics.values(),
                    key=lambda item: (item["rank"] is None, -item["final_score"], item["chunk"]["id"]),
                ),
            }
        status = "found" if passages else "not_found"
        trace.outcome(
            status,
            provider=self.semantic_provider,
            mode=mode,
            candidate_count=len(chunks),
            selected_count=len(passages),
            season_source=season_source,
        )
        return {**base, "status": status, "destination": destination.model_dump(), "passages": passages}


def make_park_knowledge(settings: Settings, *, tracer: Tracer | None = None) -> ParkKnowledge | None:
    """Configure Qdrant without network calls; the bundled file contains only approved integrity metadata."""
    if not settings.parks_enabled:
        return None
    knowledge = ParkKnowledge(settings.parks_index_path, tracer=tracer, mode=settings.parks_retrieval_mode)
    knowledge.store = QdrantParkSearch(settings, chunk_count=len(knowledge._expected))
    return knowledge
