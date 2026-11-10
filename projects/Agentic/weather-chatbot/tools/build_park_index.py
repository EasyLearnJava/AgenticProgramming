"""
tools/build_park_index.py: refresh approved NPS snapshots or prepare reproducible text-only Qdrant publication inputs.
Default builds from committed snapshots. --refresh downloads snapshots only; review before a separate build.
A pinned tokenizer preserves the hosted encoder's input budget; only the separate publisher generates embeddings.
"""

import argparse
import asyncio
import hashlib
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from pydantic import BaseModel, ConfigDict, Field

from nimbus.park_ingest import (
    MAX_SOURCE_BYTES,
    PageSection,
    ParsedPage,
    SourceSpec,
    chunk_page,
    parse_page,
    write_index,
)
from nimbus.park_models import Destination, ParkChunk
from nimbus.park_text import TOKENIZER_SHA256, TokenCounter, split_for_tokens, to_embedding_text

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "parks"
FETCH_TIMEOUT_SECONDS = 15


class Manifest(BaseModel):
    """The complete allowlist of destinations and official pages, checked before network access."""

    model_config = ConfigDict(extra="forbid")
    destinations: list[Destination] = Field(min_length=1)
    sources: list[SourceSpec] = Field(min_length=1)


class SnapshotSection(BaseModel):
    """A reviewed heading and its preserved source paragraphs."""

    model_config = ConfigDict(extra="forbid")
    title: str
    paragraphs: list[str] = Field(min_length=1)


class Snapshot(BaseModel):
    """A source snapshot containing only the approved sections, with fetch provenance."""

    model_config = ConfigDict(extra="forbid")
    document_id: str
    source_url: str
    fetched_at: str
    source_updated_at: str | None
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    sections: list[SnapshotSection] = Field(min_length=1)


async def fetch_snapshot(http: httpx2.AsyncClient, source: SourceSpec) -> Snapshot:
    """Fetch one approved HTML page with byte/time limits, rejecting redirects and unexpected content."""
    # ① No redirect can silently turn an approved URL into an unreviewed source.
    async with (
        asyncio.timeout(FETCH_TIMEOUT_SECONDS),
        http.stream("GET", source.url, follow_redirects=False) as response,
    ):
        response.raise_for_status()
        if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
            raise ValueError(f"Expected HTML from {source.id}")
        body = bytearray()
        async for part in response.aiter_bytes():
            body.extend(part)
            if len(body) > MAX_SOURCE_BYTES:
                raise ValueError(f"Source too large: {source.id}")
    # ② Reject changed headings before saving a snapshot; retain source text, never generated guidance.
    page = parse_page(body.decode("utf-8"))
    fetched_at = datetime.now(UTC).isoformat()
    chunk_page(source, page, fetched_at)
    return Snapshot(
        document_id=source.id,
        source_url=source.url,
        fetched_at=fetched_at,
        source_updated_at=page.source_updated_at,
        source_sha256=hashlib.sha256(body).hexdigest(),
        sections=[
            SnapshotSection(**asdict(section)) for section in page.sections if section.title in source.include_sections
        ],
    )


async def refresh_sources(manifest: Manifest, directory: Path) -> None:
    """Download and validate all sources before replacing the review snapshots; do not publish the index."""
    async with httpx2.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as http:
        snapshots = [await fetch_snapshot(http, source) for source in manifest.sources]
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    for snapshot in snapshots:
        path = directory / f"{snapshot.document_id}.json"
        temporary = path.with_suffix(".pending.json")
        temporary.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def read_chunks(manifest: Manifest, directory: Path) -> list[ParkChunk]:
    """Validate source snapshots against the current allowlist, then chunk the reviewed sections."""
    chunks: list[ParkChunk] = []
    for source in manifest.sources:
        snapshot = Snapshot.model_validate_json((directory / f"{source.id}.json").read_text(encoding="utf-8"))
        if snapshot.document_id != source.id or snapshot.source_url != source.url:
            raise ValueError(f"Snapshot provenance does not match {source.id}")
        page = ParsedPage(
            [PageSection(section.title, section.paragraphs) for section in snapshot.sections],
            snapshot.source_updated_at,
        )
        chunks.extend(chunk_page(source, page, snapshot.fetched_at))
    return chunks


class PreparationTokenizer:
    """Count a pinned tokenizer's inputs without loading model weights or running local inference."""

    def __init__(self, path: Path = DATA_DIR / "tokenizer.json") -> None:
        """Verify the bundled tokenizer's exact bytes before constructing the tokenizer-only engine."""
        from tokenizers import Tokenizer

        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != TOKENIZER_SHA256:
            raise ValueError("Bundled park tokenizer does not match the reviewed revision")
        self._tokenizer = Tokenizer.from_str(data.decode("utf-8"))
        self._tokenizer.no_truncation()
        self._tokenizer.no_padding()

    def token_count(self, text: str) -> int:
        """Count real MiniLM input tokens including its boundary tokens, never truncated or padded."""
        return len(self._tokenizer.encode(text, add_special_tokens=True).ids)


def prepare_chunks(chunks: list[ParkChunk], counter: TokenCounter | None = None) -> list[ParkChunk]:
    """Fit complete reviewed passages to the hosted encoder's budget, without generating any vector."""
    counter = counter or PreparationTokenizer()
    prepared: list[ParkChunk] = []
    for chunk in chunks:
        prefix = f"{chunk.title}\n{chunk.section}"
        for text in split_for_tokens(chunk.text, prefix, counter):
            digest = hashlib.sha256(to_embedding_text(chunk.title, chunk.section, text).encode()).hexdigest()
            prepared.append(
                chunk.model_copy(
                    update={"id": f"{chunk.document_id}-{digest[:16]}", "text": text, "content_hash": digest}
                )
            )
    return prepared


async def run(arguments: argparse.Namespace) -> int:
    """Refresh review inputs or prepare versioned publication inputs; never contact Qdrant or an embedding model."""
    manifest = Manifest.model_validate_json(arguments.manifest.read_text(encoding="utf-8"))
    snapshot_dir = arguments.manifest.parent / "snapshots"
    if arguments.refresh:
        await refresh_sources(manifest, snapshot_dir)
        print(f"Refreshed {len(manifest.sources)} source snapshots. Review their changes before publishing.")
        if not arguments.publish:
            return 0
    chunks = prepare_chunks(read_chunks(manifest, snapshot_dir))
    version = write_index(arguments.output, manifest.destinations, chunks, catalog_path=arguments.catalog)
    print(
        f"Prepared park index {version}: {len(manifest.destinations)} destinations, "
        f"{len(chunks)} chunks, no embeddings."
    )
    print("Publish and verify these inputs with python -m tools.setup_park_search before deploying their catalog.")
    return 0


def main() -> int:
    """Parse explicit preparation options and report sanitized failures without source bodies or credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "prepared.json")
    parser.add_argument("--catalog", type=Path, default=DATA_DIR / "catalog.json")
    parser.add_argument("--refresh", action="store_true", help="Download snapshots for review without publishing")
    parser.add_argument("--publish", action="store_true", help="Prepare after --refresh; normally review first")
    arguments = parser.parse_args()
    try:
        return asyncio.run(run(arguments))
    except Exception as error:
        print(
            f"Park preparation failed ({type(error).__name__}); review the inputs before publishing.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
