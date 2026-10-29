"""
IT Knowledge Base: Settings
===========================

Every setting the app runs with, read from config.yaml and checked before anything else runs; and the API key, the
one secret, from the environment or .env, never from config.yaml. It handles:
  1. One typed section per layer, named like its package (observability's are logging and tracing): a typo, a
     missing value or a value out of range stops the start, with a message naming each bad setting
  2. Paths in config.yaml found from the file's own folder, whichever folder the app is started from
  3. The API key as a secret value: printing or logging it shows **********

Usage:
    settings = load_settings()      ->  Settings, or ConfigError listing every problem in config.yaml
    api_key = load_api_key()        ->  SecretStr, or ConfigError saying how to set the key (never what it is)
"""
import codecs
import os
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from src.exceptions import ConfigError

# -------------------------------------------------
# Configuration
# -------------------------------------------------

# The project folder: this file is src/config/settings.py
PROJECT_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_DIR / "config.yaml"
ENV_FILE = PROJECT_DIR / ".env"                 # in .gitignore: the real key never goes into git

API_KEY_VARIABLE = "GOOGLE_API_KEY"
PLACEHOLDER = "your-key-here"                   # what .env.example says, before you put your real key in


# -------------------------------------------------
# The Sections of config.yaml
# -------------------------------------------------

def _from_config_folder(path: Path | None, info: ValidationInfo) -> Path | None:
    """A relative path, made full from the config file's folder (handed in by load_settings())."""
    base_dir = (info.context or {}).get("base_dir")
    if path is None or path.is_absolute() or base_dir is None:
        return path
    return (base_dir / path).resolve()


ConfigPath = Annotated[Path, AfterValidator(_from_config_folder)]


class Section(BaseModel):
    """A part of config.yaml: every key it has must be known (a typo is an error), and nothing can change it later."""
    model_config = ConfigDict(extra="forbid", frozen=True)


class AppSettings(Section):
    name: str
    sample_questions: list[str] = Field(min_length=1)


class IngestionSettings(Section):
    path: ConfigPath
    encoding: str
    text_columns: list[str] = Field(min_length=1)
    metadata_columns: list[str]
    required_columns: list[str]

    @field_validator("encoding")
    @classmethod
    def _known_encoding(cls, encoding: str) -> str:
        try:
            codecs.lookup(encoding)
        except LookupError:
            raise ValueError(f"{encoding!r} isn't an encoding Python knows, such as utf-8 or utf-16") from None
        return encoding

    @model_validator(mode="after")
    def _check_columns(self):
        unknown = [name for name in self.required_columns if name not in self.text_columns + self.metadata_columns]
        if unknown:
            raise ValueError(f"required_columns names columns that aren't read: {', '.join(unknown)}")
        if "title" not in self.metadata_columns:
            raise ValueError("metadata_columns must include title: each answer's sources are named by it")
        return self


class ChunkingSettings(Section):
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_overlap(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap ({self.chunk_overlap}) must be less than chunk_size ({self.chunk_size})")
        return self


class EmbeddingsSettings(Section):
    provider: Literal["google"]
    model: str
    dimensions: int = Field(gt=0)
    batch_size: int = Field(ge=1, le=100)        # Gemini takes at most 100 texts per call
    timeout_seconds: float = Field(gt=0)
    max_attempts: int = Field(ge=1, le=10)


class VectorDBSettings(Section):
    provider: Literal["qdrant"]
    location: Literal[":memory:"]
    collection: str = Field(pattern=r"^[A-Za-z0-9_-]+$")


class RetrievalSettings(Section):
    top_k: int = Field(ge=1, le=50)


class LLMSettings(Section):
    provider: Literal["google"]
    model: str
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_attempts: int = Field(ge=1, le=10)


class PipelineSettings(Section):
    max_sources: int = Field(ge=1)
    snippet_length: int = Field(ge=1)


class APISettings(Section):
    host: str
    port: int = Field(ge=1, le=65535)
    request_timeout_seconds: float = Field(gt=0)


class LoggingSettings(Section):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    console_format: Literal["text", "json"]
    file: ConfigPath | None                      # null: no log file
    max_bytes: int = Field(gt=0)
    backup_count: int = Field(ge=0)


class TracingSettings(Section):
    enabled: bool
    max_traces: int = Field(ge=1, le=10_000)


class Settings(Section):
    """Every setting, one section per layer."""
    app: AppSettings
    ingestion: IngestionSettings
    chunking: ChunkingSettings
    embeddings: EmbeddingsSettings
    vectordb: VectorDBSettings
    retrieval: RetrievalSettings
    llm: LLMSettings
    pipeline: PipelineSettings
    api: APISettings
    logging: LoggingSettings
    tracing: TracingSettings


# -------------------------------------------------
# Loading
# -------------------------------------------------

def load_settings(path: str | Path = CONFIG_FILE) -> Settings:
    """
    Read and check config.yaml.

    Raises:
        ConfigError: the file is missing or isn't YAML, or a setting is unknown, missing or out of range (each one
            is listed)
    """
    path = Path(path).resolve()
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except (UnicodeDecodeError, yaml.YAMLError) as err:
        raise ConfigError(f"Config file isn't valid YAML in UTF-8: {path}: {err}") from None
    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must hold sections such as app: and ingestion:, not {type(raw).__name__}: "
                          f"{path}")
    try:
        return Settings.model_validate(raw, context={"base_dir": path.parent})
    except ValidationError as err:
        problems = "; ".join(f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
                             for problem in err.errors())
        raise ConfigError(f"Config file has {err.error_count()} bad setting(s): {problems} ({path})") from None


def load_api_key(env_file: Path = ENV_FILE) -> SecretStr:
    """
    The API key, from the environment or the .env file. A key already in the environment wins over the file.

    Raises:
        ConfigError: there's no key, it's still the placeholder, or .env isn't UTF-8 text
    """
    try:
        load_dotenv(env_file)
    except UnicodeDecodeError:
        # PowerShell 5's `echo ... > .env` saves the file as UTF-16, which can't be read
        raise ConfigError(f"{env_file.name} isn't saved as UTF-8 text. Open it in an editor and save it with UTF-8 "
                          "encoding.") from None
    key = os.getenv(API_KEY_VARIABLE, "").strip()
    if not key:
        raise ConfigError(f"{API_KEY_VARIABLE} is not set. Copy .env.example to .env and put your key after the =, "
                          f"or set {API_KEY_VARIABLE} as an environment variable (in Codespaces: a Codespaces secret).")
    if key == PLACEHOLDER:
        raise ConfigError(f"{API_KEY_VARIABLE} is still the placeholder from .env.example: put your real key in .env.")
    return SecretStr(key)
