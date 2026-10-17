"""
A small FastAPI app that serves hello.py's two structured-output chains.

    GET / (or /index.html) -> index.html, a page with a greeting form and a support-message form
    GET /api/setup         -> {"languages": ["English", ...], "sample_message": "hi, i ordered ..."}
    POST /api/greet   body {"name": "Asha", "language": "Hindi"}
                      ->  {"message": "...", "language": "Hindi", "emoji": "🙏", "tone": "warm"}
    POST /api/triage  body {"message": "hi, i ordered ..."}
                      ->  {"intent": "...", "category": "billing", "urgency": "high", "route_to_team": "billing_team"}
                      a bad input  ->  422, and no model call
                      Gemini doesn't answer, or answers with data that doesn't fit the schema  ->  502

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import LANGUAGES, SAMPLE_MESSAGE, Greeting, Language, Ticket, greet_chain, triage_chain

app = FastAPI(title="AgenticProgramming project 15")
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"


class GreetIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)
    language: Language


class TriageIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.get("/api/setup")
async def setup():
    return {"languages": LANGUAGES, "sample_message": SAMPLE_MESSAGE}


async def run(chain, inputs):
    """Runs a chain; any failure, including an answer that doesn't fit the schema, becomes a 502."""
    try:
        return await chain.ainvoke(inputs)
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err


# response_model: FastAPI sends the Greeting object as JSON, and /docs shows its exact shape.
@app.post("/api/greet", response_model=Greeting)
async def greet(body: GreetIn):
    return await run(greet_chain, body.model_dump())


@app.post("/api/triage", response_model=Ticket)
async def triage(body: TriageIn):
    return await run(triage_chain, body.model_dump())
