"""
A small FastAPI app for hello.py's two experiments: three ways to answer, and a prompt before and after fixing it.

    GET / (or /index.html) -> index.html
    GET /api/setup         -> the questions, the three ways, and the two prompts with their anti-patterns
    POST /api/compare      -> {"rows": [...one per question, with a cell per way...], "summary": {...per way...}}
                              18 calls. Always a 200: a call that fails becomes an error in its own cell, and its
                              reason goes to this terminal
    POST /api/fix   body {"message": "hi, i ordered ..."}  ->  {"before": "...", "after": "..."}
                    a bad message (empty, or over 1,000 characters)  ->  422, and no model call
                    Gemini doesn't answer  ->  502, and the reason in this terminal

Start it with:   uvicorn main:app --reload
"""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

# The whole module, not names from it as in projects 13 to 15: the routes use many of its names. A route looks up
# hello.before_chain each time it runs, so the tests can swap it (and the other chains) for a stand-in in hello.
import hello

app = FastAPI(title="AgenticProgramming project 16")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"


class FixIn(BaseModel):
    """The JSON body: one customer message. Checked before any model call, so a bad one costs nothing."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  hi " -> "hi", and "   " -> "" (too short)

    message: str = Field(min_length=1, max_length=1000)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only calls this server's /api/... routes."""
    return FileResponse(PAGE)


@app.get("/api/setup")
async def setup():
    """What the page shows before any call: the questions, the three ways, both prompts and the anti-patterns."""
    return {
        "questions": hello.QUESTIONS,
        "ways": hello.WAYS,
        "before_prompt": hello.BEFORE_PROMPT,
        "after_system": hello.AFTER_SYSTEM,
        "after_prompt": hello.AFTER_PROMPT,
        "anti_patterns": hello.ANTI_PATTERNS,
        "sample_message": hello.SAMPLE_MESSAGE,
    }


@app.post("/api/compare")
async def compare():
    """Every question, three ways. The full reason for any failed call goes to this terminal, not the page."""
    rows = await hello.compare()
    for row in rows:
        for way, cell in row["ways"].items():
            if "error" in cell:
                detail = cell.pop("detail")          # take the full reason out: the page gets only the error type
                logger.warning("Gemini call failed (%s): %s", way, detail)
    return {"rows": rows, "summary": hello.summary(rows)}


@app.post("/api/fix")
async def fix(body: FixIn):
    """The same message, through the prompt with anti-patterns and through the fixed one, at the same time."""
    try:
        before, after = await asyncio.gather(
            hello.before_chain.ainvoke({"message": body.message}),
            hello.after_chain.ainvoke({"message": body.message}),
        )
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
    return {"before": before, "after": after}
