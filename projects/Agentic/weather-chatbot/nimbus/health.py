"""
nimbus/health.py: GET /api/health: whether the app is up, and which build is answering. In step 1 that's all it
checks; step 12 adds a check of each lane's way out (Open-Meteo, our MCP server, Apify). It answers HEAD too, which
uptime monitors often send.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from nimbus.config import Settings
from nimbus.constants import NO_STORE
from nimbus.utils import to_iso

router = APIRouter()


@router.api_route("/api/health", methods=["GET", "HEAD"])
def health(request: Request) -> JSONResponse:
    """The app's health: "ok" whenever it can answer, with the time and the build; never cached."""
    settings: Settings = request.app.state.settings
    body = {
        "status": "ok",
        "checkedAt": to_iso(datetime.now(UTC)),
        "commit": settings.commit,
        "environment": settings.environment,
    }
    return JSONResponse(body, headers={"cache-control": NO_STORE})
