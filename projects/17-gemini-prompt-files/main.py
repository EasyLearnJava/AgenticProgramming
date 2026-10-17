"""
A small FastAPI app that serves the greeting from its versioned prompt files, and says which version answered.

    GET / (or /index.html) -> index.html
    GET /api/prompts       -> {"active": "v3", "versions": {"v1": {"system": ..., "human": ..., "fingerprint": ...}, ...}}
    POST /api/hello  body {"name": "Asha"}                  ->  {"answer": "...", "prompt": "greeting",
                                                                 "version": "v3", "fingerprint": "c27b3feb"}
                     body {"name": "Asha", "version": "v1"}  ->  the same, with v1 (to compare versions)
                     a bad name or an unknown version  ->  422, and no model call
                     Gemini doesn't answer  ->  502

Start it with:   uvicorn main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

import hello

app = FastAPI(title="AgenticProgramming project 17")
logger = logging.getLogger("uvicorn.error")

PAGE = Path(__file__).resolve().parent / "index.html"


class HelloIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=40)
    version: str | None = None                 # leave it out to use the active version

    @field_validator("version")
    @classmethod
    def known_version(cls, version):
        if version is not None and version not in hello.GREETINGS:
            raise ValueError(f"no such version: the versions are {', '.join(hello.GREETINGS)}")
        return version


@app.get("/")
@app.get("/index.html")
async def page():
    return FileResponse(PAGE)


@app.get("/api/prompts")
async def prompts():
    """Every version's text and fingerprint, and which one is active."""
    return {
        "active": hello.ACTIVE,
        "versions": {v: {"system": p.system, "human": p.human, "fingerprint": p.fingerprint}
                     for v, p in hello.GREETINGS.items()},
    }


@app.post("/api/hello")
async def say_hello(body: HelloIn):
    version = body.version or hello.ACTIVE
    try:
        result = await hello.greet(body.name, version)
    except Exception as err:
        logger.warning("Gemini call failed (greeting %s): %s", version, err)
        raise HTTPException(status_code=502, detail=f"Gemini didn't answer ({type(err).__name__}).") from err
    # A one-line record of every answer and the exact prompt behind it, in the server's terminal.
    logger.info("answered with prompt %s %s (%s)", result["prompt"], result["version"], result["fingerprint"])
    return result
