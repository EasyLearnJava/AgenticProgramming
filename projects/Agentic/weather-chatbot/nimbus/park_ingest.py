"""
nimbus/park_ingest.py: reviewed NPS pages become paragraph-preserving chunks and an atomic, read-only SQLite index.
Ingestion runs before deployment; visitors cannot add a source or cause the chat to crawl the web.
"""

import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from nimbus.parks import Destination, ParkChunk, Season
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


def write_index(
    path: Path,
    destinations: list[Destination],
    chunks: list[ParkChunk],
    *,
    embeddings: list[list[float]] | None = None,
    embedding_model: str = "",
    built_at: str | None = None,
) -> str:
    """Validate all records, write a complete replacement, and atomically publish it; return its content version."""
    # ① Validate the entire generation before touching the currently published index.
    dimensions = len(embeddings[0]) if embeddings else 0
    if embeddings is not None and (
        not embedding_model
        or len(embeddings) != len(chunks)
        or not dimensions
        or any(len(vector) != dimensions or not all(math.isfinite(value) for value in vector) for vector in embeddings)
        or any(not any(vector) for vector in embeddings)
    ):
        raise ValueError("Invalid or mismatched park embeddings")
    if not destinations or not chunks or len({item.id for item in chunks}) != len(chunks):
        raise ValueError("Index requires destinations and unique chunks")
    destination_ids = {item.id: item.park_id for item in destinations}
    if any(
        any(destination_ids.get(identity) != chunk.park_id for identity in chunk.destination_ids) for chunk in chunks
    ):
        raise ValueError("Chunk names an unknown destination")
    records = [chunk.model_dump_json() for chunk in sorted(chunks, key=lambda item: item.id)]
    places = [item.model_dump_json() for item in sorted(destinations, key=lambda item: item.id)]
    version = hashlib.sha256("\n".join([*places, *records, embedding_model]).encode()).hexdigest()[:16]
    metadata = {
        "schema_version": "1",
        "index_version": version,
        "embedding_model": embedding_model,
        "embedding_dimensions": str(dimensions),
        "corpus_built_at": built_at or datetime.now(UTC).isoformat(),
        "source_count": str(len({chunk.document_id for chunk in chunks})),
        "chunk_count": str(len(chunks)),
    }
    # ② The temporary database shares the destination filesystem, so replace is atomic.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".building.sqlite")
    try:
        temporary.unlink(missing_ok=True)
        with closing(sqlite3.connect(temporary)) as connection, connection:
            connection.executescript(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                "CREATE TABLE destinations (id TEXT PRIMARY KEY, json TEXT NOT NULL);"
                "CREATE TABLE chunks (id TEXT PRIMARY KEY, json TEXT NOT NULL, embedding TEXT);"
            )
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", metadata.items())
            connection.executemany(
                "INSERT INTO destinations VALUES (?, ?)",
                ((item.id, item.model_dump_json()) for item in destinations),
            )
            connection.executemany(
                "INSERT INTO chunks VALUES (?, ?, ?)",
                (
                    (chunk.id, chunk.model_dump_json(), json.dumps(embeddings[index]) if embeddings else None)
                    for index, chunk in enumerate(chunks)
                ),
            )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return version
