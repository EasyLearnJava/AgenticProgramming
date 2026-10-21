"""
The API and the chat page: the RAG engine (step 08) served by FastAPI, plus index.html, a page to ask questions in.
The engine is built once, when the server starts; each request then answers one question. From step 11 on, the
chunks are kept in a Qdrant server, which must be running before this one starts:   docker compose up -d

    GET  / (or /index.html)  ->  the chat page; it sends each question to POST /api/query and shows the answer
    POST /api/query   {"question": "How do I fix VPN connection timeouts?"}
                      ->  {"answer": "...", "sources": [{"title", "system", "category", "snippet"}, ...]}
                      an empty or blank question, or one over 500 characters  ->  422, and no call to Gemini
                      Gemini doesn't answer  ->  502, and the reason in this terminal
    GET  /api/stats   ->  {"documents": 10, "chunks": 28, ...}
    GET  /api/health  ->  {"status": "ok"}

Start it with:   uvicorn main:app --reload   ->   Uvicorn running on http://127.0.0.1:8000
Then open that address: the chat page.
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

# ① The engine, with its settings only: importing this file reads nothing and calls nothing.
engine = RAGEngine()


# ② Start-up and shutdown. FastAPI runs the code before `yield` once, before the server takes any request, and the
#    code after it when the server stops. Building here checks the Qdrant server once, not on every request.
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

# ③ The page, found next to this file whichever folder the server was started from.
PAGE = Path(__file__).resolve().parent / "index.html"


# ④ The request's and the answer's shapes. FastAPI checks each request's JSON against QueryIn before the route runs
#    (a bad question gets a 422 and costs nothing), and shapes each answer as QueryOut.
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


# ⑤ The routes.
@app.get("/")              # two decorators on one function: the page answers at both addresses
@app.get("/index.html")
async def page():
    """The chat page. Served by this same server, so its fetch("/api/query") needs no full address."""
    # no-cache: the browser must ask the server again before reusing its saved copy of this page. Other projects in
    # this repo use port 8000 too, so without it another project's page could show up here.
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
