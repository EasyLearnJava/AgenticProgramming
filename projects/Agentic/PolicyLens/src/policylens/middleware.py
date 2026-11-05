"""Bound request bodies before the multipart parser can spool oversized uploads."""

from starlette.responses import JSONResponse
import logging

from policylens.diagnostics import log_exception

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_BODY = MAX_FILE_BYTES + 64 * 1024  # Bounded multipart headers/boundary overhead.


class SafeErrorsMiddleware:
    """Handle unexpected exceptions before Starlette can re-raise them to uvicorn."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, ended = False, False

        async def safe_send(message):
            nonlocal started, ended
            if message["type"] == "http.response.start":
                started = True
                message = {**message, "headers": list(message.get("headers", [])) + [
                    (b"x-frame-options", b"DENY"), (b"content-security-policy", b"frame-ancestors 'none'")]}
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                ended = True
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception as error:
            log_exception(logging.getLogger("policylens"), "HTTP request failed", error)
            if not started:
                await JSONResponse({"detail": "The request failed. Check the server configuration and retry."}, 503)(scope, receive, safe_send)
            elif not ended:
                await safe_send({"type": "http.response.body", "body": b"", "more_body": False})
            # Deliberately handled: do not re-raise private exception messages to uvicorn.


class RequestBodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        upload = scope["path"].rstrip("/") == "/api/documents"
        limit = MAX_UPLOAD_BODY if upload else 64 * 1024
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length."}, 400)(scope, receive, send)
        if declared > limit:
            return await JSONResponse({"detail": "Request is too large. Files are limited to 10 MB."}, 413)(scope, receive, send)
        # Enforce actual bytes too: missing/false Content-Length must not bypass the cap.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            part = message.get("body", b"")
            if len(body) + len(part) > limit:
                return await JSONResponse({"detail": "Request is too large. Files are limited to 10 MB."}, 413)(scope, receive, send)
            body.extend(part)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

