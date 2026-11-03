"""
nimbus/parks.py: a read-only, versioned park knowledge index. Destination identity constrains retrieval before
ranking; source passages keep their provenance. CPU MiniLM supplies semantic vectors, with lexical retrieval
available when cached weights are missing. This index contains preparation guidance, never live park status.
"""

import asyncio
import json
import math
import re
import sqlite3
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import structlog
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator

from nimbus.config import Settings
from nimbus.park_embeddings import EmbeddingBusyError

log = structlog.get_logger()
INDEX_SCHEMA: Final = "1"
MAX_INDEX_BYTES: Final = 20 * 1024 * 1024
MAX_PASSAGES: Final = 4
MAX_CONTEXT_CHARS: Final = 10000
EMBEDDING_TIMEOUT_SECONDS: Final = 3.0
MIN_SEMANTIC_SCORE: Final = 0.65
GUIDANCE_SCOPE: Final = (
    "Published preparation guidance, not a live status check. Closures, warnings, river levels and drinking-water "
    "availability have not been verified. A reference-point forecast does not cover every part of a trail."
)
type EmbedQuery = Callable[[str], Awaitable[list[float]]]
type Identity = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,100}$")]
type Season = Literal["all", "winter", "spring", "summer", "fall"]
STOP_WORDS: Final = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "can",
        "do",
        "does",
        "for",
        "from",
        "given",
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


def checked_source_url(value: str) -> str:
    """An HTTPS National Park Service source URL, without credentials, a port, query, or fragment."""
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname not in {"www.nps.gov", "nps.gov", "home.nps.gov"}
        or parts.username
        or parts.password
        or parts.port
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Park sources must be public HTTPS NPS pages")
    return value


class Destination(BaseModel):
    """One supported destination and an explicitly labeled forecast reference point."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identity
    park_id: Identity
    name: str = Field(min_length=1, max_length=150)
    aliases: list[str] = Field(min_length=1, max_length=20)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    time_zone: str
    forecast_reference: str = Field(min_length=1, max_length=500)
    source_url: str

    _source = field_validator("source_url")(checked_source_url)

    @field_validator("time_zone")
    @classmethod
    def known_time_zone(cls, value: str) -> str:
        """A timezone that can be used for destination-local dates."""
        try:
            ZoneInfo(value)
        except (KeyError, ValueError) as error:
            raise ValueError("Unknown destination timezone") from error
        return value


class ParkChunk(BaseModel):
    """An attributed passage with explicit destination and seasonal applicability."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identity
    document_id: Identity
    park_id: Identity
    destination_ids: list[Identity] = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=300)
    section: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=8000)
    source_url: str
    source_updated_at: str | None = None
    fetched_at: str
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    seasons: list[Season] = Field(default_factory=lambda: list[Season](["all"]), min_length=1, max_length=4)

    _source = field_validator("source_url")(checked_source_url)

    @field_validator("source_updated_at")
    @classmethod
    def source_date(cls, value: str | None) -> str | None:
        """An actual source date when the publisher exposes one; never the fetch date substituted for it."""
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator("fetched_at")
    @classmethod
    def fetched_timestamp(cls, value: str) -> str:
        """An ingestion timestamp with its timezone."""
        if datetime.fromisoformat(value).tzinfo is None:
            raise ValueError("Ingestion time needs a timezone")
        return value


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


def to_unit_vector(values: list[float], dimensions: int) -> list[float]:
    """A finite nonzero vector with the index's dimensionality, normalized for cosine similarity."""
    if len(values) != dimensions or not all(math.isfinite(value) for value in values):
        raise ValueError("Embedding dimensions or values do not match the index")
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0 or not math.isfinite(norm):
        raise ValueError("Embedding has no finite direction")
    return [value / norm for value in values]


