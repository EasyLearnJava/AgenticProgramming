"""
IT Knowledge Base: Embeddings
=============================

Turns chunks into vectors with a remote embedding model, treated as what it is in production: a service that has
limits, fails now and then, costs money, and must never receive data it shouldn't. It handles:
  1. The model, chosen in kb_settings.toml behind LangChain's Embeddings interface: Gemini, or a stand-in that needs
     no key (make_embedding_model())
  2. A sensitive-data gate: Advanced/01's redaction runs on every chunk before it's sent, and what it finds is counted
  3. A cache on disk (EmbeddingCache, SQLite): each vector kept by its model, its size and the hash of its text, so an
     unchanged chunk is never embedded twice
  4. Batches under the API's limits, by count and by tokens, a few sent at once (bounded concurrency)
  5. Retries with exponential backoff and jitter for a rate limit (429), a server error (5xx) or a timeout; a clear
     error at once for anything else, a used-up daily quota among them
  6. Checks on what comes back (one vector per text, the right size, real numbers), and a report: chunks, cache hits,
     calls, retries, tokens and time

    ChunkEmbedder(model, model_name="google/gemini-embedding-001", dimensions=768, cache=cache).embed(chunks)
      ->  one vector per chunk, in order; each chunk's metadata gets embedding_model, embedding_dimensions, embedded_at
"""
import asyncio
import json
import logging
import math
import random
import sqlite3
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from google import genai
from google.genai.types import HttpOptions, HttpRetryOptions
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

from sensitive_data import redact
from utils import count_tokens, short_hash

logger = logging.getLogger(__name__)

# The defaults: kb_settings.toml's [embeddings] can change each one
PROVIDER = "google"
MODEL = "gemini-embedding-001"
DIMENSIONS = 768
BATCH_SIZE = 100            # texts per call: Gemini's batchEmbedContents takes up to 100
BATCH_TOKENS = 20_000       # estimated tokens per call
MAX_CONCURRENCY = 2         # calls at once
MAX_ATTEMPTS = 4            # tries per call, the first included
TIMEOUT_SECONDS = 30.0      # each try is cut off after this long
BACKOFF_SECONDS = 1.0       # the first wait before trying again; it doubles each time, with jitter
BACKOFF_MAX_SECONDS = 30.0  # the longest wait

# Exception names that mean a timeout in HTTP libraries (httpx's ReadTimeout, say), matched by name
TIMEOUT_NAME_ENDINGS = ("Timeout", "TimeoutError", "TimeoutException")

# SQLite takes up to 32,766 values in one query; hashes are looked up this many at a time
LOOKUP_GROUP = 500


class EmbeddingError(RuntimeError):
    """Embedding failed and the run can't go on; the message says why and what to do."""


def utc_now() -> datetime:
    return datetime.now(UTC)


# -------------------------------------------------
# Which Errors Are Worth Another Try
# -------------------------------------------------

