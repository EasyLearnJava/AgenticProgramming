"""
A small FastAPI app that serves hello.py's chain over HTTP, the way production apps run LangChain (on a server).

    GET /api/hello -> {"answer": "Hello World, welcome to LangChain!", "python": "3.13.x",
                       "langchain_core": "1.x", "server_ms": 0.42}

The chain is built once, when this module is imported at server start. Each request only runs it.
Start it with:   uvicorn main:app --reload
"""
import platform
import time
from importlib.metadata import version

from fastapi import FastAPI

from hello import chain

app = FastAPI(title="AgenticProgramming project 2")


@app.get("/api/hello")
async def hello():
    """Runs the chain with no input and returns its answer, plus what ran it and how long it took."""
    start = time.perf_counter()
    # ainvoke() is invoke()'s async twin: the server can serve other requests while this one waits.
    answer = await chain.ainvoke({})
    server_ms = round((time.perf_counter() - start) * 1000, 2)
    return {"answer": answer, "python": platform.python_version(), "langchain_core": version("langchain-core"),
            "server_ms": server_ms}
