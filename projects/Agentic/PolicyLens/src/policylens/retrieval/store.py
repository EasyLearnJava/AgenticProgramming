"""SQLite persists JSON + numeric vectors; rebuilding replaces the index atomically.

    Exact cosine search is intentionally simple for a small handbook. At larger
    scale replace this adapter with a vector database rather than loading it all.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import numpy as np

from policylens.models import Chunk


@dataclass(frozen=True)
class QuerySession:
    """Pin one immutable index generation across a query or an entire evaluation."""
    chunks: tuple[Chunk, ...]
    matrix: np.ndarray
    metadata: MappingProxyType
    profile: object


class IndexStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, body TEXT, vector TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")

    @contextmanager
    def connect(self):
        # sqlite3's own context manager commits/rolls back but does NOT close.
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def replace(self, chunks: list[Chunk], vectors: list[list[float]], identity: str,
                documents: list[dict], corpus_hash: str):
        if len(chunks) != len(vectors) or not chunks:
            raise ValueError("An index must contain one vector for every chunk.")
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or not np.isfinite(matrix).all():
            raise ValueError("Embedding provider returned invalid vectors.")
        metadata = {"identity": identity, "documents": documents, "corpus_hash": corpus_hash,
                    "built_at": datetime.now(timezone.utc).isoformat(), "dimensions": matrix.shape[1]}
        # Readers see either the old complete index or the new complete index.
        with self.connect() as db:
            db.execute("DELETE FROM chunks")
            db.executemany("INSERT INTO chunks VALUES (?, ?, ?)",
                           [(c.id, c.model_dump_json(), json.dumps(v)) for c, v in zip(chunks, vectors)])
            db.execute("DELETE FROM metadata")
            db.executemany("INSERT INTO metadata VALUES (?, ?)",
                           [(key, json.dumps(value)) for key, value in metadata.items()])

    def snapshot(self) -> tuple[list[Chunk], np.ndarray, dict]:
        # A single read transaction ties chunks and metadata to the same generation.
        with self.connect() as db:
            db.execute("BEGIN")
            meta = {key: json.loads(value) for key, value in db.execute("SELECT key, value FROM metadata")}
            rows = db.execute("SELECT body, vector FROM chunks ORDER BY id").fetchall()
        chunks = [Chunk.model_validate_json(row[0]) for row in rows]
        vectors = np.asarray([json.loads(row[1]) for row in rows], dtype=np.float32)
        return chunks, vectors, meta

    def session(self) -> QuerySession:
        from policylens.grounding import EvidenceProfile
        chunks, matrix, metadata = self.snapshot()
        matrix.setflags(write=False)
        return QuerySession(tuple(chunks), matrix, MappingProxyType(metadata), EvidenceProfile(chunks))

