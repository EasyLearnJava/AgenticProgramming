"""
A small FastAPI app that serves hello.py's branching chain over HTTP: one input at a time, or a batch.

    GET / (or /index.html) -> index.html, a page with a one-greeting form and a batch form
    POST /api/hello  body {"name": "Raghu", "style": "formal"}  -> {"answer": "Good day, Raghu. Welcome to LangChain."}
    POST /api/batch  body {"people": [{"name": "Raghu", "style": "formal"}, {"name": "Asha", "style": "casual"}]}
                     -> {"answers": ["Good day, Raghu. Welcome to LangChain.", "Hey Asha! Welcome to LangChain!"]}
                     any bad field (or an empty list, or more than 10 people) -> 422

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 7")

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """One person: a name and the style to greet them in. The style decides which branch runs."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
    style: Literal["formal", "casual"]


class BatchIn(BaseModel):
    """A list of people, greeted in one call. Capped at 10 so one request can't ask for thousands."""
    people: list[HelloIn] = Field(min_length=1, max_length=10)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/...") calls need no full address."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain once. The branch inside picks the formal or the casual path from body.style."""
    answer = await chain.ainvoke(body.model_dump())
    return {"answer": answer}


@app.post("/api/batch")
async def batch(body: BatchIn):
    """Runs the chain on every person in one call, at most 3 at a time. The answers keep the list's order."""
    # abatch() is batch()'s async twin.
    answers = await chain.abatch([person.model_dump() for person in body.people], config={"max_concurrency": 3})
    return {"answers": answers}
