"""
IT Knowledge Base: The API
==========================

The engine (rag_engine.py) behind HTTP, safe to put in front of real users. It handles:
  1. Authentication: every /v1 route needs `Authorization: Bearer <key>`, a key whose hash is in the keys file
  2. Rate limits: each caller's requests a minute (security.RateLimiter); over it, 429 with Retry-After
  3. Request limits: the body's size (413, before it's read), the question's length (422) and the engine's deadline
     (504)
  4. Request IDs: each request gets one (or keeps a valid X-Request-ID it came with), sent back in the X-Request-ID
     header and in every error, and on every log line written while it's served
  5. Logs: one access line per request: its method, path, status, time and caller, an error's code, and for an
     answer its status, tokens, cost and each stage's time; never the question, the answer or a key. A failure of a
     part the app calls (a 5xx) gets a WARNING line too, saying what failed
  6. One error shape for every failure: {"error": {"code", "message", "request_id", "retryable", "details"?}}
  7. Health: /health/live (the process runs) and /health/ready (the store holds the knowledge base, and neither
     breaker is open)
  8. Streaming: POST /v1/query/stream sends server-sent events: "delta", each new piece of the answer as it's
     written; then "answer", the checked answer with its sources (or "error")
  9. Feedback: POST /v1/feedback rates an answer by its request ID, kept for the evaluation set (feedback.py)
 10. Versioning and CORS: the routes under /v1; a browser may call them only from a page cors_origins names

    app = create_app(engine, keys=ApiKeys.load(path), limiter=RateLimiter(30), feedback=FeedbackStore(path),
                     settings=settings.api)
"""
import asyncio
import json
import logging
import math
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated, Any, Literal, NoReturn

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from answering import AnswerError
from embedding import EmbeddingError, is_daily_quota
from feedback import FeedbackStore
from observability import current_request_id, note, request_context
from rag_engine import CircuitOpenError, DeadlineError, EngineAnswer, RAGEngine
from retriever import RetrievalError
from security import ApiKeys, RateLimiter
from settings import ApiSettings
from vector_store import StoreError

logger = logging.getLogger("api")

API = "/v1"
MAX_QUESTION_CHARS = 500
MAX_COMMENT_CHARS = 500
ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"     # a request or session ID: anything else is refused (in a header, replaced)
REQUEST_ID_HEADER = "X-Request-ID"
READY_CHECK_SECONDS = 5.0                  # how long the store's answer to "ready?" is trusted before it's asked again
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",   # a response is only ever read as the type it's sent as
    "X-Frame-Options": "DENY",             # no other site can show it in a frame
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",           # answers and errors aren't kept by a browser or a proxy
}
# An error from one of these libraries came from outside the app: Google's client, the HTTP layers under it, Qdrant's
UPSTREAM_MODULES = ("google", "httpx", "httpcore", "qdrant_client", "grpc")
INTERNAL_MESSAGE = "Something went wrong on the server. Try again; if it keeps happening, quote the request ID."
DAILY_QUOTA_MESSAGE = "The AI service's quota for today is used up. Try again after midnight Pacific time."


# -------------------------------------------------
# What Each Route Takes and Gives Back
# -------------------------------------------------

class QueryRequest(BaseModel):
    # "  hi " -> "hi", and "   " -> "" (too short); an unknown field, such as a misspelt "question", is refused
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS, examples=["My VPN keeps timing out"])
    session_id: str | None = Field(default=None, pattern=ID_PATTERN,
                                   description="The same for each question of one conversation, so a follow-up "
                                               "(\"and on Mac?\") is read with what came before")


class Source(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    section: str
    system: str


class QueryResponse(BaseModel):
    request_id: str = Field(description="Quote it to rate the answer (POST /v1/feedback), or in a complaint")
    status: Literal["answered", "not_covered", "no_match"]
    answer: str
    asked: str = Field(description="The question as it was searched: a follow-up, rewritten with the conversation")
    sources: list[Source]
    cached: Literal["exact", "meaning"] | None
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    seconds: float


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    request_id: str = Field(pattern=ID_PATTERN)
    rating: Literal["up", "down"]
    comment: str = Field(default="", max_length=MAX_COMMENT_CHARS)


class FeedbackResponse(BaseModel):
    request_id: str
    rating: Literal["up", "down"]


class LiveResponse(BaseModel):
    status: str = "alive"


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse} for status in (401, 404, 413, 422, 429, 502, 503, 504)}


