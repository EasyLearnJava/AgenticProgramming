"""
A small FastAPI app that serves hello.py's chain over HTTP, and the page that shows it.

    GET / (or /index.html) -> index.html, a page that calls /api/hello as soon as it opens and shows the answer
    GET /api/hello -> {"answer": "Hello World, welcome to LangChain!"}

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload   ->   Uvicorn running on http://127.0.0.1:8000
Open that address: the page shows Hello World, welcome to LangChain!
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

# Importing hello runs hello.py from the top: ① to ③ build the chain, once, when the server starts; ④ is skipped.
from hello import chain

# ⑤ The app: `uvicorn main:app` serves this object. Its functions below run only when a request comes in.
app = FastAPI(title="AgenticProgramming project 2")

# ⑥ The page. Path(__file__).resolve().parent is the folder this file is in, and `/` on a Path adds a name to it.
#    A bare "index.html" would be looked for in whatever folder the server or the tests were started from.
PAGE = Path(__file__).resolve().parent / "index.html"


@app.get("/")              # two decorators on one function: the page answers at both addresses
@app.get("/index.html")
async def page():
    """The page. Served by this same server, so its fetch("/api/hello") needs no full address."""
    # no-cache: the browser must ask the server again before reusing its saved copy of this page. The other FastAPI
    # projects here use port 8000 too, so without it this page could show up while one of them runs.
    return FileResponse(PAGE, headers={"Cache-Control": "no-cache"})


# ⑦ The chain's address: each GET /api/hello runs the chain once.
@app.get("/api/hello")
async def hello():
    """Runs the chain with no input and returns its answer."""
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({})
    return {"answer": answer}
