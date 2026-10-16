"""
A small FastAPI app that serves hello.py's chain over HTTP, now with one input: a name.

    GET / (or /index.html) -> index.html, a page with a name box; each click sends the name to /api/hello
    POST /api/hello  body {"name": "Raghu"}  -> {"answer": "Hello Raghu, welcome to LangChain!"}
                     an empty, blank or 41+ character name -> 422 with FastAPI's error details

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 4")

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """The JSON body the page sends. FastAPI checks it before hello() runs; a bad one gets a 422."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/hello") needs no full address."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain with the name from the request body and returns its answer."""
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({"name": body.name})
    return {"answer": answer}
