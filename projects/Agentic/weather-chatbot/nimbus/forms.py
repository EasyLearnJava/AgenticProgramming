"""Shared bounded form I/O; pure origin, URL and field validation stays in utils.py."""

from fastapi import HTTPException, Request

from nimbus.utils import checked_form_fields, is_same_origin


async def read_form_fields(request: Request, *, max_bytes: int, max_fields: int) -> dict[str, str]:
    """Check headers before reading a bounded body; never echo submitted values or accept duplicate fields."""
    # ① Both public inspection forms share these checks, with their own small byte and field budgets.
    if not is_same_origin(request.headers.get("origin"), str(request.url)):
        raise HTTPException(403, "Requests must come from this site")
    if request.headers.get("content-type", "").partition(";")[0].lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Submit a URL-encoded form")
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > max_bytes:
            raise HTTPException(413, "The submitted form is too large")
    try:
        return checked_form_fields(bytes(body), max_fields=max_fields)
    except ValueError:
        raise HTTPException(400, "Invalid form input") from None
