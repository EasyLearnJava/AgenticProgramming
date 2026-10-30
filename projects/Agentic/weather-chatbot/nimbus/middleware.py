"""
nimbus/middleware.py: what every request the app answers goes through. Both are plain ASGI middleware, not Starlette's
BaseHTTPMiddleware: each message the app sends passes through as it is, so a streamed answer (step 2) streams, with
its request's log context.
"""

import time

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from nimbus.constants import REQUEST_ID_HEADER, SECURITY_HEADERS, VERCEL_ID_HEADER
from nimbus.utils import to_request_id

MS_PER_SECOND = 1000
HTTP_SERVER_ERROR = 500


class RequestContextMiddleware:
    """
    Gives each request its id, puts the id on every line it logs and on its response, and logs one line when it ends:
    the method, the path (never the query string, which can hold what a user typed), the status and the time it took.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the app."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Runs one HTTP request through the app, with its id; anything else (the app's startup) passes as it is."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # ① The request's id: Vercel's own, when it looks like one, else a new one.
        request_id = to_request_id(Headers(scope=scope).get(VERCEL_ID_HEADER))
        status = HTTP_SERVER_ERROR
        error_class: str | None = None
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            """Sends a message on, the response's start with the request's id in a header."""
            nonlocal status
            # ② The id goes back to the browser, in a header of the response.
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        # ③ Every line this request logs carries its id, and no other request's.
        with structlog.contextvars.bound_contextvars(requestId=request_id):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception as error:
                error_class = type(error).__name__
                raise
            finally:
                # ④ One line when the request ends, however it ends; a failure that reached here says its class.
                fields = {
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "ms": round((time.perf_counter() - started) * MS_PER_SECOND),
                }
                log = structlog.get_logger()
                if error_class is None:
                    log.info("http.request", **fields)
                else:
                    log.error("http.request", **fields, errorClass=error_class)


class SecurityHeadersMiddleware:
    """Adds the security headers (constants.SECURITY_HEADERS) to every response the app makes."""

    def __init__(self, app: ASGIApp) -> None:
        """Wraps the app."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Runs one HTTP request through the app, adding the headers to its response; anything else passes as it is."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            """Sends a message on, the response's start with the security headers."""
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
