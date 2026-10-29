"""
IT Knowledge Base: The API's Shapes
===================================

What each route takes and gives back, kept apart from the engine's own classes, so the API's JSON can't change by
accident when the engine does. FastAPI checks every request against these before a route runs, and shows them at
/docs. It handles:
  1. The question: trimmed, 1 to MAX_QUESTION_LENGTH characters, nothing else in the body
  2. The answer, its sources, the health checks and the engine's info
  3. A trace: each log line of one request, as an event on its timeline
  4. One error shape for every failure: {"error": {"code", "message", "trace_id", "retryable", "details"?}}
"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# The one place the question's limit is set: the page reads it from GET /api/v1/info
MAX_QUESTION_LENGTH = 500
TRACE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"      # what a trace ID can look like: anything else is refused


class QueryRequest(BaseModel):
    # "  hi " -> "hi", and "   " -> "" (too short); an unknown field, such as a misspelt "question", is refused
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH,
                          examples=["How do I fix VPN connection timeouts?"])


class QuerySource(BaseModel):
    title: str
    system: str
    category: str
    snippet: str
    score: float = Field(description="Cosine similarity of the chunk found to the question: 1.0 is the same direction")


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySource]


class LiveResponse(BaseModel):
    status: str = "alive"


class ReadyResponse(BaseModel):
    status: str = "ready"
    chunks: int


class InfoResponse(BaseModel):
    name: str
    documents: int
    chunks: int
    collection: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    embedding_model: str
    chat_model: str
    prompt_version: str
    built_at: str | None
    build_trace_id: str | None = Field(description="The start-up build's trace, to read at /api/v1/traces/{trace_id}")
    traces: bool = Field(description="Whether each API request's trace can be read at /api/v1/traces/{trace_id}")
    request_timeout_seconds: float = Field(description="How long a question may take before it gets a 504")
    max_question_length: int
    sample_questions: list[str]


class TraceEvent(BaseModel):
    at_ms: float = Field(description="When it happened, in ms from the start of the trace; for a span, when it started")
    logged_ms: float = Field(description="When the log line was written, in ms from the start of the trace")
    depth: int = Field(description="How many spans it sits inside")
    level: str
    logger: str
    message: str
    span: str | None = Field(None, description="The stage, for a span's line: llm.generate, vectordb.search, ...")
    status: str | None = Field(None, description="How the span ended: ok, error or cancelled")
    duration_ms: float | None = None
    fields: dict[str, Any] = Field(default_factory=dict, description="What the line recorded: model, tokens, ...")
    error: str | None = Field(None, description="The error's type and message, when the line has one")


class TraceResponse(BaseModel):
    trace_id: str
    events: list[TraceEvent] = Field(description="Each log line of the request, in timeline order")
    dropped: int = Field(description="Lines not kept: a trace keeps at most 300")


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str = Field(examples=["UPSTREAM_TIMEOUT"])
    message: str
    trace_id: str = Field(description="Every log line of this request carries it")
    retryable: bool = Field(description="Whether the same request may work if it's sent again later")
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
