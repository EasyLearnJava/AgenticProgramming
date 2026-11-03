"""
tools/build_park_index.py: refresh approved NPS snapshots for review, or publish a reproducible park knowledge index.
Default builds from committed snapshots. --refresh downloads snapshots only; review before a separate build.
CPU MiniLM embeddings are built by default; --lexical-only builds a lightweight fallback index.
"""

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from nimbus.config import Settings
from nimbus.park_embeddings import (
    MINILM_DIMENSIONS,
    MINILM_MODEL,
    MiniLMEmbeddings,
    split_for_encoder,
    to_embedding_text,
)
from nimbus.park_ingest import (
    MAX_SOURCE_BYTES,
    PageSection,
    ParsedPage,
    SourceSpec,
    chunk_page,
    parse_page,
    write_index,
)
from nimbus.parks import Destination, ParkChunk

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "parks"
FETCH_TIMEOUT_SECONDS = 15
EMBED_TIMEOUT_SECONDS = 60
EMBED_DIMENSIONS = MINILM_DIMENSIONS


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


def reusable_vectors(path: Path, model: str) -> dict[str, list[float]]:
    """Reuse unchanged passage vectors only when the model and dimensionality match."""
    if not path.is_file():
        return {}
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            if metadata.get("embedding_model") != model or metadata.get("embedding_dimensions") != str(
                EMBED_DIMENSIONS
            ):
                return {}
            rows = connection.execute("SELECT json, embedding FROM chunks WHERE embedding IS NOT NULL").fetchall()
        result: dict[str, list[float]] = {}
        for payload, embedding in rows:
            chunk = ParkChunk.model_validate_json(payload)
            values: Any = json.loads(embedding)
            if isinstance(values, list) and all(isinstance(value, (int, float)) for value in values):
                result[chunk.content_hash] = values
        return result
    except (sqlite3.Error, ValueError):
        return {}


def prepare_embeddings(
    chunks: list[ParkChunk], settings: Settings, previous: Path
) -> tuple[list[ParkChunk], list[list[float]], str]:
    """Fit every passage to MiniLM's actual tokenizer budget, then embed on CPU with pinned weights."""
    # Use the host's trusted CA store for Hugging Face downloads on managed Windows machines.
    import truststore

    truststore.inject_into_ssl()
    encoder = MiniLMEmbeddings(settings.parks_model_cache, settings.parks_model_revision)
    capability = encoder.availability()
    if capability == "missing_dependencies":
        raise ValueError("Index embeddings require the optional ml dependency group")
    if capability != "ready":
        from huggingface_hub import snapshot_download

        # Provision only the pinned encoder files, then keep all model loading strictly offline.
        snapshot_download(
            repo_id=MINILM_MODEL,
            revision=settings.parks_model_revision,
            cache_dir=settings.parks_model_cache,
            max_workers=1,
            allow_patterns=[
                "config.json",
                "modules.json",
                "config_sentence_transformers.json",
                "sentence_bert_config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "vocab.txt",
                "model.safetensors",
                "1_Pooling/config.json",
            ],
        )
    prepared: list[ParkChunk] = []
    for chunk in chunks:
        prefix = f"{chunk.title}\n{chunk.section}"
        for text in split_for_encoder(chunk.text, prefix, encoder):
            content = to_embedding_text(chunk.title, chunk.section, text)
            digest = hashlib.sha256(content.encode()).hexdigest()
            prepared.append(
                chunk.model_copy(
                    update={
                        "id": f"{chunk.document_id}-{digest[:16]}",
                        "text": text,
                        "content_hash": digest,
                    }
                )
            )
    cached = reusable_vectors(previous, encoder.identity)
    missing = {chunk.content_hash: chunk for chunk in prepared if chunk.content_hash not in cached}
    if missing:
        vectors = encoder.encode(
            [to_embedding_text(chunk.title, chunk.section, chunk.text) for chunk in missing.values()]
        )
        cached.update(zip(missing, vectors, strict=True))
    return prepared, [cached[chunk.content_hash] for chunk in prepared], encoder.identity


