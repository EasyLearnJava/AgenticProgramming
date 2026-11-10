"""
nimbus/park_ingest.py: reviewed NPS pages become text-only publication inputs and compact runtime identities.
Ingestion runs before deployment; visitors cannot add a source or cause the chat to crawl the web.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nimbus.park_models import Destination, ParkChunk, Season
from nimbus.park_text import record_hash, to_embedding_text
from nimbus.utils import checked_source_url

MAX_SOURCE_BYTES = 2_000_000
TARGET_CHUNK_WORDS = 320
DATE_PATTERN = re.compile(r"Last updated:\s*([A-Za-z]+ \d{1,2}, \d{4})")


class SourceSpec(BaseModel):
    """An explicit source allowlist entry and its reviewed section names."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    park_id: str
    destination_ids: list[str] = Field(min_length=1)
    title: str
    url: str
    include_sections: list[str] = Field(min_length=1)
    seasons: list[Season] = Field(default_factory=lambda: list[Season](["all"]), min_length=1, max_length=4)
    section_seasons: dict[str, list[Season]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reviewed_seasons(self) -> "SourceSpec":
        """Season qualifiers must be explicit reviewed metadata for included sections, never inferred from names."""
        if set(self.section_seasons) - set(self.include_sections) or any(
            not values or len(values) > 4 for values in self.section_seasons.values()
        ):
            raise ValueError("Season metadata must name included sections and contain one to four seasons")
        return self

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """Apply shared URL safety, then require a reviewed document identity on www.nps.gov, without a fragment."""
        canonical = checked_source_url(value)
        parsed = urlsplit(canonical)
        if parsed.hostname != "www.nps.gov" or parsed.fragment:
            raise ValueError("Reviewed park sources must be document URLs on www.nps.gov without fragments")
        return canonical


@dataclass
class PageSection:
    """One page heading and its complete paragraphs, in their source order."""

    title: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class ParsedPage:
    """The article's text and its publisher-provided revision date, when present."""

    sections: list[PageSection]
    source_updated_at: str | None


class ArticleParser(HTMLParser):
    """Reads article blocks after the page title, skipping navigation, scripts and footer content."""

    def __init__(self) -> None:
        """Start with no article and no accumulated text."""
        super().__init__(convert_charrefs=True)
        self.sections: list[PageSection] = []
        self.buffer: list[str] = []
        self.is_active = False
        self.is_finished = False
        self.heading: str | None = None
        self.ignored: list[str] = []
        self.title = "Overview"

    def flush(self) -> None:
        """Keep one normalized paragraph, without page dates or UI-only labels."""
        text = " ".join("".join(self.buffer).split()).strip(" |")
        self.buffer = []
        if not text or text.startswith("Last updated:"):
            return
        if not self.sections or self.sections[-1].title != self.title:
            self.sections.append(PageSection(self.title))
        self.sections[-1].paragraphs.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Recognize headings and block boundaries, ignoring non-article elements."""
        attributes = dict(attrs)
        classes = attributes.get("class") or ""
        if tag in {"script", "style", "nav", "footer", "figcaption"}:
            self.ignored.append(tag)
        if self.ignored or self.is_finished:
            return
        if "ParkFooter" in classes or "GlobalFooter" in classes:
            self.flush()
            self.is_finished = True
            return
        if tag == "h1" and ("page-title" in classes or not self.is_active):
            self.is_active = True
        if not self.is_active:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading = tag
        elif tag in {"p", "li", "br", "tr"}:
            self.flush()
        elif tag in {"td", "th"}:
            self.buffer.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        """Finish headings and paragraphs without removing inline emphasis text."""
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        if not self.is_active or self.is_finished:
            return
        if tag == self.heading:
            self.title = " ".join("".join(self.buffer).split())
            self.buffer = []
            self.heading = None
        elif tag in {"p", "li", "div", "tr", "main"}:
            self.flush()

    def handle_data(self, data: str) -> None:
        """Accumulate only visible article text."""
        if self.is_active and not self.is_finished and not self.ignored:
            self.buffer.append(data)


def parse_page(html: str) -> ParsedPage:
    """Extract article sections and a normalized source revision date."""
    parser = ArticleParser()
    parser.feed(html)
    parser.close()
    parser.flush()
    updated = DATE_PATTERN.search(re.sub(r"<[^>]+>", "", html))
    date = datetime.strptime(updated.group(1), "%B %d, %Y").date().isoformat() if updated else None
    return ParsedPage(parser.sections, date)


def chunk_page(
    source: SourceSpec, page: ParsedPage, fetched_at: str, *, max_words: int = TARGET_CHUNK_WORDS
) -> list[ParkChunk]:
    """Chunk reviewed sections at paragraph boundaries, retaining conditions and source metadata."""
    # ① Fail closed when an approved heading disappears: the source needs a fresh review.
    available = {section.title for section in page.sections}
    missing = set(source.include_sections) - available
    if missing:
        raise ValueError(f"Missing reviewed sections in {source.id}: {', '.join(sorted(missing))}")
    chunks: list[ParkChunk] = []
    for section in page.sections:
        if section.title not in source.include_sections:
            continue
        # ② A paragraph may exceed the target; breaking it can separate an instruction from its qualifier.
        groups: list[list[str]] = [[]]
        for paragraph in section.paragraphs:
            if groups[-1] and sum(len(item.split()) for item in groups[-1]) + len(paragraph.split()) > max_words:
                groups.append([])
            groups[-1].append(paragraph)
        for group in groups:
            text = "\n\n".join(group)
            if not text:
                continue
            digest = hashlib.sha256(f"{source.id}\n{section.title}\n{text}".encode()).hexdigest()
            chunks.append(
                ParkChunk(
                    id=f"{source.id}-{digest[:16]}",
                    document_id=source.id,
                    park_id=source.park_id,
                    destination_ids=source.destination_ids,
                    title=source.title,
                    section=section.title,
                    text=text,
                    source_url=source.url,
                    source_updated_at=page.source_updated_at,
                    fetched_at=fetched_at,
                    content_hash=digest,
                    seasons=source.section_seasons.get(section.title, source.seasons),
                )
            )
    return chunks


INDEX_SCHEMA = 2
MAX_INDEX_BYTES = 20 * 1024 * 1024
INDEX_FIELDS = {
    "schema_version",
    "index_version",
    "corpus_built_at",
    "destinations",
    "chunks",
    "source_count",
    "chunk_count",
}


def compact_chunk(chunk: ParkChunk) -> dict[str, Any]:
    """Retain checked identities and provenance without storing passage text or embeddings in the runtime catalog."""
    return {**chunk.model_dump(mode="json", exclude={"text"}), "record_hash": record_hash(chunk)}


def _version(destinations: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> str:
    """Version the exact compact catalog, including full-record hashes, independently of its build timestamp."""
    document = {
        "schema_version": INDEX_SCHEMA,
        "destinations": sorted(destinations, key=lambda item: item["id"]),
        "chunks": sorted(chunks, key=lambda item: item["id"]),
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _checked_records(
    destinations: list[Destination], chunks: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject duplicate identities, invalid scopes and inconsistent source provenance before publication."""
    if not destinations or len(destinations) > 100 or not chunks or len(chunks) > 1000:
        raise ValueError("Index requires bounded destinations and chunks")
    places = {item.id: item.park_id for item in destinations}
    if len(places) != len(destinations) or len({item["id"] for item in chunks}) != len(chunks):
        raise ValueError("Index identities must be unique")
    if any(any(places.get(identity) != item["park_id"] for identity in item["destination_ids"]) for item in chunks):
        raise ValueError("Chunk names an unknown destination")
    sources: dict[str, tuple[str, str, str]] = {}
    for item in chunks:
        provenance = (item["park_id"], item["source_url"], item["title"])
        if item["document_id"] in sources and sources[item["document_id"]] != provenance:
            raise ValueError("Source identity has conflicting provenance")
        sources[item["document_id"]] = provenance
    return (
        sorted((item.model_dump(mode="json") for item in destinations), key=lambda item: item["id"]),
        sorted(chunks, key=lambda item: item["id"]),
    )


def _read_document(path: Path) -> dict[str, Any]:
    """Read a bounded JSON artifact; do not create missing files or accept unknown schema fields."""
    if not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError("Missing or oversized park artifact")
    document: Any = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(document, dict)
        or set(document) != INDEX_FIELDS
        or type(document["schema_version"]) is not int
        or document["schema_version"] != INDEX_SCHEMA
        or not isinstance(document["index_version"], str)
        or not re.fullmatch(r"[a-f0-9]{16}", document["index_version"])
        or not isinstance(document["corpus_built_at"], str)
        or datetime.fromisoformat(document["corpus_built_at"]).tzinfo is None
        or not isinstance(document["destinations"], list)
        or not isinstance(document["chunks"], list)
    ):
        raise ValueError("Invalid park artifact schema")
    return document


