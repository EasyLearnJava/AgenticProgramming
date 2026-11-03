"""CPU MiniLM embeddings shared by ingestion and retrieval, with tokenizer-aware chunk limits and pinned weights."""

import asyncio
import importlib.util
import threading
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

MINILM_MODEL: Final = "sentence-transformers/all-MiniLM-L6-v2"
MINILM_DIMENSIONS: Final = 384
MINILM_MAX_TOKENS: Final = 256


class EmbeddingBusyError(RuntimeError):
    """The single inference worker is already occupied; requests must use keyword retrieval instead of queuing."""


class MiniLMEmbeddings:
    """One lazily loaded CPU encoder; runtime loads cached weights only and never downloads during a question."""

    def __init__(self, cache_folder: Path, revision: str, *, allow_download: bool = False) -> None:
        """Configure the model without importing PyTorch, loading weights, or contacting the network."""
        self.cache_folder = cache_folder
        self.revision = revision
        self.allow_download = allow_download
        self._model: Any = None
        self._lock = threading.Lock()
        self._query_lock = threading.Lock()
        self._pending: Future[list[list[float]]] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nimbus-embedding")

    @property
    def identity(self) -> str:
        """The exact model and weight revision that must match between documents and questions."""
        return f"{MINILM_MODEL}@{self.revision}"

    def _load(self) -> Any:
        """Load trusted, pinned weights onto CPU once; callers hold the model lock."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                device="cpu",
                revision=self.revision,
                cache_folder=str(self.cache_folder),
                local_files_only=not self.allow_download,
                trust_remote_code=False,
            )
            self._model.max_seq_length = MINILM_MAX_TOKENS
        return self._model

    def availability(self) -> str:
        """Check local capabilities without importing ML libraries, loading weights, downloading or starting threads."""
        if any(importlib.util.find_spec(name) is None for name in ("sentence_transformers", "torch", "transformers")):
            return "missing_dependencies"
        snapshot = self.cache_folder / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots" / self.revision
        if (
            not all((snapshot / name).is_file() for name in ("config.json", "modules.json", "tokenizer.json"))
            or not (snapshot / "model.safetensors").is_file()
        ):
            return "missing_weights"
        return "ready"

    def token_count(self, text: str) -> int:
        """Count the actual encoder input, including special tokens, without silent truncation."""
        with self._lock:
            model = self._load()
            return len(model.tokenizer.encode(text, add_special_tokens=True, truncation=False, verbose=False))

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Produce normalized 384-dimensional vectors on CPU, rejecting inputs that would be truncated."""
        if not texts:
            return []
        with self._lock:
            model = self._load()
            if any(
                len(model.tokenizer.encode(text, truncation=False, verbose=False)) > MINILM_MAX_TOKENS for text in texts
            ):
                raise ValueError("MiniLM input exceeds its tokenizer limit; rebuild smaller chunks")
            vectors = model.encode(
                list(texts),
                batch_size=32,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return [[float(value) for value in row] for row in vectors]

    async def embed_query(self, text: str) -> list[float]:
        """Use one dedicated worker with no queued requests; timeout never consumes the default DNS executor."""
        # ① A timed-out native operation can finish, but later requests cannot create more work or lock waiters.
        with self._query_lock:
            if self._pending is not None and not self._pending.done():
                raise EmbeddingBusyError("Local embedding worker is busy")
            pending = self._executor.submit(self.encode, [text])
            self._pending = pending
        pending.add_done_callback(self._forget_query)
        wrapped = asyncio.wrap_future(pending)
        wrapped.add_done_callback(self._consume_exception)
        vectors = await asyncio.shield(wrapped)
        return vectors[0]

    def _forget_query(self, pending: Future[list[list[float]]]) -> None:
        """Release completed query state even if its original request timed out or was cancelled."""
        with self._query_lock:
            if self._pending is pending:
                self._pending = None

    @staticmethod
    def _consume_exception(future: asyncio.Future[list[list[float]]]) -> None:
        """Retrieve failures of abandoned requests without logging query text or retaining exception tracebacks."""
        if not future.cancelled():
            future.exception()


def to_embedding_text(title: str, section: str, text: str) -> str:
    """The identical title/section/body representation used when counting and embedding passages."""
    return f"{title}\n{section}\n{text}"


@lru_cache(maxsize=2)
def cached_encoder(cache_folder: Path, revision: str) -> MiniLMEmbeddings:
    """Share lazy model loading and serialized inference across app instances in the same process."""
    return MiniLMEmbeddings(cache_folder, revision)


def split_for_encoder(text: str, prefix: str, encoder: MiniLMEmbeddings) -> list[str]:
    """Keep paragraphs and sentences intact where possible, with overlap for unusually long sentences."""
    import re

    units = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    output: list[str] = []
    current = ""
    # ① Keep each sentence with its qualifier whenever it fits the encoder's actual input budget.
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()
        if encoder.token_count(f"{prefix}\n{candidate}") <= MINILM_MAX_TOKENS:
            current = candidate
            continue
        if current:
            output.append(current)
            current = ""
        if encoder.token_count(f"{prefix}\n{unit}") <= MINILM_MAX_TOKENS:
            current = unit
            continue
        # ② A single oversized sentence is split by words with context overlap; the full source stays in snapshots.
        words = unit.split()
        offset = 0
        while offset < len(words):
            end = offset
            while (
                end < len(words)
                and encoder.token_count(f"{prefix}\n{' '.join(words[offset : end + 1])}") <= MINILM_MAX_TOKENS
            ):
                end += 1
            if end == offset:
                raise ValueError("Passage heading or individual word exceeds MiniLM's input budget")
            output.append(" ".join(words[offset:end]))
            offset = end if end == len(words) else max(offset + 1, end - 12)
    if current:
        output.append(current)
    return output
