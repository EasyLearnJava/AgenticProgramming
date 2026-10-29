"""
IT Knowledge Base: The API's Errors
===================================

Turns every failure into the one error shape, with the request's trace ID, and logs it once. It handles:
  1. AppError: its code, status and public message to the caller; the detail to the log (and so to the request's
     trace, while traces are kept): INFO for a 4xx, WARNING when trying again may work, else ERROR with its traceback
  2. A request FastAPI refuses (422): each field and why, logged at INFO (the caller's mistake, not the server's),
     without the values sent
  3. Starlette's own HTTP errors, such as 404 and 405, in the same shape
  4. error_response(): the shape itself; the middleware uses it too, for an error nothing else handled (500)
"""
import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.schemas import ErrorBody, ErrorDetail, ErrorResponse
from src.exceptions import AppError
from src.observability.tracing import current_trace_id

logger = logging.getLogger(__name__)


def error_response(status_code: int, code: str, message: str, *, retryable: bool = False,
                   details: list[ErrorDetail] | None = None, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """The one error shape, with the trace ID of the request it answers."""
    body = ErrorResponse(error=ErrorBody(code=code, message=message, trace_id=current_trace_id(),
                                         retryable=retryable, details=details))
    return JSONResponse(body.model_dump(exclude_none=True), status_code=status_code, headers=headers)


async def handle_app_error(request: Request, err: AppError) -> JSONResponse:
    fields = {"code": err.code, "status_code": err.status_code, "error": str(err)}
    if err.status_code < 500:   # the caller's mistake, such as a trace that isn't kept
        logger.info("Request failed: %s", err.code, extra=fields)
    elif err.retryable:         # a busy or slow provider, or the engine not built yet: no traceback needed
        logger.warning("Request failed: %s", err.code, extra=fields)
    else:
        logger.error("Request failed: %s", err.code, extra=fields, exc_info=err)
    return error_response(err.status_code, err.code, err.public_message, retryable=err.retryable)


async def handle_validation_error(request: Request, err: RequestValidationError) -> JSONResponse:
    details = [ErrorDetail(field=_field_name(problem["loc"]), message=problem["msg"]) for problem in err.errors()]
    logger.info("Request refused: INVALID_REQUEST", extra={"fields": [detail.field for detail in details]})
    message = "The request isn't valid: " + "; ".join(f"{detail.field}: {detail.message}" for detail in details)
    return error_response(422, "INVALID_REQUEST", message, details=details)


async def handle_http_error(request: Request, err: StarletteHTTPException) -> JSONResponse:
    # HTTPStatus names the status: 404 -> NOT_FOUND, 405 -> METHOD_NOT_ALLOWED
    return error_response(err.status_code, HTTPStatus(err.status_code).name, str(err.detail), headers=err.headers)


def _field_name(location: tuple) -> str:
    """Where a problem is: ("body", "question") -> "question"; the whole body (missing, or not JSON) -> "body"."""
    parts = list(location)
    if len(parts) > 1 and parts[0] == "body" and isinstance(parts[1], str):
        parts = parts[1:]
    elif parts and parts[0] == "body":
        parts = ["body"]
    return ".".join(str(part) for part in parts)


def register_error_handlers(app: FastAPI) -> None:
    """Every handler above, on the app."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