def _checked_header(document: dict[str, Any], places: list[dict[str, Any]], chunks: list[dict[str, Any]]) -> None:
    """Counts and version must identify exactly the validated public records, not merely a plausible index."""
    if (
        document["index_version"] != _version(places, chunks)
        or type(document["chunk_count"]) is not int
        or document["chunk_count"] != len(chunks)
        or type(document["source_count"]) is not int
        or document["source_count"] != len({chunk["document_id"] for chunk in chunks})
    ):
        raise ValueError("Park artifact count or version mismatch")


def load_prepared(path: Path) -> dict[str, Any]:
    """Validate the text-only publication artifact, including every dense-input hash and full-record identity."""
    document = _read_document(path)
    destinations = [Destination.model_validate(value) for value in document["destinations"]]
    chunks = [ParkChunk.model_validate(value) for value in document["chunks"]]
    for chunk in chunks:
        expected = hashlib.sha256(to_embedding_text(chunk.title, chunk.section, chunk.text).encode()).hexdigest()
        if chunk.content_hash != expected:
            raise ValueError("Prepared passage content hash mismatch")
    places, compact = _checked_records(destinations, [compact_chunk(chunk) for chunk in chunks])
    _checked_header(document, places, compact)
    return {
        **document,
        "destinations": places,
        "chunks": [chunk.model_dump(mode="json") for chunk in sorted(chunks, key=lambda item: item.id)],
    }


