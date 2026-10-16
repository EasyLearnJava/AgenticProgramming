"""
A small FastAPI app that serves hello.py's chain over HTTP: one name in, four results out.

    GET / (or /index.html) -> index.html, a page with a name box that shows all four results
    POST /api/hello  body {"name": "Raghu"}
                     -> {"original": "Hello Raghu, welcome to LangChain!", "upper": "HELLO RAGHU, WELCOME TO LANGCHAIN!",
                         "length": 34, "shout": "HELLO RAGHU, WELCOME TO LANGCHAIN!!!"}
                     an empty, blank or 41+ character name -> 422
    GET /api/graph   -> {"mermaid": "graph TD; ..."}, the chain's shape as a Mermaid diagram

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 6")

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """The JSON body the page sends. FastAPI checks it before hello() runs; a bad one gets a 422."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Raghu " -> "Raghu", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/...") calls need no full address."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain with the name and returns its dict as is: original, upper, length and shout."""
    # ainvoke() is invoke()'s async twin; inside the chain, the three side-by-side steps run concurrently.
    return await chain.ainvoke({"name": body.name})


@app.get("/api/graph")
async def graph():
    """The chain's shape, drawn by LangChain itself as Mermaid text."""
    return {"mermaid": chain.get_graph().draw_mermaid()}
