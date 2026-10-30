"""
IT Knowledge Base: The Vector File
==================================

The chunks' vectors, saved in a file, so a start-up can load them rather than embed the chunks again: python main.py
index saves them (on Vercel, each deployment's build runs it), and each start-up loads them. It handles:
  1. Saving the vectors with what they were made from: the provider, the model, the number of dimensions, and a hash
     of each chunk's text
  2. Loading them only when every chunk has one, made the same way: each chunk's vector is found by its text's hash,
     so the chunks' order doesn't matter, but after an edited article, another chunk size or another model, the file
     isn't used. Nor is one that can't be read. Why is logged (a missing file isn't a warning: nothing has been saved
     yet), and the chunks are embedded instead
  3. Writing the file whole or not at all: it's written beside, flushed to disk, then renamed into place

Usage:
    vector_file = VectorFile(path, provider="google", model="gemini-embedding-001", dimensions=768)
    vector_file.save(texts, vectors)        # VectorFileError if it can't be written
    vector_file.load(texts)                 ->  one vector per text, in order; or None, and why is logged
"""
import contextlib
import hashlib
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from src.exceptions import VectorFileError
from src.observability.tracing import span

logger = logging.getLogger(__name__)


class SavedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_sha256: str
    vector: list[float]


class SavedVectors(BaseModel):
    """What the file holds: how the vectors were made, then each chunk's text hash and vector."""
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str
    dimensions: int
    saved_at: datetime
    chunks: list[SavedChunk]


def _text_hash(text: str) -> str:
    """A chunk's text as 64 hex characters: the same text, the same hash; any change, another."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class VectorFile:
    """
    The chunks' vectors in a JSON file, with what they were made from.

    Step 1: Configure: the constructor stores the path and how the vectors are made; nothing is read
    Step 2: Use: save() once the chunks are embedded (python main.py index); load() at each start-up
    """

    def __init__(self, path: Path, *, provider: str, model: str, dimensions: int):
        self.path = path
        self.provider, self.model, self.dimensions = provider, model, dimensions

    def save(self, texts: list[str], vectors: list[list[float]]) -> None:
        """Write the file: each text's hash and vector, in order, and how they were made. Raises VectorFileError."""
        with span("embeddings.save_vectors", file=self.path.name, vectors=len(vectors)):
            if len(texts) != len(vectors):
                raise VectorFileError(f"{len(texts)} texts but {len(vectors)} vectors: nothing was saved")
            saved = SavedVectors(provider=self.provider, model=self.model, dimensions=self.dimensions,
                                 saved_at=datetime.now(UTC),
                                 chunks=[SavedChunk(text_sha256=_text_hash(text), vector=vector)
                                         for text, vector in zip(texts, vectors, strict=True)])
            self._write(saved.model_dump_json())

    def load(self, texts: list[str]) -> list[list[float]] | None:
        """The saved vector of each text, in order, if the file holds one for every text, made the way this one makes
        them; else None, with why logged (the caller then embeds them)."""
        with span("embeddings.load_vectors", file=self.path.name) as fields:
            try:
                saved = SavedVectors.model_validate_json(self.path.read_bytes())
            except FileNotFoundError:
                fields.update(used=False, reason="there's no file: python main.py index makes it")
                return None
            except OSError as err:
                vectors, reason = None, f"it can't be read ({err.strerror or err})"
            except ValidationError as err:
                problem = err.errors()[0]
                where = ".".join(str(part) for part in problem["loc"]) or "the file"
                vectors, reason = None, f"it doesn't hold saved vectors ({where}: {problem['msg']})"
            else:
                vectors, reason = self._vectors_for(saved, texts)
            if vectors is None:
                fields.update(used=False, reason=reason)
                logger.warning("The saved vectors aren't used: %s. The chunks are embedded instead; python main.py "
                               "index saves their vectors", reason)
                return None
            fields.update(used=True, vectors=len(vectors), saved_at=saved.saved_at.isoformat(timespec="seconds"))
            return vectors

    def _vectors_for(self, saved: SavedVectors, texts: list[str]) -> tuple[list[list[float]] | None, str]:
        """Each text's saved vector, found by the hash of the text, if every text has one, made the way this file
        makes them; else None, and why."""
        if (saved.provider, saved.model, saved.dimensions) != (self.provider, self.model, self.dimensions):
            return None, (f"they were made by {saved.provider}'s {saved.model} at {saved.dimensions} numbers, and the "
                          f"chunks are embedded by {self.provider}'s {self.model} at {self.dimensions}")
        wrong = sorted({len(chunk.vector) for chunk in saved.chunks} - {self.dimensions})
        if wrong:
            return None, f"some have {', '.join(map(str, wrong))} numbers, not {self.dimensions}"
        by_hash = {chunk.text_sha256: chunk.vector for chunk in saved.chunks}
        hashes = [_text_hash(text) for text in texts]
        missing = sum(text_hash not in by_hash for text_hash in hashes)
        if missing:
            return None, (f"there's no saved vector for {missing} of the {len(hashes)} chunks (an article, the "
                          "columns read or the chunking changed since they were saved)")
        return [by_hash[text_hash] for text_hash in hashes], ""

    def _write(self, text: str) -> None:
        """Write the file beside, under this run's own name, flush it to disk, then rename it into place: a start-up
        never reads half a file, and two runs at once never mix theirs. Raises VectorFileError."""
        partial = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with partial.open("w", encoding="utf-8") as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(partial, self.path)
        except OSError as err:
            with contextlib.suppress(OSError):
                partial.unlink(missing_ok=True)
            raise VectorFileError(f"Couldn't save the vectors in {self.path}: {err.strerror or err}") from err
