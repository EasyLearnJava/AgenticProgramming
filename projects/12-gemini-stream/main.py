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
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"
STOPPED = "\n\n[Gemini stopped before the end of the answer.]"


class HelloIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.post("/api/hello")
async def hello(body: HelloIn):
    """Streams the answer. The first piece is fetched before replying, so an early failure can still be a 502."""
    pieces = chain.astream({"name": body.name})          # nothing runs yet: this only sets up the stream

    # ① Wait for the first piece. Once the reply starts, its status (200) is already sent and can't become a 502,
    #    so a failure here, like a bad key, is the last chance to say "Gemini didn't answer" properly.
    try:
        first = await anext(pieces, "")
    except Exception as err:
        logger.warning("Gemini call failed: %s", err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err

    # ② The rest: an async generator. Each `yield` sends one more piece to the page, right away.
    async def the_rest():
        yield first
        try:
            async for piece in pieces:
                yield piece
        except Exception as err:                         # it failed part-way: say so at the end of the text
            logger.warning("Gemini stopped part-way: %s", err)
            yield STOPPED

    # ③ StreamingResponse sends each yielded piece as soon as it's ready, instead of waiting for the end.
    #    The two headers ask browsers and proxies (like Codespaces' port forwarding) not to hold pieces back.
    return StreamingResponse(
        the_rest(),
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
