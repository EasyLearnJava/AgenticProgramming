"""
A small FastAPI app that checks the Gemini key at start-up, and tells the page only whether it is set.

    GET / (or /index.html) -> index.html, a page that asks the server about the key
    GET /api/status        -> {"key_set": true}       never the key itself
    no key at start-up     -> the server doesn't start, and says why

The key stays on the server: it is read here, kept in a variable, and never put in a response or in the page.
Start it with:   uvicorn main:app --reload
"""
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from config import MissingKeyError, load_api_key

# ① The fail-fast check, when this module is imported at server start: no key, no server.
try:
    GOOGLE_API_KEY = load_api_key()          # project 10 hands this to Gemini; nothing here sends it anywhere
except MissingKeyError as err:
    sys.exit(f"Can't start the server: {err}")

app = FastAPI(title="AgenticProgramming project 9")

PAGE = Path(__file__).resolve().parent / "index.html"


@app.get("/")
@app.get("/index.html")
async def page():
    """The page. It holds no key: it only asks /api/status."""
    return FileResponse(PAGE)


@app.get("/api/status")
async def status():
    """Says the key is set. If it weren't, the server wouldn't be running to answer."""
    return {"key_set": True}
