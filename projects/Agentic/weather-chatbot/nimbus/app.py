"""
nimbus/app.py: builds the app: its settings and logging, the pages, the chat and the health check, our MCP server,
the files served beside them, and the middleware every request goes through. main.py calls create_app() once, when the
server starts.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from nimbus import chat, health, pages
from nimbus.answer import make_http_client
from nimbus.apify import make_apify_http_client
from nimbus.axiom import make_log_shipper
from nimbus.cache import make_weather_cache
from nimbus.config import Settings, get_settings
from nimbus.constants import DOCS_IMAGES_DIR, STATIC_DIR
from nimbus.logger import configure_logging
from nimbus.mcp_lane import make_mcp_http_client, to_self_mcp_url
from nimbus.mcp_server import make_mcp_server, to_routes
from nimbus.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from nimbus.model import make_chat_model, make_tracer
from nimbus.sentry import start_sentry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """While the app runs, so does the MCP server's session manager, which each MCP request needs (step 8)."""
    async with app.state.mcp_server.session_manager.run():
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """The app, with the given settings (a test's), else the environment's."""
    # ① The settings, checked, and the logging, set up before anything logs: each line also kept for Axiom, and each
    # error sent to Sentry, when they're set up (step 12).
    settings = settings or get_settings()
    log_shipper = make_log_shipper(settings)
    configure_logging(settings, log_shipper)
    sentry_on = start_sentry(settings)
    # ② The app, without FastAPI's own API pages: /docs is our documentation, and the API isn't public.
    app = FastAPI(title="Nimbus", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    # The model that answers, made once: None on a deployment without its key, where the chat says it isn't set up;
    # and LangSmith's client, when it may trace, which hides every run's inputs and outputs.
    # One line says how this copy of the app starts: the model, whether it's set up, whether LangSmith may trace,
    # whether Axiom and Sentry are on, and the cache's store: AsyncBuildCache, ours, else the package's own.
    app.state.chat_model = make_chat_model(settings)
    app.state.tracer = make_tracer(settings)
    # How each answer's weather tools reach Open-Meteo: a new HTTP client for each, and one cache for Open-Meteo's
    # answers (step 7); the tests give their own.
    app.state.make_http_client = make_http_client
    app.state.weather_cache = make_weather_cache(settings)
    # And on the MCP lane (step 9), where its tools find our MCP server, and a new HTTP client for each answer's calls.
    app.state.to_mcp_url = to_self_mcp_url
    app.state.make_mcp_http_client = make_mcp_http_client
    # And on the lanes with auth (step 10), a new HTTP client for each answer's calls to Apify.
    app.state.make_apify_http_client = make_apify_http_client
    # And the health check's runs (step 12), one through each address, each answering it for a minute.
    app.state.health_runs = {}
    structlog.get_logger().info(
        "app.started",
        model=settings.gemini_model,
        modelSetUp=app.state.chat_model is not None,
        tracing=app.state.tracer is not None,
        axiom=log_shipper is not None,
        sentry=sentry_on,
        cacheStore=type(app.state.weather_cache.store).__name__,
    )
    # ③ The routes: the pages, the chat and the health check; and our MCP server's, with the same tools (step 8).
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(health.router)
    app.state.mcp_server = make_mcp_server(app.state)
    app.router.routes.extend(to_routes(app.state.mcp_server, settings))
    # ④ The files beside them: the docs' pictures, and, on a computer only, the stylesheet. On Vercel, its CDN serves
    # public/ itself, with the headers vercel.json gives it; Vercel's docs say never to mount public/ there.
    app.mount("/docs/images", StaticFiles(directory=DOCS_IMAGES_DIR), name="docs-images")
    if not settings.is_vercel:
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # ⑤ A missing page gets our own 404 page.
    app.add_exception_handler(StarletteHTTPException, pages.http_error_response)
    # ⑥ Every request: its id and its log line, its lines to Axiom and any error to Sentry, then, outermost, the
    # security headers on its response.
    app.add_middleware(RequestContextMiddleware, log_shipper=log_shipper, is_vercel=settings.is_vercel)
    app.add_middleware(SecurityHeadersMiddleware)
    return app