# -------------------------------------------------
# Errors - One Shape for Every Failure
# -------------------------------------------------

class ApiError(Exception):
    """A failure the caller is told about: its status, code and message; never a part's own error text."""

    def __init__(self, status: int, code: str, message: str, *, retryable: bool = False,
                 headers: Mapping[str, str] | None = None, details: list[ErrorDetail] | None = None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.retryable, self.headers, self.details = retryable, dict(headers or {}), details

    def body(self) -> dict[str, Any]:
        return ErrorResponse(error=ErrorBody(code=self.code, message=self.message, request_id=current_request_id(),
                                             retryable=self.retryable, details=self.details)).model_dump(
            exclude_none=True)

    def response(self) -> JSONResponse:
        return JSONResponse(self.body(), status_code=self.status, headers=self.headers)


class BodyTooLarge(HTTPException):
    """A body sent without its size grew past the limit while it was read. An HTTPException, so FastAPI passes it on
    as it is (any other error while reading a body becomes a 400)."""

    def __init__(self, limit: int):
        super().__init__(413, f"The request's body is over {limit:,} bytes")


def failure(err: BaseException) -> ApiError | None:
    """What the caller is told about an error the engine raised; None for one that's the app's own fault (a 500)."""
    if isinstance(err, ApiError):
        return err
    if isinstance(err, DeadlineError):
        return ApiError(504, "DEADLINE_EXCEEDED", str(err), retryable=True)
    if isinstance(err, CircuitOpenError):
        return ApiError(503, "UNAVAILABLE", str(err), retryable=True,
                        headers={"Retry-After": str(max(1, math.ceil(err.retry_after)))})
    if is_daily_quota(err):
        return ApiError(503, "UPSTREAM_DAILY_QUOTA", DAILY_QUOTA_MESSAGE, retryable=True)
    if isinstance(err, (EmbeddingError, StoreError, RetrievalError, AnswerError, ConnectionError, TimeoutError)) or \
            type(err).__module__.split(".")[0] in UPSTREAM_MODULES:
        return ApiError(502, "UPSTREAM_ERROR", "The search, or the model behind it, failed: try again shortly",
                        retryable=True)
    return None


def raise_for(err: Exception) -> NoReturn:
    """Raise what the caller is told about the engine's error; the app's own fault is raised as it is (a 500)."""
    known = failure(err)
    if known is None:
        raise err
    raise known from err


def log_failure(err: ApiError) -> None:
    """The error's code goes in the request's access line; a failure of a part the app calls (a 5xx) also gets a
    WARNING line, with what failed. The caller's mistakes (4xx) get no line of their own: a flood of them is one line
    each, not two."""
    note(error_code=err.code)
    if err.status >= 500:
        fields: dict[str, Any] = {"code": err.code, "status": err.status}
        cause = err.__cause__
        if cause is not None:        # the engine's errors and the services' never hold the question
            fields.update(error_type=type(cause).__name__, error=str(cause)[:300])
        logger.warning("Request failed: %s", err.code, extra=fields)


async def handle_api_error(request: Request, err: ApiError) -> JSONResponse:
    log_failure(err)
    return err.response()


async def handle_validation_error(request: Request, err: RequestValidationError) -> JSONResponse:
    """422, with each field and why; the values sent aren't logged or sent back."""
    details = [ErrorDetail(field=_field_name(problem["loc"]), message=problem["msg"]) for problem in err.errors()]
    refused = ApiError(422, "INVALID_REQUEST", "The request isn't valid: " + "; ".join(
        f"{detail.field}: {detail.message}" for detail in details), details=details)
    note(error_code=refused.code, invalid_fields=[detail.field for detail in details])
    return refused.response()


async def handle_http_error(request: Request, err: HTTPException) -> JSONResponse:
    """Starlette's own errors (404, 405) and BodyTooLarge, in the same shape."""
    code = {413: "REQUEST_TOO_LARGE"}.get(err.status_code) or HTTPStatus(err.status_code).name
    note(error_code=code)
    return ApiError(err.status_code, code, str(err.detail), headers=err.headers).response()


def _field_name(location: tuple) -> str:
    """Where a problem is: ("body", "question") -> "question"; the whole body (missing, or not JSON) -> "body"."""
    parts = list(location)
    if len(parts) > 1 and parts[0] == "body" and isinstance(parts[1], str):
        parts = parts[1:]
    elif parts and parts[0] == "body":
        parts = ["body"]
    return ".".join(str(part) for part in parts)


# -------------------------------------------------
# RequestMiddleware - Every Request's ID, Size Limit and Access Line
# -------------------------------------------------

class RequestMiddleware:
    """
    Wraps every HTTP request, outside the rest of the app (CORS too):
      1. Its ID: a valid X-Request-ID it came with, else a new one; sent back in the X-Request-ID header
      2. Its body's size: over max_body_bytes, a 413 before the route reads it (by its Content-Length, or as it
         arrives when it has none)
      3. Its access line, once the response is done (a streamed one too): method, path, status, time and the fields
         the route noted; the health checks' lines are DEBUG, so a load balancer's checks don't drown the rest
      4. Security headers on every response
      5. The last line of defence: an error nothing else handled is logged with its traceback, and answered with a
         500 in the one error shape, never with the error's text

    A plain ASGI middleware, not Starlette's BaseHTTPMiddleware: it sees every response, and adds no task of its own.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":           # the server's start-up and shut-down messages
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        given = headers.get(REQUEST_ID_HEADER, "")
        request_id = given if re.fullmatch(ID_PATTERN, given) else uuid.uuid4().hex
        method, path = scope["method"], scope["path"]
        with request_context(request_id) as fields:
            started = time.perf_counter()
            status: int | None = None
            received = 0

            async def send_with_headers(message: Message) -> None:
                nonlocal status
                if message["type"] == "http.response.start":
                    status = message["status"]
                    response_headers = MutableHeaders(scope=message)
                    response_headers[REQUEST_ID_HEADER] = request_id
                    for name, value in SECURITY_HEADERS.items():
                        response_headers.setdefault(name, value)
                await send(message)

            async def receive_counted() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > self.max_body_bytes:
                        raise BodyTooLarge(self.max_body_bytes)
                return message

            try:
                length = headers.get("content-length", "")
                if length.isdigit() and int(length) > self.max_body_bytes:
                    refused = ApiError(413, "REQUEST_TOO_LARGE", f"The request's body is over "
                                                                 f"{self.max_body_bytes:,} bytes")
                    log_failure(refused)
                    await refused.response()(scope, receive, send_with_headers)
                else:
                    await self.app(scope, receive_counted, send_with_headers)
            except Exception:
                logger.exception("Unhandled error", extra={"method": method, "path": path})
                note(error_code="INTERNAL_ERROR")
                if status is not None:        # the response has started: nothing more can be sent
                    raise
                await ApiError(500, "INTERNAL_ERROR", INTERNAL_MESSAGE).response()(scope, receive, send_with_headers)
            finally:
                level = logging.DEBUG if path.startswith("/health/") else logging.INFO
                logger.log(level, "%s %s %s", method, path, status or 500,
                           extra={"method": method, "path": path, "status": status or 500,
                                  "ms": round((time.perf_counter() - started) * 1000, 1), **fields})


# -------------------------------------------------
# Readiness - Can the Engine Answer?
# -------------------------------------------------

class Readiness:
    """Whether the store holds the knowledge base: a collection behind its alias, with points in it. The store is
    asked at most every READY_CHECK_SECONDS, so a busy server doesn't ask it on every request."""

    def __init__(self, engine: RAGEngine, *, clock: Callable[[], float] = time.monotonic):
        self.engine = engine
        self.clock = clock
        self._problem: str | None = None
        self._asked_at: float | None = None

    def store_problem(self) -> str | None:
        """None when the store holds the knowledge base; else what's wrong."""
        now = self.clock()
        if self._asked_at is None or now - self._asked_at >= READY_CHECK_SECONDS:
            self._problem, self._asked_at = self._ask_store(), now
        return self._problem

    def _ask_store(self) -> str | None:
        store = self.engine.store
        try:
            collection = store.current()
            if collection is None:
                return f"no collection behind the alias {store.alias}: run python pipeline.py first"
            if not store.client.count(collection, exact=False).count:
                return f"{collection} holds no points: run python pipeline.py"
        except Exception as err:
            return f"the vector store can't be reached ({type(err).__name__})"
        return None

    def checks(self) -> dict[str, str]:
        return {"store": self.store_problem() or "ok", "vector_store_breaker": self.engine.store_breaker.state,
                "chat_model_breaker": self.engine.model_breaker.state}


# -------------------------------------------------
# What an Answer Becomes
# -------------------------------------------------

def answer_body(answered: EngineAnswer, request_id: str) -> QueryResponse:
    grounded = answered.answer
    return QueryResponse(
        request_id=request_id, status=grounded.status, answer=grounded.answer, asked=answered.asked,
        sources=[Source(**{name: str(doc.metadata.get(name, "")) for name in Source.model_fields})
                 for doc in grounded.sources],
        cached=answered.cached or None, prompt_version=grounded.prompt_version,
        input_tokens=grounded.usage.get("input_tokens", 0), output_tokens=grounded.usage.get("output_tokens", 0),
        cost_usd=answered.cost_usd, seconds=round(answered.trace.seconds, 3))


def answer_fields(answered: EngineAnswer) -> dict[str, Any]:
    """What the access line says of an answer: its counts and times, never its text or the question's."""
    grounded = answered.answer
    return {"answer_status": grounded.status, "cached": answered.cached or "no", "calls": grounded.calls,
            "input_tokens": grounded.usage.get("input_tokens", 0),
            "output_tokens": grounded.usage.get("output_tokens", 0), "cost_usd": answered.cost_usd,
            "trace_id": answered.trace.trace_id,
            "stages_ms": {span.name: round(span.seconds * 1000, 1) for span in answered.trace.spans}}


def sse(event: str, data: Mapping[str, Any]) -> str:
    """One server-sent event: its name, then its data as one line of JSON."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# -------------------------------------------------
# create_app() - The Routes, Guarded
# -------------------------------------------------

def create_app(engine: RAGEngine, *, keys: ApiKeys, limiter: RateLimiter, feedback: FeedbackStore,
               settings: ApiSettings, on_close: Callable[[], None] | None = None) -> FastAPI:
    """
    The API around the engine: every part passed in (wiring.make_api() builds them from kb_settings.toml), nothing
    called until a request comes. on_close: called when the server stops (the store's client is closed there).
    """
    readiness = Readiness(engine)
    bearer = HTTPBearer(auto_error=False, description="An API key: python main.py add-key NAME makes one")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if on_close is not None:
            on_close()

    app = FastAPI(title="IT Knowledge Base API", version="1", lifespan=lifespan, redoc_url=None)
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    # The last one added is the outermost: every request, a CORS preflight too, gets an ID and an access line
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
                       expose_headers=[REQUEST_ID_HEADER, "Retry-After"], max_age=600)
    app.add_middleware(RequestMiddleware, max_body_bytes=settings.max_body_bytes)

    async def caller(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
        """The caller's name, from its key, within its rate limit. Raises ApiError: 401, or 429."""
        if credentials is None:
            raise ApiError(401, "UNAUTHORIZED", "An API key is needed: send it as Authorization: Bearer <key>",
                           headers={"WWW-Authenticate": "Bearer"})
        name = keys.caller(credentials.credentials)
        if name is None:
            raise ApiError(401, "UNAUTHORIZED", "The API key isn't valid", headers={"WWW-Authenticate": "Bearer"})
        note(caller=name)
        wait = limiter.take(name)
        if wait:
            seconds = max(1, math.ceil(wait))
            many = f"{limiter.per_minute} request{'s' if limiter.per_minute != 1 else ''}"
            raise ApiError(429, "RATE_LIMITED", f"Over {many} a minute: try again in "
                                                f"{seconds} s", retryable=True, headers={"Retry-After": str(seconds)})
        return name

    async def require_ready() -> None:
        problem = await asyncio.to_thread(readiness.store_problem)
        if problem:
            raise ApiError(503, "NOT_READY", f"The knowledge base isn't ready: {problem}", retryable=True,
                           headers={"Retry-After": str(int(READY_CHECK_SECONDS))})

    def session(name: str, session_id: str | None) -> str | None:
        """A caller's conversation: another caller can't read it, even with the same session ID."""
        return f"{name}/{session_id}" if session_id else None

    async def answered_body(answered: EngineAnswer, name: str) -> QueryResponse:
        """Keep the answer so it can be rated, note its counts for the access line, and give back its body."""
        request_id = current_request_id()
        await asyncio.to_thread(feedback.record, request_id, name, answered, model=engine.model_name)
        note(**answer_fields(answered))
        return answer_body(answered, request_id)

    @app.post(f"{API}/query", response_model=QueryResponse, responses=ERROR_RESPONSES,
              summary="Ask a question; the checked answer, with its sources")
    async def query(body: QueryRequest, name: Annotated[str, Depends(caller)]) -> QueryResponse:
        await require_ready()
        try:
            answered = await engine.aask(body.question, session=session(name, body.session_id))
        except Exception as err:
            raise_for(err)
        return await answered_body(answered, name)

    @app.post(f"{API}/query/stream", response_class=StreamingResponse, responses=ERROR_RESPONSES,
              summary="Ask a question; server-sent events: the answer as it's written, then the checked answer")
    async def query_stream(body: QueryRequest, name: Annotated[str, Depends(caller)]) -> StreamingResponse:
        await require_ready()
        events = engine.astream(body.question, session=session(name, body.session_id))
        try:
            first = await anext(events)       # a failure before the first piece still gets its own status code
        except Exception as err:
            raise_for(err)

        async def event_text(event: tuple[str, Any]) -> str:
            kind, value = event
            if kind == "delta":
                return sse("delta", {"text": value})
            return sse("answer", (await answered_body(value, name)).model_dump())

        async def stream() -> AsyncIterator[str]:
            try:
                yield await event_text(first)
                async for event in events:
                    yield await event_text(event)
            except Exception as err:          # the response has started: the failure is the last event
                known = failure(err)
                if known is None:
                    logger.exception("Stream failed")
                    known = ApiError(500, "INTERNAL_ERROR", INTERNAL_MESSAGE)
                    note(error_code=known.code)
                else:
                    known.__cause__ = err
                    log_failure(known)
                yield sse("error", known.body())

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.post(f"{API}/feedback", response_model=FeedbackResponse, responses=ERROR_RESPONSES,
              summary="Rate an answer, by its request ID: up or down, with a comment")
    def rate(body: FeedbackRequest, name: Annotated[str, Depends(caller)]) -> FeedbackResponse:
        if not feedback.rate(body.request_id, name, body.rating, body.comment):
            raise ApiError(404, "NOT_FOUND", f"No answer with the request ID {body.request_id} was given to this "
                                             f"API key in the last {feedback.keep_days:g} days")
        note(rating=body.rating)
        return FeedbackResponse(request_id=body.request_id, rating=body.rating)

    @app.get(f"{API}/stats", responses=ERROR_RESPONSES, summary="What the engine runs with, and the feedback so far")
    def stats(name: Annotated[str, Depends(caller)]) -> dict[str, Any]:
        return {"engine": engine.stats(), "feedback": feedback.counts(), "requests_per_minute": limiter.per_minute,
                "max_question_chars": MAX_QUESTION_CHARS}

    @app.get("/health/live", response_model=LiveResponse, summary="The process runs")
    async def live() -> LiveResponse:
        return LiveResponse()

    @app.get("/health/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}},
             summary="The store holds the knowledge base, and neither breaker is open")
    async def ready() -> JSONResponse:
        checks = await asyncio.to_thread(readiness.checks)
        is_ready = checks["store"] == "ok" and "open" not in (checks["vector_store_breaker"],
                                                              checks["chat_model_breaker"])
        body = ReadyResponse(status="ready" if is_ready else "not_ready", checks=checks)
        return JSONResponse(body.model_dump(), status_code=200 if is_ready else 503)

    return app
