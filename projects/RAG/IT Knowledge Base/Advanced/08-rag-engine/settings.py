"""
IT Knowledge Base: The Loader's Settings
========================================

Reads kb_settings.toml, which describes the knowledge base export and how its articles are cut, and checks it before
anything is loaded. It handles:
  1. KBSettings: which column holds each field, which fields are the Document's text and which its labels, what an
     ID is made from, and one spelling for each label value
  2. ChunkingSettings: the chunks' sizes, in tokens
  3. EmbeddingSettings: the embedding model, and how it's called: batches, concurrency, retries, the cache
  4. VectorStoreSettings: where Qdrant is, the alias, and the HNSW index's settings
  5. RetrievalSettings: how a question is searched: dense, sparse or hybrid, how many, the threshold, re-ranking
  6. AnswerSettings: the chat model, the prompt file, the context's token budget, the "not covered" reply, the judge
  7. load_settings(): the file read and checked; a typo or a missing setting stops the run with one clear line

    load_settings(Path("kb_settings.toml"))  ->  KBSettings(text_fields=("title", ...), columns={"title": "title", ...})
"""
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import answering
import embedding
import rag_engine
import retriever
import vector_store
from article import ARTICLE_FIELDS, REQUIRED_FIELDS, Priority, describe
from chunking import CHUNK_OVERLAP, CHUNK_SIZE, MAX_TOKENS, MIN_TOKENS
from utils import spelling_key

# Where the embedding cache is kept, from the settings file's folder (an absolute path is used as it is)
CACHE_FILE = Path("data") / "embedding_cache.sqlite3"

# An environment variable that starts with this sets a setting: KB__ENGINE__QUESTION_TIMEOUT_SECONDS=20
ENV_PREFIX = "KB__"

# Fields an ID can be made from, and labels that can have a table of spellings: those holding one piece of text
TEXT_LIKE_FIELDS = tuple(name for name in ARTICLE_FIELDS if name not in ("id", "tags"))


class ChunkingSettings(BaseModel):
    """The chunks' sizes, in tokens; a setting left out of kb_settings.toml keeps chunking.py's default."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_size: int = Field(default=CHUNK_SIZE, gt=0)
    chunk_overlap: int = Field(default=CHUNK_OVERLAP, ge=0)
    min_tokens: int = Field(default=MIN_TOKENS, gt=0)
    max_tokens: int = Field(default=MAX_TOKENS, gt=0)

    @model_validator(mode="after")
    def _check(self) -> "ChunkingSettings":
        if not self.chunk_overlap < self.chunk_size or not self.min_tokens < self.chunk_size \
                or self.chunk_size + self.min_tokens > self.max_tokens:
            raise ValueError("chunking: the sizes must keep chunk_overlap and min_tokens below chunk_size, and "
                             "chunk_size + min_tokens <= max_tokens")
        return self


class EmbeddingSettings(BaseModel):
    """The embedding model and how it's called; a setting left out keeps embedding.py's default."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["google", "fake"] = embedding.PROVIDER
    model: str = Field(default=embedding.MODEL, min_length=1)
    dimensions: int = Field(default=embedding.DIMENSIONS, gt=0, le=3072)
    batch_size: int = Field(default=embedding.BATCH_SIZE, gt=0, le=100)          # Gemini takes up to 100 a call
    batch_tokens: int = Field(default=embedding.BATCH_TOKENS, gt=0)
    max_concurrency: int = Field(default=embedding.MAX_CONCURRENCY, gt=0, le=16)
    max_attempts: int = Field(default=embedding.MAX_ATTEMPTS, gt=0, le=10)
    timeout_seconds: float = Field(default=embedding.TIMEOUT_SECONDS, gt=0)
    backoff_seconds: float = Field(default=embedding.BACKOFF_SECONDS, ge=0)
    backoff_max_seconds: float = Field(default=embedding.BACKOFF_MAX_SECONDS, ge=0)
    cache_path: Path = CACHE_FILE

    @property
    def model_name(self) -> str:
        """"<provider>/<model>": recorded with every vector and part of the cache's key, so a stand-in's vectors are
        never taken for Gemini's."""
        return f"{self.provider}/{self.model}"