class ParkKnowledge:
    """A validated immutable corpus, shared across requests; request text and query vectors are never retained."""

    def __init__(
        self,
        index_path: Path,
        embed_query: EmbedQuery | None = None,
        embedding_model: str | None = None,
        *,
        semantic_status: str = "unavailable",
    ) -> None:
        """Load the deployment's index once, leaving the service unavailable when the artifact is invalid."""
        self.index_version = "unavailable"
        self.embedding_model = ""
        self.embedding_dimensions = 0
        self.available = False
        self._destinations: dict[str, Destination] = {}
        self._chunks: list[ParkChunk] = []
        self._vectors: dict[str, list[float]] = {}
        self._embed_query = embed_query
        self._query_model = embedding_model
        self.semantic_status = semantic_status
        try:
            self._load(index_path)
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, ValidationError) as error:
            self._destinations.clear()
            self._chunks.clear()
            self._vectors.clear()
            log.warning("park.index.unavailable", errorType=type(error).__name__)

    def _load(self, path: Path) -> None:
        """Read bounded, typed records through a read-only SQLite connection; never create a missing index."""
        # ① Reject missing or oversized artifacts before opening the read-only database.
        if not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
            raise ValueError("Missing or oversized park index")
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)) as db:
            metadata = dict(db.execute("SELECT key, value FROM metadata LIMIT 30"))
            if metadata.get("schema_version") != INDEX_SCHEMA:
                raise ValueError("Unsupported park index schema")
            self.index_version = metadata["index_version"]
            self.embedding_model = metadata.get("embedding_model", "")
            self.embedding_dimensions = int(metadata.get("embedding_dimensions", "0"))
            if not 0 <= self.embedding_dimensions <= 4096:
                raise ValueError("Invalid embedding dimensions")
            # ② Every passage's scope must refer to an existing destination in the same park.
            for identity, payload in db.execute("SELECT id, json FROM destinations LIMIT 101"):
                item = Destination.model_validate_json(payload)
                if item.id != identity:
                    raise ValueError("Destination identity mismatch")
                self._destinations[item.id] = item
            if not self._destinations or len(self._destinations) > 100:
                raise ValueError("Invalid destination count")
            for identity, payload, embedding in db.execute("SELECT id, json, embedding FROM chunks LIMIT 1001"):
                chunk = ParkChunk.model_validate_json(payload)
                if chunk.id != identity or any(
                    name not in self._destinations or self._destinations[name].park_id != chunk.park_id
                    for name in chunk.destination_ids
                ):
                    raise ValueError("Invalid passage scope")
                self._chunks.append(chunk)
                if embedding is not None:
                    values = json.loads(embedding)
                    if not isinstance(values, list) or not all(isinstance(value, (int, float)) for value in values):
                        raise ValueError("Invalid embedding record")
                    self._vectors[identity] = to_unit_vector(values, self.embedding_dimensions)
            if len(self._chunks) > 1000:
                raise ValueError("Too many passages")
        self.available = True

    def inspection(self) -> dict[str, Any]:
        """A detached snapshot of public source passages and normalized vectors, without loading an encoder."""
        return {
            "available": self.available,
            "index_version": self.index_version,
            "embedding_model": self.embedding_model,
            "dimensions": self.embedding_dimensions,
            "destinations": [item.model_dump() for item in self._destinations.values()],
            "chunks": [
                {**chunk.model_dump(), "embedding": list(self._vectors.get(chunk.id, []))} for chunk in self._chunks
            ],
        }

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

    def _lexical_scores(self, chunks: list[ParkChunk], query: str, destination: Destination) -> list[float]:
        """Rank question concepts with length-normalized term frequency and corpus inverse document frequency."""
        terms = set(to_terms(query))
        for word in list(terms):
            terms.update(to_terms(" ".join(QUERY_EXPANSIONS.get(word, ()))))
        identity_terms = set(to_terms(" ".join([destination.name, *destination.aliases])))
        terms.difference_update(identity_terms)
        documents = [Counter(to_terms(f"{chunk.section} {chunk.section} {chunk.text}")) for chunk in chunks]
        average_length = sum(sum(doc.values()) for doc in documents) / max(len(documents), 1)
        scores = []
        for document in documents:
            score = 0.0
            for term in terms:
                count = document[term]
                if not count:
                    continue
                containing = sum(term in candidate for candidate in documents)
                rarity = math.log(1 + (len(documents) - containing + 0.5) / (containing + 0.5))
                length = sum(document.values()) / max(average_length, 1)
                score += rarity * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length))
            scores.append(score)
        return scores

    async def _query_vector(self, query: str) -> tuple[list[float] | None, str]:
        """Embed once within a short deadline, falling back on service failure while propagating cancellation."""
        if not self._vectors or self._embed_query is None or self._query_model != self.embedding_model:
            return None, self.semantic_status
        try:
            async with asyncio.timeout(EMBEDDING_TIMEOUT_SECONDS):
                return to_unit_vector(await self._embed_query(query), self.embedding_dimensions), "ready"
        except EmbeddingBusyError:
            return None, "busy"
        except TimeoutError:
            log.warning("park.embedding.unavailable", errorType="TimeoutError")
            return None, "timeout"
        except Exception as error:
            log.warning("park.embedding.unavailable", errorType=type(error).__name__)
            return None, "failed"

    async def search(
        self, destination_id: str, query: str, visit_date: date | None = None, *, explain: bool = False
    ) -> dict[str, Any]:
        """Retrieve scoped passages, optionally explaining the same scores and selections for the playground."""
        base: dict[str, Any] = {
            "passages": [],
            "index_version": self.index_version,
            "retrieval_mode": "lexical",
            "semantic_status": self.semantic_status,
            "scope_note": GUIDANCE_SCOPE,
        }
        if not self.available:
            return {**base, "status": "unavailable"}
        destination = self._destinations.get(destination_id)
        if destination is None:
            return {**base, "status": "unsupported"}
        # ① Identity and season constrain the candidate set before either ranking method sees it.
        season = to_season(visit_date) if visit_date else None
        chunks = [
            chunk
            for chunk in self._chunks
            if destination_id in chunk.destination_ids
            and chunk.park_id == destination.park_id
            and (season is None or "all" in chunk.seasons or season in chunk.seasons)
        ]
        bounded_query = query[:2000]
        lexical = self._lexical_scores(chunks, bounded_query, destination)
        vector, semantic_status = await self._query_vector(bounded_query) if chunks else (None, "not_needed")
        base["semantic_status"] = semantic_status
        if vector is not None:
            base["retrieval_mode"] = "hybrid"
        diagnostics: dict[str, dict[str, Any]] = {}
        # ② Semantic similarity augments lexical relevance only when vectors use the same model and dimensions.
        ranked: list[tuple[float, ParkChunk]] = []
        for chunk, score in zip(chunks, lexical, strict=True):
            stored = self._vectors.get(chunk.id)
            similarity = sum(a * b for a, b in zip(vector, stored, strict=True)) if vector and stored else 0.0
            rank = score / (1 + score) + (similarity if vector is not None else 0)
            if explain:
                diagnostics[chunk.id] = {
                    "chunk": chunk.model_dump(),
                    "keyword_score": score,
                    "keyword_component": score / (1 + score),
                    "semantic_score": similarity if vector is not None and stored is not None else None,
                    "final_score": rank,
                    "rank": None,
                    "selection": "below_threshold",
                }
            if score <= 0 and similarity < MIN_SEMANTIC_SCORE:
                continue
            ranked.append((rank, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        if explain:
            for position, (_, chunk) in enumerate(ranked, start=1):
                diagnostics[chunk.id].update(rank=position, selection="result_limit")
        # ③ Explain why a ranked chunk was included or skipped without changing the chat's selection or payload.
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
        if explain:
            base["diagnostics"] = {
                "candidate_count": len(chunks),
                "season": season,
                "context_chars": used,
                "max_passages": MAX_PASSAGES,
                "max_context_chars": MAX_CONTEXT_CHARS,
                "semantic_threshold": MIN_SEMANTIC_SCORE,
                "candidates": sorted(
                    diagnostics.values(),
                    key=lambda item: (item["rank"] is None, -item["final_score"], item["chunk"]["id"]),
                ),
            }
        return {
            **base,
            "status": "found" if passages else "not_found",
            "destination": destination.model_dump(),
            "passages": passages,
        }


def make_park_knowledge(settings: Settings) -> ParkKnowledge | None:
    """Build the configured service without network work; CPU inference loads pinned, previously cached weights."""
    if not settings.parks_enabled:
        return None
    use_semantic = settings.parks_retrieval_mode == "hybrid" or (
        settings.parks_retrieval_mode == "auto" and not settings.is_vercel
    )
    knowledge = ParkKnowledge(
        settings.parks_index_path, semantic_status="disabled" if not use_semantic else "unavailable"
    )
    if use_semantic and knowledge.available and knowledge.embedding_dimensions:
        from nimbus.park_embeddings import cached_encoder

        encoder = cached_encoder(settings.parks_model_cache, settings.parks_model_revision)
        if knowledge.embedding_model == encoder.identity:
            knowledge.semantic_status = encoder.availability()
            if knowledge.semantic_status == "ready":
                knowledge._embed_query = encoder.embed_query
                knowledge._query_model = encoder.identity
        else:
            knowledge.semantic_status = "incompatible_model"
    return knowledge
