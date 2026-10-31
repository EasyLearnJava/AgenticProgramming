"""
IT Knowledge Base: The Loader's Settings
========================================

Reads kb_settings.toml, which describes the knowledge base export and how its articles are cut, and checks it before
anything is loaded. It handles:
  1. KBSettings: which column holds each field, which fields are the Document's text and which its labels, what an
     ID is made from, and one spelling for each label value
  2. ChunkingSettings: the chunks' sizes, in tokens
  3. EmbeddingSettings: the embedding model, and how it's called: batches, concurrency, retries, the cache
  4. load_settings(): the file read and checked; a typo or a missing setting stops the run with one clear line

    load_settings(Path("kb_settings.toml"))  ->  KBSettings(text_fields=("title", ...), columns={"title": "title", ...})
"""
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

import embedding
from article import ARTICLE_FIELDS, REQUIRED_FIELDS, Priority, describe
from chunking import CHUNK_OVERLAP, CHUNK_SIZE, MAX_TOKENS, MIN_TOKENS
from utils import spelling_key

# Where the embedding cache is kept, from the settings file's folder (an absolute path is used as it is)
CACHE_FILE = Path("data") / "embedding_cache.sqlite3"

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


def load_settings(path: Path) -> KBSettings:
    """
    Read and check the settings file.

    Raises:
        FileNotFoundError: there's no file at path
        ValueError: it isn't valid TOML, or a setting is missing, unknown or wrong (the message says which)
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Settings file not found: {path}")
    try:
        with open(path, "rb") as file:
            return KBSettings.model_validate(tomllib.load(file))
    except tomllib.TOMLDecodeError as err:
        raise ValueError(f"Settings file isn't valid TOML ({err}): {path}") from None
    except ValidationError as err:
        raise ValueError(f"Settings file has a bad setting ({describe(err)}): {path}") from None
