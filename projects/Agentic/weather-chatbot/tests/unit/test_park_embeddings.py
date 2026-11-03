"""MiniLM's CPU configuration, real input budget, and identical document/query embedding representation."""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nimbus.park_embeddings import MiniLMEmbeddings, split_for_encoder, to_embedding_text


class Tokenizer:
    """A deterministic tokenizer that includes two special tokens."""

    def encode(self, text: str, **_kwargs: Any) -> list[int]:
        """One token per word plus the encoder boundary tokens."""
        return [1] * (len(text.split()) + 2)


def test_model_runs_on_cpu_with_pinned_offline_weights(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    class Model:
        """Record the model's configuration and normalized embedding request."""

        def __init__(self, name: str, **kwargs: Any) -> None:
            """Capture construction without importing or downloading external model weights."""
            calls.append({"name": name, **kwargs})
            self.tokenizer = Tokenizer()
            self.max_seq_length = 0

        def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
            """Give one known vector per input, checking inference settings."""
            assert kwargs["normalize_embeddings"] is True
            assert kwargs["show_progress_bar"] is False
            return [[1.0] + [0.0] * 383 for _ in texts]

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=Model))
    encoder = MiniLMEmbeddings(tmp_path, "a" * 40)
    assert calls == []
    assert len(encoder.encode(["Warm clothing"])[0]) == 384
    assert asyncio.run(encoder.embed_query("clothing"))[0] == 1
    assert len(calls) == 1
    assert calls[0]["name"] == "all-MiniLM-L6-v2"
    assert calls[0]["device"] == "cpu"
    assert calls[0]["local_files_only"] is True
    assert calls[0]["trust_remote_code"] is False
    assert calls[0]["revision"] == "a" * 40
    with pytest.raises(ValueError, match="tokenizer limit"):
        encoder.encode(["word " * 256])


def test_token_splitting_reserves_heading_budget_and_retains_sentence_context(tmp_path: Path) -> None:
    encoder = MiniLMEmbeddings(tmp_path, "a" * 40)
    encoder._model = SimpleNamespace(tokenizer=Tokenizer())
    sentence = "Carry layers with waterproof bags unless the ranger advises otherwise."
    text = " ".join([sentence] * 50)
    pieces = split_for_encoder(text, "Narrows Safety\nYear-Round", encoder)
    assert len(pieces) > 1
    assert all(encoder.token_count(f"Narrows Safety\nYear-Round\n{piece}") <= 256 for piece in pieces)
    assert " ".join(pieces).replace("\n", " ").split() == text.split()
    assert all(piece.endswith("otherwise.") for piece in pieces)
    assert to_embedding_text("Title", "Section", "Content") == "Title\nSection\nContent"


def test_oversized_sentence_gets_overlapping_bounded_windows(tmp_path: Path) -> None:
    encoder = MiniLMEmbeddings(tmp_path, "a" * 40)
    encoder._model = SimpleNamespace(tokenizer=Tokenizer())
    words = [f"word{number}" for number in range(600)]
    pieces = split_for_encoder(" ".join(words), "Heading", encoder)
    assert len(pieces) == 3
    assert all(encoder.token_count(f"Heading\n{piece}") <= 256 for piece in pieces)
    assert pieces[0].split()[-12:] == pieces[1].split()[:12]
    assert set(" ".join(pieces).split()) == set(words)
