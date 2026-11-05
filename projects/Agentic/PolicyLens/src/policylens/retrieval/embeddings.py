"""Swap embedding providers here without changing ingestion or retrieval."""

import hashlib
import math
from collections import Counter

import numpy as np
from langchain_core.embeddings import Embeddings

from policylens.config import Settings
from policylens.network import create_http_client
from policylens.text import tokens
from policylens.grounding import terms


class LocalHashEmbeddings(Embeddings):
    """Deterministic lexical vectors for the key-free preview, NOT semantic embeddings.

    Hashing avoids a model download and never sends documents over the network.
    Collisions and synonyms limit quality; use the OpenAI adapter for neural RAG.
    """

    dimensions = 768

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        meaningful = terms(text)
        for token, count in Counter(t for t in tokens(text) if t in meaningful).items():
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            vector[index] += (1 if digest[4] % 2 else -1) * (1 + math.log(count))
        length = np.linalg.norm(vector)
        return (vector / length if length else vector).tolist()


def make_embeddings(settings: Settings) -> Embeddings:
    if settings.mode == "extractive":
        return LocalHashEmbeddings()
    from langchain_openai import OpenAIEmbeddings

    # Respect the operating system's trusted roots, including enterprise proxies.
    return OpenAIEmbeddings(model=settings.embedding_model, request_timeout=30, max_retries=1,
                            http_client=create_http_client())

