"""
IT Knowledge Base: The Trace Middleware
=======================================

Wraps every HTTP request: the outermost layer of the app's own code. It handles:
  1. A new trace for each request, so every log line written while answering it, in any module, carries its ID; the
     API's requests are kept in the trace store, the page's own files, the health checks and trace reads aren't
  2. One log line when the request ends (method, path, status and duration: the server's access log), written just
     before the response's last bytes go out, so a trace read right after holds it
  3. Headers on every response: X-Trace-ID, so a caller can quote it or read the trace; and security headers, and
     no-cache unless the route set its own caching
  4. The last line of defence: an error nothing else handled is logged with its traceback, and answered with a 500
     in the one error shape, never with the error's text

A plain ASGI middleware rather than Starlette's BaseHTTPMiddleware: it sees every response, errors included, and
adds no task of its own between the request and the route.
"""
import logging
import time

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.errors import error_response
from src.exceptions import AppError
from src.observability.tracing import trace_context
from src.utils.helpers import elapsed_ms

logger = logging.getLogger(__name__)

TRACE_HEADER = "X-Trace-ID"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",    # a file is only ever read as the type it's sent as
    "X-Frame-Options": "DENY",              # no other site can show these pages in a frame
    "Referrer-Policy": "no-referrer",       # links out don't tell other sites which page they came from
}
# Load balancers ask these every few seconds: their lines are DEBUG, so they don't drown the others
QUIET_PATH_PREFIXES = ("/health/",)
# The trace store keeps the API's requests; reading a trace isn't kept, or each read would push out a real one
RECORDED_PATH_PREFIX = "/api/"
TRACES_PATH_PREFIX = "/api/v1/traces/"


class TraceMiddleware:
    """Gives each HTTP request its own trace, logs how it ended, and adds the trace ID and security headers."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":           # the server's start-up and shut-down messages
            await self.app(scope, receive, send)
            return

        method, path = scope["method"], scope["path"]
        recorded = path.startswith(RECORDED_PATH_PREFIX) and not path.startswith(TRACES_PATH_PREFIX)
        with trace_context(recorded=recorded) as trace_id:
            start = time.perf_counter()
            status_code: int | None = None
            finished = False
            logger.debug("Request started", extra={"method": method, "path": path})

            def log_finished() -> None:
                nonlocal finished
                finished = True
                level = logging.DEBUG if path.startswith(QUIET_PATH_PREFIXES) else logging.INFO
                logger.log(level, "Request finished", extra={"method": method, "path": path,
                                                              "status_code": status_code or 500,
                                                              "duration_ms": elapsed_ms(start)})

            async def send_with_headers(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    headers = MutableHeaders(scope=message)
                    headers[TRACE_HEADER] = trace_id
                    for name, value in SECURITY_HEADERS.items():
                        headers.setdefault(name, value)
                    headers.setdefault("Cache-Control", "no-cache")
                elif message["type"] == "http.response.body" and not message.get("more_body") and not finished:
                    log_finished()            # before the last bytes go: the caller can't read the trace sooner
                await send(message)

            try:
                await self.app(scope, receive, send_with_headers)
            except Exception:
                logger.exception("Unhandled error", extra={"method": method, "path": path})
                if status_code is not None:   # the response has started: nothing more can be sent
                    raise
                response = error_response(500, AppError.code, AppError.public_message)
                await response(scope, receive, send_with_headers)
            finally:
                if not finished:              # the response never finished: the caller left, or it broke off
                    log_finished()
