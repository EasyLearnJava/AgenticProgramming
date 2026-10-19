"""
A small FastAPI app that streams hello.py's Gemini chain to the page, piece by piece.

    GET / (or /index.html) -> index.html, a page that shows the answer as it arrives
    POST /api/hello  body {"name": "Asha"}  ->  plain text, sent in pieces as Gemini writes them
                     a bad name  ->  422, and no model call
                     Gemini fails before the first piece  ->  502, and the reason in this terminal
                     Gemini fails part-way through  ->  the text so far, then a line saying it stopped

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from hello import chain

app = FastAPI(title="AgenticProgramming project 12")
logger = logging.getLogger("uvicorn.error")        # prints in the same terminal as uvicorn's own messages

PAGE = Path(__file__).resolve().parent / "index.html"
STOPPED = "\n\n[Gemini stopped before the end of the answer.]"   # added to the text when it breaks off part-way


class HelloIn(BaseModel):
    """The JSON body: one name. Checked before the model is called, so a bad name costs nothing."""
    model_config = ConfigDict(str_strip_whitespace=True)   # "  Asha " -> "Asha", and "   " -> "" (too short)

    name: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It has no key: it only sends a name to /api/hello."""
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Streams the answer. The first piece is fetched before replying, so an early failure can still be a 502."""
    pieces = chain.astream({"name": body.name})          # nothing runs yet: this only sets up the stream

    # ① Wait for the first piece. StreamingResponse sends the status (200) and the headers as soon as it starts,
    #    before it asks for any text, and after that the status can't change. So a failure here, like a bad key,
    #    is the last chance to answer with a proper 502.
    #    anext() is the async version of next(): it runs the chain until Gemini sends its first piece.
    #    The "" is what we get if there are no pieces at all: an empty reply, rather than a 502.
    try:
        first = await anext(pieces, "")
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err

    # ② The whole answer, as an async generator (an `async def` with `yield`): the first piece, then the rest.
    #    StreamingResponse asks it for one piece at a time and sends each one to the page as soon as it's yielded.
    async def first_then_the_rest():
        yield first
        try:
            async for piece in pieces:
                yield piece
        except Exception as err:                         # it failed part-way: say so at the end of the text
            logger.warning("Gemini stopped part-way: %s", err)
            yield STOPPED

    # ③ StreamingResponse sends each yielded piece as soon as it's ready, instead of waiting for the end.
    #    The two headers are for proxies on the way, such as Codespaces' port forwarding:
    #    X-Accel-Buffering: no asks a proxy to pass each piece on at once (nginx reads this one), and
    #    Cache-Control: no-cache says no cache may hand this reply out again without asking the server.
    return StreamingResponse(
        first_then_the_rest(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
