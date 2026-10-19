"""
A small FastAPI app that serves hello.py's chain over HTTP, the way production apps run LangChain (on a server).

    GET / (or /index.html) -> index.html, a page with a button; each click calls /api/hello once
    GET /api/hello -> {"answer": "Hello World, welcome to LangChain!"}

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from hello import chain

app = FastAPI(title="AgenticProgramming project 3")

PAGE = Path(__file__).resolve().parent / "index.html"


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/hello") needs no full address."""
    return FileResponse(PAGE)


@app.get("/api/hello")
async def hello():
    """Runs the chain with no input and returns its answer."""
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({})
    return {"answer": answer}
