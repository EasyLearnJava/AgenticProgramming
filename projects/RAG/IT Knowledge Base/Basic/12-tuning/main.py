"""
IT Knowledge Base: The API and the Chat Page
============================================

The RAG engine served by FastAPI, plus index.html, a page to ask questions in, with the chunks kept on disk in
qdrant_data/. The engine is built once, when the server starts, and each request answers one question. It handles:
  1. Building the engine at start-up, and closing Qdrant's folder when the server stops
  2. Serving the chat page
  3. Checking each question before it costs a call to Gemini, then answering it

    GET  / (or /index.html)  ->  the chat page; it sends each question to POST /api/query
    POST /api/query   {"question": "..."}  ->  {"answer": "...", "sources": [...]};  bad question 422, Gemini fails 502
    GET  /api/stats   ->  {"documents": 10, "chunks": 28, ...}
    GET  /api/health  ->  {"status": "ok"}

Usage:
    uvicorn main:app               # then open http://127.0.0.1:8000: the chat page
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from rag_engine import RAGEngine

# getLogger() comes from Python's logging module: the logger by that name
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

engine = RAGEngine()                               # settings only: importing this file reads and calls nothing


# Runs once before the server takes any request, so the stored chunks are checked once, not on every request
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.build()
    # info() comes from Python's logging module: a line in the server's log
    logger.info("RAG engine built: %(documents)s articles, %(chunks)s chunks", engine.stats())
    yield
    # The server is stopping (Ctrl+C): free qdrant_data/ for the next start
    # close() comes from qdrant_client's QdrantClient: it frees the folder, so another program can open it
    engine.client.close()


# FastAPI() comes from fastapi: the web app; lifespan is our code that runs at start-up
app = FastAPI(title="IT Knowledge Base", lifespan=lifespan)

# Found next to this file, whichever folder the server was started from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
PAGE = Path(__file__).resolve().parent / "index.html"


# FastAPI checks each request against QueryIn before the route runs: a bad question gets a 422 and costs nothing
class QueryIn(BaseModel):
    # ConfigDict comes from pydantic: settings for this model; here, spaces trimmed from every string
    model_config = ConfigDict(str_strip_whitespace=True)   # "  hi " -> "hi", and "   " -> "" (too short)
    # Field comes from pydantic: the checks FastAPI makes on each question before the route runs
    question: str = Field(min_length=1, max_length=500)


class Source(BaseModel):
    title: str
    system: str
    category: str
    snippet: str


class QueryOut(BaseModel):
    answer: str
    sources: list[Source]


# app.get() comes from FastAPI: the function below answers GET requests at this address
@app.get("/")              # two decorators on one function: the page answers at both addresses
@app.get("/index.html")
async def page():
    """The chat page. Served by this same server, so its fetch("/api/query") needs no full address."""
    # no-cache: other projects in this repo use port 8000 too, so a saved copy could be another project's page
    # FileResponse comes from fastapi: it sends this file as the answer
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})


# app.get() comes from FastAPI: the function below answers GET requests at this address
@app.get("/api/health")
async def health():
    """Answers as soon as the server is up: a quick check that it runs."""
    return {"status": "ok"}


# app.get() comes from FastAPI: the function below answers GET requests at this address
@app.get("/api/stats")
async def stats():
    """What the engine holds and how it's set up."""
    return engine.stats()


# app.post() comes from FastAPI: the function below answers POST requests at this address
@app.post("/api/query", response_model=QueryOut)
async def query(body: QueryIn):
    """One question, answered from the knowledge base, with its sources. Two calls to Gemini."""
    try:
        return await engine.aquery(body.question)
    except Exception as err:
        # The full error, with its traceback, goes to this terminal; the page only learns the question wasn't
        # answered, and the error's type. It's often Gemini (a quota, a network problem), but not always.
        # exception() comes from Python's logging module: an error line in the server's log, with the traceback
        logger.exception("Couldn't answer: %s", err)
        # HTTPException comes from fastapi: FastAPI answers with this status code and detail
        raise HTTPException(status_code=502, detail=f"Couldn't answer the question ({type(err).__name__}).") from None