async def bounded_command(command: list[str], seconds: float) -> None:
    """Run an indexing worker within a real overall deadline; kill and reap it on timeout or cancellation."""
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        async with asyncio.timeout(seconds):
            status = await process.wait()
        if status != 0:
            raise ValueError("Embedding worker failed; check the ML installation and pinned model cache")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def bounded_embeddings(
    chunks: list[ParkChunk], settings: Settings, previous: Path
) -> tuple[list[ParkChunk], list[list[float]], str]:
    """Isolate downloads, tokenizer work and CPU inference so their deadline actually stops the operation."""
    previous_path = await asyncio.to_thread(previous.resolve)
    with tempfile.TemporaryDirectory(prefix="nimbus-index-") as temporary:
        directory = Path(temporary)
        request, response = directory / "request.json", directory / "response.json"
        request.write_text(
            json.dumps(
                {
                    "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
                    "cache": str(settings.parks_model_cache),
                    "revision": settings.parks_model_revision,
                    "previous": str(previous_path),
                }
            ),
            encoding="utf-8",
        )
        await bounded_command(
            [
                sys.executable,
                "-m",
                "tools.build_park_index",
                "--embedding-worker",
                str(request),
                "--embedding-output",
                str(response),
            ],
            EMBED_TIMEOUT_SECONDS,
        )
        result = json.loads(response.read_text(encoding="utf-8"))
        prepared = TypeAdapter(list[ParkChunk]).validate_python(result["chunks"])
        return prepared, result["vectors"], str(result["model"])


def embedding_worker(request: Path, output: Path) -> None:
    """Produce one trusted builder result; the parent process owns the deadline and publication."""
    payload = json.loads(request.read_text(encoding="utf-8"))
    chunks = TypeAdapter(list[ParkChunk]).validate_python(payload["chunks"])
    settings = Settings(
        _env_file=None, parks_model_cache=Path(payload["cache"]), parks_model_revision=payload["revision"]
    )
    prepared, vectors, model = prepare_embeddings(chunks, settings, Path(payload["previous"]))
    output.write_text(
        json.dumps(
            {
                "chunks": [chunk.model_dump(mode="json") for chunk in prepared],
                "vectors": vectors,
                "model": model,
            }
        ),
        encoding="utf-8",
    )


async def run(arguments: argparse.Namespace) -> int:
    """Refresh review inputs or publish an index, returning a command exit code."""
    manifest = Manifest.model_validate_json(arguments.manifest.read_text(encoding="utf-8"))
    snapshot_dir = arguments.manifest.parent / "snapshots"
    if arguments.refresh:
        await refresh_sources(manifest, snapshot_dir)
        print(f"Refreshed {len(manifest.sources)} source snapshots. Review their changes before publishing.")
        if not arguments.publish:
            return 0
    chunks = read_chunks(manifest, snapshot_dir)
    settings = Settings()
    embeddings = None
    model = ""
    if not arguments.lexical_only:
        chunks, embeddings, model = await bounded_embeddings(chunks, settings, arguments.output)
    version = write_index(arguments.output, manifest.destinations, chunks, embeddings=embeddings, embedding_model=model)
    mode = "hybrid" if embeddings else "lexical"
    print(f"Published park index {version}: {len(manifest.destinations)} destinations, {len(chunks)} chunks, {mode}.")
    return 0


def main() -> int:
    """Parse explicit ingestion options; print sanitized failures without source bodies or provider exception text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "manifest.json")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "index.sqlite")
    parser.add_argument("--refresh", action="store_true", help="Download snapshots for review without publishing")
    parser.add_argument("--publish", action="store_true", help="Publish after --refresh; normally review first")
    parser.add_argument("--lexical-only", action="store_true", help="Build without MiniLM vectors")
    parser.add_argument("--embedding-worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--embedding-output", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    try:
        if arguments.embedding_worker:
            if arguments.embedding_output is None:
                raise ValueError("Embedding worker output is required")
            embedding_worker(arguments.embedding_worker, arguments.embedding_output)
            return 0
        return asyncio.run(run(arguments))
    except Exception as error:
        print(
            f"Park index build failed ({type(error).__name__}); the existing index was not replaced.", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
