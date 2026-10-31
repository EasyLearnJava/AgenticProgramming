"""
A stand-in embedding service for the tests: it can be told to rate-limit, fail or be slow, call by call, and it
records what it was sent, so every path of embedding.py is tested with no key and no network.

    ScriptedEmbeddings(script=[rate_limit(), None])   ->  the 1st call answers 429, the 2nd answers
"""
import asyncio
import hashlib

from google.genai import errors
from langchain_core.embeddings import Embeddings


def google_error(code: int, message: str = "An error from Google.", status: str = "ERROR") -> errors.APIError:
    """Google's own error for an HTTP status, as its client raises it."""
    error_class = errors.ClientError if code < 500 else errors.ServerError
    return error_class(code, {"error": {"code": code, "message": message, "status": status}})


def rate_limit() -> errors.APIError:
    return google_error(429, "Quota exceeded for metric: embed_content_free_tier_requests, limit: 100, "
                             "description: Embed content requests per minute.", "RESOURCE_EXHAUSTED")


def daily_quota() -> errors.APIError:
    return google_error(429, "Quota exceeded for metric: embed_content_free_tier_requests, limit: 1000, "
                             "description: Embed content requests per day limit exceeded on Free Tier.",
                        "RESOURCE_EXHAUSTED")


class ScriptedEmbeddings(Embeddings):
    """
    Each call takes its outcome from the script, in order: None answers, an exception is raised, "slow" answers
    after `delay` seconds (past a short timeout), "short" answers with vectors one number short. Past the end of the
    script, every call answers. Each answer is made from the text's hash, so the same text gets the same vector.
    """

    def __init__(self, dimensions: int = 8, script: list | None = None, delay: float = 0.0):
        self.dimensions = dimensions
        self.script = list(script or [])
        self.delay = delay
        self.calls: list[list[str]] = []     # the texts sent, call by call
        self.in_flight = 0
        self.most_in_flight = 0              # the most calls waiting at once

    def vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [byte / 255 for byte in (digest * (self.dimensions // 32 + 1))[:self.dimensions]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return asyncio.run(self.aembed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        outcome = self.script.pop(0) if self.script else None
        self.in_flight += 1
        self.most_in_flight = max(self.most_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay if outcome == "slow" else 0.01)
        finally:
            self.in_flight -= 1
        if isinstance(outcome, BaseException):
            raise outcome
        vectors = [self.vector(text) for text in texts]
        return [vector[:-1] for vector in vectors] if outcome == "short" else vectors
