"""
A small FastAPI app that asks each question twice, without and with few-shot examples, and checks the format.

    GET / (or /index.html) -> index.html, a page with the questions and a table of answers
    GET /api/setup         -> {"system_prompt": "...", "examples": [...], "questions": [...]}   what the page shows
    POST /api/compare  body {"questions": ["What is a list?", ...]}   (1 to 10 questions)
                       ->  {"results": [{"question": "What is a list?",
                                         "without": "...", "without_ok": false,
                                         "with": "In one line: ...", "with_ok": true}, ...]}
                       a question Gemini didn't answer  ->  {"question": "...", "error": "Gemini didn't answer (...)."}
                       a bad list or question  ->  422, and no model call

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, StringConstraints

from hello import EXAMPLES, QUESTIONS, SYSTEM_PROMPT, chain, follows_format

app = FastAPI(title="AgenticProgramming project 14")
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class CompareIn(BaseModel):
    """1 to 10 questions. Each one is two Gemini calls, so 10 questions are 20 calls."""
    questions: list[Question] = Field(min_length=1, max_length=10)


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.get("/api/setup")
async def setup():
    """What the page shows before anything runs: the system prompt, the examples, and the default questions."""
    return {"system_prompt": SYSTEM_PROMPT, "examples": EXAMPLES, "questions": QUESTIONS}


@app.post("/api/compare")
async def compare(body: CompareIn):
    """Every question, without and with examples. At most 2 questions at a time, so at most 4 calls at once."""
    results = await chain.abatch(
        [{"question": q} for q in body.questions],
        config={"max_concurrency": 2},
        return_exceptions=True,          # one failed question becomes an error in its row, not a failed page
    )
    rows = []
    for question, answers in zip(body.questions, results):
        if isinstance(answers, Exception):
            logger.warning("Gemini call failed for %r: %s", question, answers)
            rows.append({"question": question, "error": f"Gemini didn't answer ({type(answers).__name__})."})
            continue
        rows.append({
            "question": question,
            "without": answers["without"], "without_ok": follows_format(answers["without"]),
            "with": answers["with"], "with_ok": follows_format(answers["with"]),
        })
    return {"results": rows}
