"""
IT Knowledge Base: The API
==========================

The RAG engine from pipeline.py, served by FastAPI: the engine is built once, when the server starts, and each
request answers one question. It handles:
  1. Building the engine at start-up
  2. Checking each question before it costs a call to Gemini
  3. Answering, and reporting a 502 if answering fails (often a failed call to Gemini)

    POST /api/query   {"question": "..."}  ->  {"answer": "...", "sources": [{"title", "system", "category", ...}]}
                      blank, or over 500 characters  ->  422;  answering fails (often Gemini)  ->  502
    GET  /api/stats   ->  {"documents": 10, "chunks": 28, ...}
    GET  /api/health  ->  {"status": "ok"}

Usage:
    uvicorn main:app               # http://127.0.0.1:8000/docs is FastAPI's page for trying the routes
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pipeline import RAGEngine

# getLogger() comes from Python's logging module: the logger by that name
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

engine = RAGEngine()                               # settings only: importing this file reads and calls nothing


# Runs once before the server takes any request, so the chunks are embedded once, not on every request
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.build()
    # info() comes from Python's logging module: a line in the server's log
    logger.info("RAG engine built: %(documents)s articles, %(chunks)s chunks", engine.stats())
    yield


# FastAPI() comes from fastapi: the web app; lifespan is our code that runs at start-up
app = FastAPI(title="IT Knowledge Base", lifespan=lifespan)


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
        # The full error, with its traceback, goes to this terminal; the caller only learns the question wasn't
        # answered, and the error's type. It's often Gemini (a quota, a network problem), but not always.
        # exception() comes from Python's logging module: an error line in the server's log, with the traceback
        logger.exception("Couldn't answer: %s", err)
        # HTTPException comes from fastapi: FastAPI answers with this status code and detail
        raise HTTPException(status_code=502, detail=f"Couldn't answer the question ({type(err).__name__}).") from None
