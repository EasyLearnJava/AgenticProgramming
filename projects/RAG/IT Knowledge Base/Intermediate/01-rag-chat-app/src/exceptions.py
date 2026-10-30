"""
IT Knowledge Base: Errors
=========================

Every error the app raises on purpose, in one hierarchy. Each has a stable code, the HTTP status the API answers
with, a message that's safe to show a caller, and whether trying again may work; the detail (str(error)) is for the
log only. It handles:
  1. AppError, the base class, and one subclass per kind of failure
  2. upstream_error(): any model provider's exception turned into the right UpstreamError, whichever provider
     (Gemini, or another LangChain integration) raised it

    AppError                    INTERNAL_ERROR         500
    ├── ConfigError             CONFIG_ERROR           config.yaml or the API key can't be used (start-up only)
    ├── IngestionError          INGESTION_ERROR        the knowledge base file can't be read (start-up only)
    ├── VectorFileError         VECTOR_FILE_ERROR      the vectors can't be saved (python main.py index only)
    ├── TraceNotFoundError      TRACE_NOT_FOUND        404  no trace is kept with this ID
    ├── NotReadyError           NOT_READY              503  the engine isn't built
    ├── VectorStoreError        VECTOR_STORE_ERROR     503  the vector store failed
    ├── RequestTimeoutError     REQUEST_TIMEOUT        504  the whole question took too long
    └── UpstreamError           UPSTREAM_ERROR         502  a model provider failed
        ├── UpstreamTimeoutError    UPSTREAM_TIMEOUT       504
        └── UpstreamRateLimitError  UPSTREAM_RATE_LIMITED  503
"""
from collections.abc import Iterator

from langchain_core.exceptions import ModelRateLimitError, ModelTimeoutError


class AppError(Exception):
    """An error the app raises on purpose. str(error) is the detail for the log; public_message is for callers."""

    code = "INTERNAL_ERROR"
    status_code = 500
    public_message = "Something went wrong on the server."
    retryable = False


class ConfigError(AppError):
    code = "CONFIG_ERROR"


class IngestionError(AppError):
    code = "INGESTION_ERROR"


class VectorFileError(AppError):
    code = "VECTOR_FILE_ERROR"


class TraceNotFoundError(AppError):
    code = "TRACE_NOT_FOUND"
    status_code = 404
    public_message = "No trace is kept with this ID: only the newest API requests' traces are kept."


class NotReadyError(AppError):
    code = "NOT_READY"
    status_code = 503
    public_message = "The knowledge base isn't loaded yet. Try again shortly."
    retryable = True


class VectorStoreError(AppError):
    code = "VECTOR_STORE_ERROR"
    status_code = 503
    public_message = "The search index failed. Try again in a moment."


class RequestTimeoutError(AppError):
    code = "REQUEST_TIMEOUT"
    status_code = 504
    public_message = "The question took too long to answer. Try again in a moment."
    retryable = True


class UpstreamError(AppError):
    """A model provider failed. service names which one: "embeddings" or "llm"."""

    code = "UPSTREAM_ERROR"
    status_code = 502
    public_message = "The AI service failed to answer. Try again in a moment."

    def __init__(self, service: str, detail: str, *, retryable: bool | None = None):
        super().__init__(f"{service}: {detail}")
        self.service = service
        if retryable is not None:
            self.retryable = retryable


class UpstreamTimeoutError(UpstreamError):
    code = "UPSTREAM_TIMEOUT"
    status_code = 504
    public_message = "The AI service took too long to answer. Try again in a moment."
    retryable = True


class UpstreamRateLimitError(UpstreamError):
    code = "UPSTREAM_RATE_LIMITED"
    status_code = 503
    public_message = "The AI service is busy (rate limited). Try again in a minute."
    retryable = True


# -------------------------------------------------
# Provider Errors
# -------------------------------------------------

# httpx's ReadTimeout, ConnectTimeout and TimeoutException, and the like in other HTTP libraries: matched by name, so
# this module needs none of them installed
TIMEOUT_NAME_ENDINGS = ("Timeout", "TimeoutError", "TimeoutException")


def upstream_error(service: str, error: Exception) -> UpstreamError:
    """The UpstreamError for a provider's exception: a timeout, a rate limit, or any other failure. The provider's
    own error is often wrapped (LangChain's Gemini embeddings wrap Google's), so the whole chain of causes is read."""
    detail = f"{type(error).__name__}: {error}"
    causes = list(_causes(error))
    for cause in causes:
        status = _http_status(cause)
        if (isinstance(cause, (TimeoutError, ModelTimeoutError)) or status in (408, 504)
                or type(cause).__name__.endswith(TIMEOUT_NAME_ENDINGS)):
            return UpstreamTimeoutError(service, detail)
        if isinstance(cause, ModelRateLimitError) or status == 429:
            return UpstreamRateLimitError(service, detail)
    # A server error (5xx) may pass; a refused request (a bad key, a bad model name) won't until it's fixed
    retryable = any(getattr(cause, "is_retryable", False) or 500 <= (_http_status(cause) or 0) < 600
                    for cause in causes)
    return UpstreamError(service, detail, retryable=retryable)


def _causes(error: BaseException) -> Iterator[BaseException]:
    """The error, then what caused it, and so on: `raise ... from` (__cause__) or an error while handling another."""
    seen = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _http_status(error: BaseException) -> int | None:
    """The HTTP status an exception carries, if any: Google's errors call it code; others, status_code."""
    for name in ("code", "status_code"):
        value = getattr(error, name, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    return None
