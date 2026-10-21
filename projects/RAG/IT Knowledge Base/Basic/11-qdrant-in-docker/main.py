"""
IT Knowledge Base: The API and the Chat Page
============================================

The RAG engine served by FastAPI, plus index.html, a page to ask questions in, with the chunks kept in a Qdrant
server. The engine is built once, when the server starts, and each request answers one question. It handles:
  1. Building the engine at start-up, or stopping with what to do if Qdrant isn't running
  2. Serving the chat page
  3. Checking each question before it costs a call to Gemini, then answering it

    GET  / (or /index.html)  ->  the chat page; it sends each question to POST /api/query
    POST /api/query   {"question": "..."}  ->  {"answer": "...", "sources": [...]};  bad question 422, Gemini fails 502
    GET  /api/stats   ->  {"documents": 10, "chunks": 28, ...}
    GET  /api/health  ->  {"status": "ok"}

Usage (the Qdrant server must be running first: docker compose up -d):
    uvicorn main:app --reload      # then open http://127.0.0.1:8000: the chat page
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from qdrant_client.http.exceptions import ResponseHandlingException

from rag_engine import RAGEngine
from vector_store import QDRANT_URL

logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

engine = RAGEngine()                               # settings only: importing this file reads and calls nothing


# Runs once before the server takes any request, so Qdrant is checked once, not on every request
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine.build()
    except ResponseHandlingException as err:
        # No Qdrant server answered at QDRANT_URL: the server can't start, so say what to do.
        raise RuntimeError(f"Can't reach Qdrant at {QDRANT_URL} ({err}). "
                           "Start it first, in this folder:   docker compose up -d") from None
    logger.info("RAG engine built: %(documents)s articles, %(chunks)s chunks", engine.stats())
    yield


app = FastAPI(title="IT Knowledge Base", lifespan=lifespan)

# Found next to this file, whichever folder the server was started from
PAGE = Path(__file__).resolve().parent / "index.html"


# FastAPI checks each request against QueryIn before the route runs: a bad question gets a 422 and costs nothing
class QueryIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)   # "  hi " -> "hi", and "   " -> "" (too short)
    question: str = Field(min_length=1, max_length=500)


class Source(BaseModel):
    title: str
    system: str
    category: str
    snippet: str


class QueryOut(BaseModel):
    answer: str
    sources: list[Source]


@app.get("/")              # two decorators on one function: the page answers at both addresses
@app.get("/index.html")
async def page():
    """The chat page. Served by this same server, so its fetch("/api/query") needs no full address."""
    # no-cache: other projects in this repo use port 8000 too, so a saved copy could be another project's page
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health():
    """Answers as soon as the server is up: a quick check that it runs."""
    return {"status": "ok"}


@app.get("/api/stats")
async def stats():
    """What the engine holds and how it's set up."""
    return engine.stats()


@app.post("/api/query", response_model=QueryOut)
async def query(body: QueryIn):
    """One question, answered from the knowledge base, with its sources. Two calls to Gemini."""
    try:
        return await engine.aquery(body.question)
    except Exception as err:
        # The full reason goes to this terminal; the page only learns that Gemini didn't answer.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from None
