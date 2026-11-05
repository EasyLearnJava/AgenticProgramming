"""All configuration lives here; paths do not depend on your terminal directory."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
# Ship the tokenizer vocabulary so extractive mode also works on an offline PC.
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(ROOT / "data" / "tokenizer"))


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    mode: str = "extractive"
    chat_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 500
    chunk_overlap: int = 75
    candidates: int = 16
    top_k: int = 5
    latency_target: float = 10
    freshness_days: int = 7

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def db(self) -> Path:
        return self.data / "index" / "policylens.sqlite3"

    @property
    def embedding_identity(self) -> str:
        # Different models must never query vectors created by another model.
        return f"openai:{self.embedding_model}" if self.mode == "openai" else "local-hash-v3:768"

    @property
    def index_identity(self) -> str:
        return f"{self.embedding_identity}:{self.chunk_size}:{self.chunk_overlap}:source-spans-v2"


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    settings = Settings(
        mode=os.getenv("RAG_MODE", "extractive").lower(),
        chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "75")),
        candidates=int(os.getenv("RETRIEVAL_CANDIDATES", "16")),
        top_k=int(os.getenv("RETRIEVAL_TOP_K", "5")),
        latency_target=float(os.getenv("LATENCY_TARGET_SECONDS", "10")),
        freshness_days=int(os.getenv("FRESHNESS_DAYS", "7")),
    )
    if settings.mode not in {"extractive", "openai"}:
        raise ValueError("RAG_MODE must be extractive or openai.")
    if not 64 <= settings.chunk_size <= 2000 or not 0 <= settings.chunk_overlap < settings.chunk_size:
        raise ValueError("Use CHUNK_SIZE 64–2000 and CHUNK_OVERLAP smaller than CHUNK_SIZE.")
    if not 1 <= settings.top_k <= settings.candidates <= 100:
        raise ValueError("Use 1 <= RETRIEVAL_TOP_K <= RETRIEVAL_CANDIDATES <= 100.")
    if settings.latency_target <= 0 or settings.freshness_days < 1:
        raise ValueError("Latency target and freshness days must be positive.")
    if settings.mode == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in .env to use RAG_MODE=openai, or use extractive mode.")
    return settings

