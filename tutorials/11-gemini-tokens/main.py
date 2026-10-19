"""
A small FastAPI app that serves hello.py's measured Gemini call over HTTP.

    GET / (or /index.html) -> index.html, a page with a name box, a max-tokens box and a table of every call
    POST /api/hello  body {"name": "Asha", "max_output_tokens": 10}
                     ->  {"answer": "Welcome, Asha! LangChain", "finish_reason": "MAX_TOKENS", "counted_tokens": 21,
                          "input_tokens": 21, "output_tokens": 10, "thinking_tokens": 0, "latency_ms": 610,
                          "cost_usd": 3.13e-05}
                          (made-up example: Gemini's words and numbers change from call to call)
                     a bad name or max_output_tokens  ->  422, and no model call
                     Gemini doesn't answer  ->  502, and the reason in this terminal

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import MAX_OUTPUT_TOKENS, ask

app = FastAPI(title="AgenticProgramming project 11")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    """The JSON body: a name, and how many output tokens this call may use (10 to 200)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)
    # ge / le: greater than or equal to, less than or equal to. Anything outside 10 to 200 is a 422.
    max_output_tokens: int = Field(default=MAX_OUTPUT_TOKENS, ge=10, le=MAX_OUTPUT_TOKENS)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only sends a name and a cap to /api/hello."""
    return FileResponse(PAGE)


# A plain `def`, not `async def`: ask() makes ordinary (blocking) calls, so FastAPI runs this in a worker thread
# and the server stays free for other requests meanwhile.
@app.post("/api/hello")
def hello(body: HelloIn):
    """Counts the prompt's tokens, calls Gemini once, and returns the answer with its numbers."""
    try:
        return ask(body.name, body.max_output_tokens)
    except Exception as err:
        # The full reason goes to the server's terminal; the page only learns that the model didn't answer.
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
