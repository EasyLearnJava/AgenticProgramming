"""Gemini-independent official-notice cards; execution uses a bounded POST under the existing API firewall scope."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from nimbus.forms import read_form_fields
from nimbus.nps_alerts import PARKS, NpsAlertsService, ParkId
from nimbus.pages import render_page
from nimbus.retrieval_gate import RetrievalGate

router = APIRouter()


class AlertsInput(BaseModel):
    """Only one known park may be selected; no question, arbitrary URL or API key is accepted."""

    model_config = ConfigDict(extra="forbid")
    park: ParkId = "zion"


@router.get("/parks/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request) -> HTMLResponse:
    """Display a selector without spending NPS quota on page loads or crawler requests."""
    if request.query_params:
        raise HTTPException(400, "Use the park selector")
    return await render_alerts(request, AlertsInput(), run=False)


@router.post("/api/parks/alerts", response_class=HTMLResponse)
async def check_alerts(request: Request) -> HTMLResponse:
    """Validate the small form and reserve request capacity before opening an upstream connection."""
    # ① Reject foreign forms and bound their bytes and fields before reserving upstream request capacity.
    fields = AlertsInput()
    try:
        try:
            fields = AlertsInput.model_validate(await read_form_fields(request, max_bytes=1024, max_fields=1))
        except ValidationError:
            raise HTTPException(400, "Choose a supported park") from None
        gate: RetrievalGate = request.app.state.alerts_gate
        async with gate.reserve(request.client.host if request.client else "unknown"):
            return await render_alerts(request, fields, run=True)
    except HTTPException as error:
        messages = {
            400: "Choose a supported park.",
            403: "Checks must come from this site.",
            413: "The park selection is too large.",
            415: "Submit the park selector.",
            429: "Too many park alert checks. Please wait a minute and try again."
            if (error.headers or {}).get("retry-after") == "60"
            else "Park alert checks are busy. Please try again shortly.",
        }
        response = await render_alerts(
            request, fields, run=False, error_message=messages[error.status_code], status_code=error.status_code
        )
        response.headers.update(error.headers or {})
        return response


async def render_alerts(
    request: Request,
    fields: AlertsInput,
    *,
    run: bool,
    error_message: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Render public reports and explicit missing-configuration states without exposing credentials."""
    # ② Keep the canonical menu selection after POST, and never cache credential-dependent reports at the CDN.
    service: NpsAlertsService = request.app.state.nps_alerts
    enabled = request.app.state.settings.parks_enabled
    report = None
    if enabled:
        report = (
            await service.get(fields.park, tool="park_alerts") if run else service.configuration_report(fields.park)
        )
    response = render_page(
        request,
        "park_alerts.html",
        {
            "parks": PARKS,
            "selection": fields.park,
            "report": report,
            "enabled": enabled,
            "menu_path": "/parks/alerts",
            "error_message": error_message,
        },
        status_code=status_code,
    )
    response.headers["cache-control"] = "no-store"
    return response
