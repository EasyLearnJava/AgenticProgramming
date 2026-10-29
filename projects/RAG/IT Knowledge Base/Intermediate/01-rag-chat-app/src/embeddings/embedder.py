"""
IT Knowledge Base: Embeddings
=============================

Turns texts into vectors with whichever embedding model config.yaml names, and checks what comes back. It handles:
  1. Building the provider's model from its settings: a timeout on each call, and a limited number of attempts
  2. Embedding the chunks in batches, and a question on its own (sync or async), each call timed in a span
  3. Checking the vectors: one per text, each with the number of dimensions config.yaml expects
  4. Turning any provider failure into an UpstreamError: a timeout, a rate limit, or anything else

To add a provider: write a builder like _google() and add it to BUILDERS; the rest of the app only sees LangChain's
Embeddings interface.

Usage:
    embedder = Embedder(create_embedding_model(settings.embeddings, api_key), dimensions=768, batch_size=100)
    embedder.embed_documents(texts)     ->  one vector per text, in order
    await embedder.aembed_query(text)   ->  one vector
"""
from collections.abc import Callable

from google import genai
from google.genai.types import HttpOptions, HttpRetryOptions
from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from pydantic import SecretStr

from src.config.settings import EmbeddingsSettings
from src.exceptions import UpstreamError, upstream_error
from src.observability.tracing import span

# -------------------------------------------------
# Providers
# -------------------------------------------------

def _google(settings: EmbeddingsSettings, api_key: SecretStr) -> Embeddings:
    """Gemini's embedding model, with a timeout and retries on each call."""
    model = GoogleGenerativeAIEmbeddings(model=settings.model, api_key=api_key,
                                         output_dimensionality=settings.dimensions)
    # LangChain's class has no timeout or retry settings, so its Google client is replaced by one that has them:
    # each attempt is cut off after timeout_seconds, and a timeout, a 429 or a 5xx is tried again, up to max_attempts
    model.client = genai.Client(api_key=api_key.get_secret_value(), http_options=HttpOptions(
        timeout=int(settings.timeout_seconds * 1000), retry_options=HttpRetryOptions(attempts=settings.max_attempts)))
    return model


BUILDERS: dict[str, Callable[[EmbeddingsSettings, SecretStr], Embeddings]] = {"google": _google}


def create_embedding_model(settings: EmbeddingsSettings, api_key: SecretStr) -> Embeddings:
    """The embedding model config.yaml names. Building it makes no call to the provider."""
    return BUILDERS[settings.provider](settings, api_key)


# -------------------------------------------------
# Embedder Class - Embeds and Checks
# -------------------------------------------------

class Embedder:
    """
    Embeds texts with any LangChain Embeddings model: in batches, timed, each result checked.

    Step 1: Configure: the constructor stores the model and the sizes; no call is made
    Step 2: Embed: embed_documents() for the chunks, embed_query() or aembed_query() for a question
    """

    def __init__(self, model: Embeddings, *, dimensions: int, batch_size: int):
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        # Gemini's models know their name (.model); a stand-in goes by its class name
        self.model_name: str = getattr(model, "model", type(model).__name__)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in order, batch_size texts per call. Raises UpstreamError."""
        with span("embeddings.embed_documents", model=self.model_name, texts=len(texts)) as fields:
            vectors: list[list[float]] = []
            batches = [texts[start:start + self.batch_size] for start in range(0, len(texts), self.batch_size)]
            for batch in batches:
                try:
                    vectors.extend(self.model.embed_documents(batch))
                except Exception as err:
                    raise upstream_error("embeddings", err) from err
            self._check(vectors, len(texts))
            fields["batches"] = len(batches)
            return vectors

    def embed_query(self, text: str) -> list[float]:
        """One question's vector. Raises UpstreamError."""
        with span("embeddings.embed_query", model=self.model_name):
            try:
                vector = self.model.embed_query(text)
            except Exception as err:
                raise upstream_error("embeddings", err) from err
            self._check([vector], 1)
            return vector

    async def aembed_query(self, text: str) -> list[float]:
        """The same, for async code: the server can do other work while the provider answers."""
        with span("embeddings.embed_query", model=self.model_name):
            try:
                vector = await self.model.aembed_query(text)
            except Exception as err:
                raise upstream_error("embeddings", err) from err
            self._check([vector], 1)
            return vector

    def _check(self, vectors: list[list[float]], expected: int) -> None:
        """One vector per text, each `dimensions` numbers long; a vector of another size couldn't be stored."""
        if len(vectors) != expected:
            raise UpstreamError("embeddings", f"{expected} texts were sent, but {len(vectors)} vectors came back")
        wrong = {len(vector) for vector in vectors} - {self.dimensions}
        if wrong:
            raise UpstreamError("embeddings", f"vectors of {', '.join(map(str, sorted(wrong)))} numbers came back, "
                                              f"but embeddings.dimensions in config.yaml is {self.dimensions}")
