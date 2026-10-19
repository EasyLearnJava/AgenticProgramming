"""
A small FastAPI app that serves hello.py's two structured-output chains.

    GET / (or /index.html) -> index.html, a page with a greeting form and a support-message form
    GET /api/setup         -> {"languages": ["English", ...], "sample_message": "hi, i ordered ..."}
    POST /api/greet   body {"name": "Asha", "language": "Hindi"}
                      ->  {"message": "...", "language": "Hindi", "emoji": "🙏", "tone": "warm"}
    POST /api/triage  body {"message": "hi, i ordered ..."}
                      ->  {"intent": "...", "category": "billing", "urgency": "high", "route_to_team": "billing_team"}
    Both POSTs:       a bad input  ->  422, and no model call
                      Gemini doesn't answer, or its answer doesn't fit the schema  ->  502, the reason in this terminal

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import LANGUAGES, SAMPLE_MESSAGE, Greeting, Language, Ticket, greet_chain, triage_chain

app = FastAPI(title="AgenticProgramming project 15")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"


class GreetIn(BaseModel):
    """The greeting form's JSON body. Checked before the model is called, so a bad one costs nothing."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Asha " -> "Asha", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)
    language: Language                  # the same Literal as Greeting.language: "Klingon" gets a 422, before any call


class TriageIn(BaseModel):
    """The support message to sort. Checked before the model is called, so a bad one costs nothing."""
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only calls this server's /api/... routes."""
    return FileResponse(PAGE)


@app.get("/api/setup")
async def setup():
    """What the page needs when it opens: the languages for its dropdown, and the sample message."""
    return {"languages": LANGUAGES, "sample_message": SAMPLE_MESSAGE}


async def run(chain, inputs):
    """Runs a chain; any failure, including an answer that doesn't fit the schema, becomes a 502."""
    try:
        return await chain.ainvoke(inputs)
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns the error's type.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err


# response_model=Greeting: /docs shows the answer's exact shape, taken from the Greeting class.
# (FastAPI would send the returned object as the same JSON without it.)
@app.post("/api/greet", response_model=Greeting)
async def greet(body: GreetIn):
    """One welcome, as a Greeting object: one real call to Gemini."""
    return await run(greet_chain, body.model_dump())      # {"name": "Asha", "language": "Hindi"}: the prompt's inputs


@app.post("/api/triage", response_model=Ticket)
async def triage(body: TriageIn):
    """The message, sorted into a Ticket object: one real call to Gemini."""
    return await run(triage_chain, body.model_dump())     # {"message": "..."}
