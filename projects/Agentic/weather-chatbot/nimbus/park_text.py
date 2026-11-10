"""Public park text identity and tokenizer budgets; no model weights, inference, or provider credentials."""

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Final, Protocol

from nimbus.park_models import ParkChunk

MINILM_MODEL: Final = "sentence-transformers/all-minilm-l6-v2"
MINILM_DIMENSIONS: Final = 384
MINILM_MAX_TOKENS: Final = 256
TOKENIZER_SHA256: Final = "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"


class TokenCounter(Protocol):
    """The preparation-time capability required to prevent hosted encoder truncation."""

    def token_count(self, text: str) -> int:
        """Count the full input, including special tokens, without truncating it."""
        ...


def to_embedding_text(title: str, section: str, text: str) -> str:
    """The identical title/section/body input for preparation and hosted dense embedding."""
    return f"{title}\n{section}\n{text}"


def record_hash(chunk: ParkChunk | Mapping[str, Any]) -> str:
    """Hash every validated passage field, including text and provenance, in canonical key order."""
    item = chunk if isinstance(chunk, ParkChunk) else ParkChunk.model_validate(chunk)
    canonical = json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def split_for_tokens(text: str, prefix: str, counter: TokenCounter) -> list[str]:
    """Preserve sentences where possible, reserving heading tokens and overlapping oversized sentences."""
    units = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    output: list[str] = []
    current = ""
    # ① Keep complete sentences and their qualifiers whenever the full hosted input fits.
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()
        if counter.token_count(f"{prefix}\n{candidate}") <= MINILM_MAX_TOKENS:
            current = candidate
            continue
        if current:
            output.append(current)
            current = ""
        if counter.token_count(f"{prefix}\n{unit}") <= MINILM_MAX_TOKENS:
            current = unit
            continue
        # ② An unusually long sentence keeps overlapping context; no word silently disappears.
        words = unit.split()
        offset = 0
        while offset < len(words):
            end = offset
            while (
                end < len(words)
                and counter.token_count(f"{prefix}\n{' '.join(words[offset : end + 1])}") <= MINILM_MAX_TOKENS
            ):
                end += 1
            if end == offset:
                raise ValueError("Passage heading or individual word exceeds MiniLM's input budget")
            output.append(" ".join(words[offset:end]))
            offset = end if end == len(words) else max(offset + 1, end - 12)
    if current:
        output.append(current)
    return output
