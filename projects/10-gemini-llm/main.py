"""
A small FastAPI app that serves hello.py's Gemini chain over HTTP.

    GET / (or /index.html) -> index.html, a page with a name box and a button
    POST /api/hello  body {"name": "Raghu"}  ->  {"answer": "Welcome, Raghu! ..."}   written by Gemini, new each time
                     a bad name (empty, or over 40 characters)  ->  422, and no model call
                     Gemini doesn't answer (bad key, quota, network)  ->  502, and the reason in this terminal

The key stays here: the page sends a name, this server calls Gemini with the key, and only the answer goes back.
Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 10")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """The JSON body: one name. Checked before the model is called, so a bad name costs nothing."""
    # model_config holds Pydantic's settings for this class: nothing to do with the Gemini model.
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Asha " -> "Asha", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only sends a name to /api/hello."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Runs the chain once: one real call to Gemini."""
    try:
        # ainvoke() is invoke()'s async twin (project 4): while Gemini writes, the server can serve other requests.
        answer = await chain.ainvoke({"name": body.name})
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns that the model didn't answer.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
    return {"answer": answer}