class VectorStoreSettings(BaseModel):
    """Where Qdrant is and how the collection is set up; a setting left out keeps vector_store.py's default. A
    server's API key never goes here: it's QDRANT_API_KEY, in .env or the environment."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    location: str = Field(default=vector_store.LOCATION, min_length=1)    # a folder, ":memory:" or an http(s) URL
    alias: str = Field(default=vector_store.ALIAS, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    hnsw_m: int = Field(default=vector_store.HNSW_M, gt=0)
    hnsw_ef_construct: int = Field(default=vector_store.HNSW_EF_CONSTRUCT, gt=0)


class RetrievalSettings(BaseModel):
    """How a question is searched; a setting left out keeps retriever.py's default."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["dense", "sparse", "hybrid"] = retriever.MODE
    k: int = Field(default=retriever.K, gt=0, le=50)
    candidates: int = Field(default=retriever.CANDIDATES, gt=0, le=200)
    rrf_k: int = Field(default=retriever.RRF_K, ge=0)
    min_score: float = Field(default=retriever.MIN_SCORE, ge=-1, le=1)
    max_per_article: int = Field(default=retriever.MAX_PER_ARTICLE, gt=0)
    mmr_lambda: float = Field(default=retriever.MMR_LAMBDA, ge=0, le=1)
    read_filters: bool = retriever.READ_FILTERS
    reranker: Literal["none", "word-overlap", "cross-encoder"] = "none"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    @model_validator(mode="after")
    def _check(self) -> "RetrievalSettings":
        if self.candidates < self.k:
            raise ValueError(f"retrieval: candidates ({self.candidates}) must be at least k ({self.k})")
        return self


class AnswerSettings(BaseModel):
    """The chat model and how an answer is made; a setting left out keeps answering.py's default."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["google", "fake"] = "google"
    model: str = Field(default="gemini-3.5-flash-lite", min_length=1)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=512, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_attempts: int = Field(default=3, gt=0, le=10)
    prompt_file: Path = Path("prompts") / "answer-v1.txt"     # from the settings file's folder
    max_context_tokens: int = Field(default=answering.MAX_CONTEXT_TOKENS, gt=0)
    not_covered: str = Field(default=answering.NOT_COVERED, min_length=1)
    judge: bool = False                                         # a second call that checks faithfulness
    condense_prompt_file: Path = Path("prompts") / "condense-v1.txt"   # rewrites a follow-up into a question

    @property
    def model_name(self) -> str:
        return f"{self.provider}/{self.model}"


class EngineSettings(BaseModel):
    """How the engine guards, caches and remembers; a setting left out keeps rag_engine.py's default."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    question_timeout_seconds: float = Field(default=rag_engine.QUESTION_TIMEOUT_SECONDS, gt=0)
    breaker_failures: int = Field(default=rag_engine.BREAKER_FAILURES, gt=0)
    breaker_reset_seconds: float = Field(default=rag_engine.BREAKER_RESET_SECONDS, ge=0)
    cache: bool = True
    cache_path: Path = Path("data") / "answer_cache.sqlite3"   # from the settings file's folder
    cache_ttl_seconds: float = Field(default=rag_engine.CACHE_TTL_SECONDS, gt=0)
    semantic_threshold: float = Field(default=rag_engine.SEMANTIC_THRESHOLD, ge=0, le=1)
    memory_turns: int = Field(default=rag_engine.MEMORY_TURNS, ge=0)
    input_price_per_million: float = Field(default=0.0, ge=0)    # dollars, from the model's price list
    output_price_per_million: float = Field(default=0.0, ge=0)


