"""
A small FastAPI app that answers one question for two audiences, using hello.py's two system prompts.

    GET / (or /index.html) -> index.html, a page with a question box and a table: each system prompt above its answer
    GET /api/prompts       -> {"beginner": "You are a patient teacher ...", "expert": "You are a senior ..."}
    POST /api/ask    body {"question": "What is an API?"}  ->  {"beginner": "...", "expert": "..."}
                     an empty, blank or 201+ character question  ->  422, and no model call
                     Gemini doesn't answer (bad key, quota, network)  ->  502, and the reason in this terminal
                     (one of the two calls failing is enough: then neither answer comes back)

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import SYSTEM_PROMPTS, chain

app = FastAPI(title="AgenticProgramming project 13")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"


class AskIn(BaseModel):
    """The JSON body: one question. Checked before the model is called, so a bad question costs nothing."""
    # Spaces at either end are trimmed first: " What is an API? " -> "What is an API?", and "   " -> "" (too short).
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=200)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only calls this server's /api/prompts and /api/ask."""
    return FileResponse(PAGE)


@app.get("/api/prompts")
async def system_prompts():
    """The two system prompts, so the page can show what each answer was told to do."""
    return SYSTEM_PROMPTS


@app.post("/api/ask")
async def ask(body: AskIn):
    """Two Gemini calls at the same time: one per system prompt, the same question in both."""
    try:
        return await chain.ainvoke({"question": body.question})
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns that the model didn't answer.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
