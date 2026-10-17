"""
A small FastAPI app for hello.py's two experiments: three ways to answer, and a prompt before and after fixing it.

    GET / (or /index.html) -> index.html
    GET /api/setup         -> the questions, the three ways, and the two prompts with their anti-patterns
    POST /api/compare      -> {"rows": [...one per question, with a cell per way...], "summary": {...per way...}}
                              18 calls; a call that fails becomes an error in its own cell
    POST /api/fix   body {"message": "hi, i ordered ..."}  ->  {"before": "...", "after": "..."}
                    a bad message  ->  422, and no model call
                    Gemini doesn't answer  ->  502

Start it with:   uvicorn main:app --reload
"""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

import hello

app = FastAPI(title="AgenticProgramming project 16")
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"


class FixIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.get("/api/setup")
async def setup():
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
                logger.warning("Gemini call failed (%s): %s", way, cell.pop("detail"))
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