class KBSettings(BaseModel):
    """What the knowledge base export holds, and how its articles become Documents."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    text_fields: tuple[str, ...]                        # the Document's text (page_content), in this order
    label_fields: tuple[str, ...]                       # the Document's labels (metadata)
    id_fields: tuple[str, ...]                          # what an ID is made from when the export has no id column
    columns: dict[str, str]                             # each field -> the export's column that holds it
    spellings: dict[str, dict[str, list[str]]] = {}     # a label -> {right spelling: [other spellings]}
    chunking: ChunkingSettings = ChunkingSettings()     # the chunks' sizes
    embeddings: EmbeddingSettings = EmbeddingSettings() # the embedding model and how it's called
    vectorstore: VectorStoreSettings = VectorStoreSettings()   # where the points are kept
    retrieval: RetrievalSettings = RetrievalSettings()         # how a question is searched
    answer: AnswerSettings = AnswerSettings()                  # how it's answered
    engine: EngineSettings = EngineSettings()                  # how the engine guards, caches and remembers

    @model_validator(mode="after")
    def _check(self) -> "KBSettings":
        """Every name is a field an article has, the required fields have a column, and no spelling is ambiguous."""
        for setting, names in [("text_fields", self.text_fields), ("label_fields", self.label_fields),
                               ("id_fields", self.id_fields), ("columns", tuple(self.columns)),
                               ("spellings", tuple(self.spellings))]:
            unknown = [name for name in names if name not in ARTICLE_FIELDS]
            if unknown:
                raise ValueError(f"{setting} names a field an article doesn't have ({', '.join(unknown)}); "
                                 f"the fields are {', '.join(ARTICLE_FIELDS)}")
        missing = [name for name in REQUIRED_FIELDS if name not in self.columns]
        if missing:
            raise ValueError(f"columns gives no column for a required field ({', '.join(missing)})")
        shared = sorted({column for column in self.columns.values() if list(self.columns.values()).count(column) > 1})
        if shared:
            raise ValueError(f"columns reads two fields from one column ({', '.join(shared)})")
        if not self.id_fields or any(name not in TEXT_LIKE_FIELDS for name in self.id_fields):
            raise ValueError(f"id_fields must name one or more of {', '.join(TEXT_LIKE_FIELDS)}")
        for label, table in self.spellings.items():
            if label not in TEXT_LIKE_FIELDS:
                raise ValueError(f"spellings.{label}: only {', '.join(TEXT_LIKE_FIELDS)} can have spellings")
            if label == "priority" and set(table) - set(Priority):
                raise ValueError(f"spellings.priority: a right spelling must be one of {', '.join(Priority)}")
            claimed: dict[str, str] = {}
            for right, others in table.items():
                for spelling in (right, *others):
                    key = spelling_key(spelling)
                    if claimed.setdefault(key, right) != right:
                        raise ValueError(f'spellings.{label}: "{spelling}" is a spelling of both "{claimed[key]}" '
                                         f'and "{right}"')
        return self


def apply_environment(data: dict, environ: Mapping[str, str]) -> list[str]:
    """
    Put each KB__<TABLE>__<SETTING> variable of the environment over the file's setting, as TOML (a number, true,
    "text") or else as text: KB__ENGINE__QUESTION_TIMEOUT_SECONDS=20 sets [engine] question_timeout_seconds. Returns
    the variables used.
    """
    used = []
    for name, raw in sorted(environ.items()):
        if not name.upper().startswith(ENV_PREFIX) or len(name) == len(ENV_PREFIX):
            continue
        *tables, setting = name[len(ENV_PREFIX):].lower().split("__")
        try:
            value = tomllib.loads(f"value = {raw}")["value"]
        except tomllib.TOMLDecodeError:
            value = raw
        place = data
        for table in tables:
            place = place.setdefault(table, {})
            if not isinstance(place, dict):
                raise ValueError(f"{name} names a setting inside {table}, which isn't a table")
        place[setting] = value
        used.append(name)
    return used


def load_settings(path: Path, environ: Mapping[str, str] | None = None) -> KBSettings:
    """
    Read and check the settings file, with any KB__ variables of the environment over it (os.environ by default).

    Raises:
        FileNotFoundError: there's no file at path
        ValueError: it isn't valid TOML, or a setting is missing, unknown or wrong (the message says which, and the
                    environment variables used)
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Settings file not found: {path}")
    used: list[str] = []
    try:
        with open(path, "rb") as file:
            data = tomllib.load(file)
        used = apply_environment(data, os.environ if environ is None else environ)
        return KBSettings.model_validate(data)
    except tomllib.TOMLDecodeError as err:
        raise ValueError(f"Settings file isn't valid TOML ({err}): {path}") from None
    except ValidationError as err:
        from_environment = f"; from the environment: {', '.join(used)}" if used else ""
        raise ValueError(f"Settings file has a bad setting ({describe(err)}{from_environment}): {path}") from None
