"""Read local configuration without exposing secrets in logs or run state."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINTS = ROOT / ".rivalscope" / "runs.sqlite3"


@dataclass(frozen=True)
class Settings:
    default_mode: str = "demo"
    model: str = "openai/gpt-oss-120b"
    tavily_key: str = field(default="", repr=False)
    nebius_key: str = field(default="", repr=False)

    @classmethod
    def load(cls) -> "Settings":
        file = dotenv_values(ROOT / ".env")

        def value(name: str, default: str = "") -> str:
            return (os.environ.get(name, file.get(name, default)) or "").strip()

        mode = value("RIVALSCOPE_MODE", "demo")
        return cls(
            default_mode=mode if mode in {"demo", "live"} else "demo",
            model=value("NEBIUS_MODEL") or cls.model,
            tavily_key=value("TAVILY_API_KEY"),
            nebius_key=value("NEBIUS_API_KEY"),
        )

    @property
    def missing_keys(self) -> list[str]:
        return [
            name for name, key in (
                ("TAVILY_API_KEY", self.tavily_key),
                ("NEBIUS_API_KEY", self.nebius_key),
            ) if not key
        ]
