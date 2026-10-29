"""
IT Knowledge Base: The Routes
=============================

What the server answers at each address. The routes get the engine, the settings and the trace store from the app
(app.state), never from a module of their own, so a test can hand the app an engine with stand-ins. It handles:
  1. The chat page, with a content security policy: its scripts and styles may only come from this server
  2. Two health checks: alive (the process answers) and ready (the engine is built and holds every chunk)
  3. The engine's info for the page: what it holds, the question's limit, the sample questions, the build's trace
  4. One question: answered within api.request_timeout_seconds, or a 504
  5. One request's trace: each of its log lines, for the page's boxes (its pipeline, times, calls and logs)

    GET  /                      ->  the chat page (static/index.html; its script and styles are under /static/)
    GET  /health/live           ->  {"status": "alive"}
    GET  /health/ready          ->  {"status": "ready", "chunks": 28}, or 503 NOT_READY
    GET  /api/v1/info           ->  {"documents": 10, "chunks": 28, ..., "sample_questions": [...]}
    POST /api/v1/query          {"question": "..."}  ->  {"answer": "...", "sources": [...]}
                                or an error: 422, 502, 503, 504, each {"error": {"code", "message", "trace_id", ...}}
    GET  /api/v1/traces/{id}    ->  {"trace_id": "...", "events": [...], "dropped": 0}, or 404 TRACE_NOT_FOUND
"""
import asyncio
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import FileResponse

from src.api.schemas import (
    MAX_QUESTION_LENGTH,
    TRACE_ID_PATTERN,
    ErrorResponse,
    InfoResponse,
    LiveResponse,
    QueryRequest,
    QueryResponse,
    QuerySource,
    ReadyResponse,
    TraceResponse,
)
from src.config.settings import PROJECT_DIR, Settings
from src.exceptions import RequestTimeoutError, TraceNotFoundError
from src.observability.trace_store import TraceStore
from src.pipeline.rag_engine import RAGEngine

STATIC_DIR: FilePath = PROJECT_DIR / "static"

# The page's own files only: no inline script, no other site's script, style, font or frame
CONTENT_SECURITY_POLICY = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                           "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

# The error shapes each route can answer with, for /docs
ERRORS = {status: {"model": ErrorResponse} for status in (422, 500, 502, 503, 504)}
TRACE_ERRORS = {status: {"model": ErrorResponse} for status in (404, 422)}

router = APIRouter()


def get_engine(request: Request) -> RAGEngine:
    return request.app.state.engine


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_trace_store(request: Request) -> TraceStore | None:
    return request.app.state.trace_store


# Depends() comes from FastAPI: it calls the function for each request and hands the route what it returns
EngineDep = Annotated[RAGEngine, Depends(get_engine)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TraceStoreDep = Annotated[TraceStore | None, Depends(get_trace_store)]


@router.get("/", include_in_schema=False)
async def page() -> FileResponse:
    """The chat page. Served by this same server, so its requests need no full address."""
    return FileResponse(STATIC_DIR / "index.html", headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY})


@router.get("/health/live", response_model=LiveResponse, tags=["health"])
async def live() -> LiveResponse:
    """Answers as soon as the process runs: whether to restart it."""
    return LiveResponse()


@router.get("/health/ready", response_model=ReadyResponse, tags=["health"], responses=ERRORS)
async def ready(engine: EngineDep) -> ReadyResponse:
    """Whether it can answer questions: whether to send it any. It calls no model: a check every few seconds would
    spend the key's quota."""
    return ReadyResponse(chunks=await asyncio.to_thread(engine.check_ready))


@router.get("/api/v1/info", response_model=InfoResponse, tags=["api"])
async def info(engine: EngineDep, settings: SettingsDep, trace_store: TraceStoreDep) -> InfoResponse:
    """What the engine holds and how it's set up, and what the page needs: the question's limit, the samples, and
    whether it can show traces."""
    return InfoResponse(name=settings.app.name, **engine.stats(), traces=trace_store is not None,
                        request_timeout_seconds=settings.api.request_timeout_seconds,
                        max_question_length=MAX_QUESTION_LENGTH, sample_questions=settings.app.sample_questions)


@router.post("/api/v1/query", response_model=QueryResponse, tags=["api"], responses=ERRORS)
async def query(body: QueryRequest, engine: EngineDep, settings: SettingsDep) -> QueryResponse:
    """One question, answered from the knowledge base, with its sources. Two calls to the providers."""
    timeout = settings.api.request_timeout_seconds
    try:
        # A deadline for the whole question, whatever each call's own timeout and retries add up to
        async with asyncio.timeout(timeout):
            result = await engine.aquery(body.question)
    except TimeoutError:
        raise RequestTimeoutError(f"No answer within api.request_timeout_seconds ({timeout} s)") from None
    return QueryResponse(answer=result.answer, sources=[
        QuerySource(title=source.title, system=source.system, category=source.category, snippet=source.snippet,
                    score=source.score) for source in result.sources])


@router.get("/api/v1/traces/{trace_id}", response_model=TraceResponse, tags=["api"], responses=TRACE_ERRORS)
async def trace(trace_id: Annotated[str, Path(pattern=TRACE_ID_PATTERN)], trace_store: TraceStoreDep) -> TraceResponse:
    """One API request's trace: each of its log lines, in timeline order. Kept for the newest tracing.max_traces
    requests, and only while tracing.enabled is on."""
    kept = trace_store.get(trace_id) if trace_store is not None else None
    if kept is None:
        reason = "it isn't kept, or never was" if trace_store is not None else "tracing.enabled is off"
        raise TraceNotFoundError(f"No trace {trace_id}: {reason}")
    return TraceResponse(trace_id=trace_id, **kept)
