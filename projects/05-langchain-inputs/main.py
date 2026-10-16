"""
A small FastAPI app that serves hello.py's chain over HTTP, now with three inputs: a greeting, a name and a city.

    GET / (or /index.html) -> index.html, a page with a greeting list and name and city boxes
    POST /api/hello  body {"greeting": "Good morning", "name": "Raghu", "city": "Dallas"}
                     -> {"answer": "Good morning Raghu from Dallas, welcome to LangChain!"}
                     leave "greeting" out -> the prompt's default, "Hello"
                     any bad field -> 422, with one error per bad field

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 5")

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """The JSON body the page sends. FastAPI checks every field before hello() runs; each bad one gets its own error."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    greeting: Literal["Hello", "Good morning", "Namaste"] | None = None   # only these three; left out -> default
    name: str = Field(min_length=1, max_length=40)
    city: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/hello") needs no full address."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain with the fields from the request body and returns its answer."""
    # exclude_none drops a greeting that wasn't sent, so the prompt's partial fills in "Hello".
    answer = await chain.ainvoke(body.model_dump(exclude_none=True))
    return {"answer": answer}