def _causes(error: BaseException) -> Iterator[BaseException]:
    """The error, then what caused it, and so on: LangChain wraps Google's own error."""
    seen = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _status(error: BaseException) -> int | None:
    """The HTTP status an exception carries, if any: Google's errors call it code; others, status_code."""
    for name in ("code", "status_code"):
        value = getattr(error, name, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    return None


def is_daily_quota(error: BaseException) -> bool:
    """A 429 for a quota that lasts the day ("... requests per day limit exceeded ..."): trying again won't help."""
    causes = list(_causes(error))
    text = " ".join(str(cause) for cause in causes).casefold()
    return any(_status(cause) == 429 for cause in causes) and ("per day" in text or "perday" in text)


def is_retryable(error: BaseException) -> bool:
    """A rate limit (429, but not the day's quota), a server error (5xx) or a timeout: another try may work."""
    for cause in _causes(error):
        if isinstance(cause, TimeoutError) or type(cause).__name__.endswith(TIMEOUT_NAME_ENDINGS):
            return True
        status = _status(cause)
        if status == 429:
            return not is_daily_quota(error)
        if status is not None and 500 <= status < 600:
            return True
    return False


# -------------------------------------------------
# The Model
# -------------------------------------------------

def make_embedding_model(*, provider: str, model: str, dimensions: int, timeout_seconds: float,
                         api_key: SecretStr | None) -> Embeddings:
    """
    The embedding model kb_settings.toml names. Building it makes no call.

    "google" is Gemini; its client is built with a timeout and no retries of its own, so ChunkEmbedder's retries are
    the only ones. "fake" is LangChain's DeterministicFakeEmbedding: vectors made from each text's hash, which mean
    nothing but let every step around them run with no key and no network.
    """
    if provider == "fake":
        return DeterministicFakeEmbedding(size=dimensions)
    if api_key is None:
        raise ValueError(f"The {provider} embedding model needs an API key")
    embeddings = GoogleGenerativeAIEmbeddings(model=model, api_key=api_key, output_dimensionality=dimensions)
    embeddings.client = genai.Client(api_key=api_key.get_secret_value(), http_options=HttpOptions(
        timeout=int(timeout_seconds * 1000), retry_options=HttpRetryOptions(attempts=1)))
    return embeddings


# -------------------------------------------------
# EmbeddingCache - Vectors on Disk
# -------------------------------------------------

class EmbeddingCache:
    """
    Vectors on disk, in SQLite: each kept by its model, its size and the hash of its text, with the date it was made.
    The same text with the same model is never embedded twice, and two models' vectors never mix.

    Step 1: Configure: the constructor stores the path and the model; nothing is opened
    Step 2: get() and put(), each opening the file for the call
    """

    def __init__(self, path: str | Path, *, model: str, dimensions: int):
        """
        Args:
            path: the SQLite file; it's made on the first put()
            model: the model's name, as "<provider>/<model>": part of each vector's key
            dimensions: the vectors' size: part of each vector's key
        """
        self.path = Path(path)
        self.model = model
        self.dimensions = dimensions

    def get(self, hashes: list[str]) -> dict[str, tuple[list[float], str]]:
        """{hash: (vector, the date it was made)} for each hash the cache holds for this model and size."""
        if not hashes or not self.path.exists():
            return {}
        found = {}
        with self._connection() as db:
            for start in range(0, len(hashes), LOOKUP_GROUP):
                group = hashes[start:start + LOOKUP_GROUP]
                rows = db.execute("SELECT text_hash, vector, embedded_at FROM vectors WHERE model = ? AND "
                                  f"dimensions = ? AND text_hash IN ({', '.join('?' * len(group))})",
                                  (self.model, self.dimensions, *group))
                found.update({text_hash: (json.loads(vector), when) for text_hash, vector, when in rows})
        return found

    def put(self, vectors: dict[str, list[float]], embedded_at: str) -> None:
        """Keep each new vector under its text's hash; all of them are written, or none."""
        with self._connection() as db, db:
            db.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?, ?, ?)",
                           [(self.model, self.dimensions, text_hash, json.dumps(vector), embedded_at)
                            for text_hash, vector in vectors.items()])

    def count(self) -> int:
        """How many vectors the cache holds for this model and size."""
        if not self.path.exists():
            return 0
        with self._connection() as db:
            return db.execute("SELECT COUNT(*) FROM vectors WHERE model = ? AND dimensions = ?",
                              (self.model, self.dimensions)).fetchone()[0]

    def _connection(self):
        """An open connection, closed when the `with` ends; any problem with the file becomes an EmbeddingError."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path)
            db.execute("CREATE TABLE IF NOT EXISTS vectors (model TEXT NOT NULL, dimensions INTEGER NOT NULL, "
                       "text_hash TEXT NOT NULL, vector TEXT NOT NULL, embedded_at TEXT NOT NULL, "
                       "PRIMARY KEY (model, dimensions, text_hash))")
            return _Guarded(closing(db), self.path)
        except (sqlite3.Error, OSError) as err:
            raise EmbeddingError(f"The embedding cache can't be used ({err}): {self.path.resolve()}. Delete it, and "
                                 "the next run embeds every chunk again.") from None


class _Guarded:
    """A `with` around a SQLite connection that turns a database error inside it into an EmbeddingError."""

    def __init__(self, closer, path: Path):
        self.closer, self.path = closer, path

    def __enter__(self) -> sqlite3.Connection:
        return self.closer.__enter__()

    def __exit__(self, kind, error, trace) -> None:
        self.closer.__exit__(kind, error, trace)
        if isinstance(error, (sqlite3.Error, json.JSONDecodeError)):          # a broken file, or a broken vector
            raise EmbeddingError(f"The embedding cache can't be used ({error}): {self.path.resolve()}. Delete it, "
                                 "and the next run embeds every chunk again.") from None


# -------------------------------------------------
# ChunkEmbedder Class - Chunks to Vectors
# -------------------------------------------------

@dataclass
class EmbedReport:
    """What embed() did: where each vector came from, the calls it took, and what the gate redacted."""
    chunks: int = 0
    from_cache: int = 0
    embedded: int = 0            # chunks whose vector the model made this run
    calls: int = 0               # tries, retries included
    retries: int = 0
    failed_calls: int = 0
    tokens: int = 0              # estimated tokens sent, retries included
    seconds: float = 0.0
    redacted: list[str] = field(default_factory=list)   # "<chunk_id>: <kind> <masked>", for each value the gate caught


class ChunkEmbedder:
    """
    Embeds chunks with any LangChain Embeddings model: through the gate, from the cache when it can, in batches, a
    few at once, each call timed out and retried as it should be.

    Step 1: Configure: the constructor stores the model, the cache and the limits; nothing is called
    Step 2: embed() (or aembed()) gives one vector per chunk; afterwards self.report says how they were made
    """

    def __init__(self, model: Embeddings, *, model_name: str, dimensions: int, cache: EmbeddingCache | None = None,
                 batch_size: int = BATCH_SIZE, batch_tokens: int = BATCH_TOKENS,
                 max_concurrency: int = MAX_CONCURRENCY, max_attempts: int = MAX_ATTEMPTS,
                 timeout_seconds: float = TIMEOUT_SECONDS, backoff_seconds: float = BACKOFF_SECONDS,
                 backoff_max_seconds: float = BACKOFF_MAX_SECONDS,
                 length_function: Callable[[str], int] = count_tokens,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep, rng: random.Random | None = None,
                 clock: Callable[[], datetime] = utc_now):
        """
        Args:
            model: any LangChain Embeddings model (make_embedding_model() builds the one kb_settings.toml names)
            model_name: "<provider>/<model>": recorded with every vector, and part of the cache's key
            dimensions: the size every vector must have
            cache: where vectors are kept between runs (None: every chunk is embedded)
            batch_size, batch_tokens: the most texts, and estimated tokens, in one call
            max_concurrency: how many calls may be waiting at once
            max_attempts, timeout_seconds, backoff_seconds, backoff_max_seconds: how each call is tried
            length_function: counts a text's tokens (default: count_tokens(), an estimate that errs high)
            sleep, rng, clock: how to wait, the jitter's randomness, and the time: tests pass their own
        """
        self.model = model
        self.model_name = model_name
        self.dimensions = dimensions
        self.cache = cache
        self.batch_size = batch_size
        self.batch_tokens = batch_tokens
        self.max_concurrency = max_concurrency
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds
        self.backoff_seconds = backoff_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.length_function = length_function
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.clock = clock
        self.report = EmbedReport()

    def embed(self, chunks: list[Document]) -> list[list[float]]:
        """One vector per chunk, in order. Each chunk's metadata gets embedding_model, embedding_dimensions and
        embedded_at (the date its vector was made).

        Raises:
            EmbeddingError: a call failed for good, the model gave back something unusable, or the cache can't be used
        """
        return asyncio.run(self.aembed(chunks))

    async def aembed(self, chunks: list[Document]) -> list[list[float]]:
        """embed(), for code that's already async."""
        started = time.perf_counter()
        self.report = report = EmbedReport(chunks=len(chunks))
        try:
            # Step 2a: The gate: nothing sensitive leaves the machine, whatever the chunk's source
            texts = []
            for chunk in chunks:
                text, findings = redact(chunk.page_content)
                report.redacted += [f"{chunk.metadata.get('chunk_id', '?')}: {found.kind} {found.masked}"
                                    for found in findings]
                texts.append(text)
            hashes = [short_hash(text) for text in texts]

            # Step 2b: The cache: a text embedded before, by this model at this size, isn't sent again
            known = self.cache.get(list(dict.fromkeys(hashes))) if self.cache else {}
            missing = dict.fromkeys(hash_ for hash_ in hashes if hash_ not in known)
            report.from_cache = sum(hash_ in known for hash_ in hashes)
            report.embedded = len(chunks) - report.from_cache

            # Step 2c: The rest, in batches, a few at once; each batch's vectors are cached as soon as they come
            text_of = dict(zip(hashes, texts, strict=True))
            batches = self._batches([(hash_, text_of[hash_]) for hash_ in missing])
            limit = asyncio.Semaphore(self.max_concurrency)
            when = self.clock().isoformat(timespec="seconds")

            async def run(batch: list[tuple[str, str]]) -> None:
                async with limit:
                    vectors = await self._embed_batch([text for _, text in batch])
                new = {hash_: vector for (hash_, _), vector in zip(batch, vectors, strict=True)}
                if self.cache:
                    self.cache.put(new, when)
                known.update({hash_: (vector, when) for hash_, vector in new.items()})

            await asyncio.gather(*(run(batch) for batch in batches))
        finally:
            report.seconds = time.perf_counter() - started

        # Step 2d: Each chunk's vector, labelled with the model, its size and when it was made
        for chunk, hash_ in zip(chunks, hashes, strict=True):
            chunk.metadata.update(embedding_model=self.model_name, embedding_dimensions=self.dimensions,
                                  embedded_at=known[hash_][1])
        logger.info("Embedded %d chunks: %d from the cache, %d by the model in %d call%s (%d retr%s), about %d "
                    "tokens, %.1f s", report.chunks, report.from_cache, report.embedded, report.calls,
                    "" if report.calls == 1 else "s", report.retries, "y" if report.retries == 1 else "ies",
                    report.tokens, report.seconds)
        return [known[hash_][0] for hash_ in hashes]

    def _batches(self, items: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
        """(hash, text) pairs grouped under batch_size texts and batch_tokens estimated tokens each; a text bigger
        than batch_tokens goes alone."""
        batches: list[list[tuple[str, str]]] = []
        tokens = 0
        for item in items:
            size = self.length_function(item[1])
            if not batches or len(batches[-1]) == self.batch_size or tokens + size > self.batch_tokens:
                batches.append([])
                tokens = 0
            batches[-1].append(item)
            tokens += size
        return batches

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """One batch's vectors: each try cut off after timeout_seconds; a retryable failure tried again after a
        wait that doubles each time, with jitter; anything else ends the run with why."""
        tokens = sum(map(self.length_function, texts))
        for attempt in range(1, self.max_attempts + 1):
            self.report.calls += 1
            self.report.tokens += tokens
            try:
                vectors = await asyncio.wait_for(self.model.aembed_documents(texts), self.timeout_seconds)
            except Exception as err:
                self.report.failed_calls += 1
                what = "a timeout" if isinstance(err, TimeoutError) else f"{type(err).__name__}: {err}"
                if is_daily_quota(err):
                    raise EmbeddingError(f"The embedding model's quota for today is used up ({what}). It comes back "
                                         "at midnight Pacific time; the vectors made so far are cached.") from err
                if not is_retryable(err) or attempt == self.max_attempts:
                    tries = f"{attempt} tr{'y' if attempt == 1 else 'ies'}"
                    raise EmbeddingError(f"Embedding failed after {tries} ({what}); the vectors made so far are "
                                         "cached") from err
                delay = self._backoff(attempt)
                self.report.retries += 1
                logger.warning("Embedding call failed (%s), try %d of %d: trying again in %.1f s",
                               what if len(what) <= 120 else what[:117] + "...", attempt, self.max_attempts, delay)
                await self.sleep(delay)
                continue
            self._check(texts, vectors)
            return [[float(value) for value in vector] for vector in vectors]    # plain floats, whatever the model's
        raise AssertionError("unreachable: the last try returns or raises")

    def _backoff(self, attempt: int) -> float:
        """The wait before try attempt + 1: backoff_seconds doubled per try, at most backoff_max_seconds, then
        "equal jitter" (half of it fixed, half random), so clients that failed together don't retry together."""
        ceiling = min(self.backoff_max_seconds, self.backoff_seconds * 2 ** (attempt - 1))
        return ceiling / 2 + self.rng.uniform(0, ceiling / 2)

    def _check(self, texts: list[str], vectors: list[list[float]]) -> None:
        """One vector per text, each of `dimensions` real numbers, or the run stops: a wrong vector is worse than
        none."""
        if len(vectors) != len(texts):
            raise EmbeddingError(f"The model gave back {len(vectors)} vectors for {len(texts)} texts")
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(f"The model gave back a vector of {len(vector)} numbers, not {self.dimensions}: "
                                     "the model or its size isn't what kb_settings.toml says")
            if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
                raise EmbeddingError("The model gave back a vector with a value that isn't a real number")
