"""
A small FastAPI app that answers one question for two audiences, using hello.py's two system prompts.

    GET / (or /index.html) -> index.html, a page with a question box and two answers side by side
    GET /api/prompts       -> {"beginner": "You are a patient teacher ...", "expert": "You are a senior ..."}
    POST /api/ask    body {"question": "What is an API?"}  ->  {"beginner": "...", "expert": "..."}
                     an empty or too long question  ->  422, and no model call
                     Gemini doesn't answer  ->  502, and the reason in this terminal

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import SYSTEM_PROMPTS, chain

app = FastAPI(title="AgenticProgramming project 13")
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"


class AskIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=200)


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.get("/api/prompts")
async def prompts():
    """The two system prompts, so the page can show what each answer was told to do."""
    return SYSTEM_PROMPTS


@app.post("/api/ask")
async def ask(body: AskIn):
    """Two Gemini calls at the same time: one per system prompt, the same question in both."""
    try:
        return await chain.ainvoke({"question": body.question})
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