def load_catalog(path: Path) -> dict[str, Any]:
    """Validate the runtime identity catalog; it must contain neither passage text nor stored vectors."""
    document = _read_document(path)
    destinations = [Destination.model_validate(value) for value in document["destinations"]]
    chunks: list[dict[str, Any]] = []
    expected_fields = (set(ParkChunk.model_fields) - {"text"}) | {"record_hash"}
    for value in document["chunks"]:
        if (
            not isinstance(value, dict)
            or set(value) != expected_fields
            or not isinstance(value["record_hash"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["record_hash"])
        ):
            raise ValueError("Invalid compact passage metadata")
        metadata = ParkChunk.model_validate(
            {**{name: item for name, item in value.items() if name != "record_hash"}, "text": "metadata only"}
        ).model_dump(mode="json", exclude={"text"})
        chunks.append({**metadata, "record_hash": value["record_hash"]})
    places, chunks = _checked_records(destinations, chunks)
    _checked_header(document, places, chunks)
    return {**document, "destinations": places, "chunks": chunks}


def write_index(
    path: Path,
    destinations: list[Destination],
    chunks: list[ParkChunk],
    *,
    catalog_path: Path | None = None,
    built_at: str | None = None,
) -> str:
    """Publish validated text-only preparation and a compact runtime catalog, with each file replaced atomically."""
    # ① Validate every record and digest before touching either currently prepared artifact.
    full_records = [ParkChunk.model_validate(chunk.model_dump()) for chunk in chunks]
    for chunk in full_records:
        expected = hashlib.sha256(to_embedding_text(chunk.title, chunk.section, chunk.text).encode()).hexdigest()
        if chunk.content_hash != expected:
            raise ValueError("Prepared passage content hash mismatch")
    places, compact = _checked_records(destinations, [compact_chunk(chunk) for chunk in full_records])
    timestamp = built_at or datetime.now(UTC).isoformat()
    if datetime.fromisoformat(timestamp).tzinfo is None:
        raise ValueError("Build time needs a timezone")
    version = _version(places, compact)
    common: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA,
        "index_version": version,
        "corpus_built_at": timestamp,
        "destinations": places,
        "source_count": len({item["document_id"] for item in compact}),
        "chunk_count": len(compact),
    }
    prepared = {
        **common,
        "chunks": [item.model_dump(mode="json") for item in sorted(full_records, key=lambda item: item.id)],
    }
    catalog = {**common, "chunks": compact}
    catalog_path = catalog_path or path.with_name("catalog.json")
    if path.resolve() == catalog_path.resolve():
        raise ValueError("Preparation and catalog paths must differ")
    # ② Stage both complete files first. A reader checks versions rather than consuming a mismatched pair.
    staged: list[tuple[Path, Path]] = []
    try:
        for target, document in ((path, prepared), (catalog_path, catalog)):
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".building.json")
            staged.append((temporary, target))
            payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            if len(payload.encode()) > MAX_INDEX_BYTES:
                raise ValueError("Oversized park artifact")
            temporary.write_text(payload, encoding="utf-8")
        for temporary, target in staged:
            temporary.replace(target)
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)
    return version
