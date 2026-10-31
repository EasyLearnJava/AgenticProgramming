"""
nimbus/app.py: builds the app: its settings and logging, the pages, the chat and the health check, the files served
beside them, and the middleware every request goes through. main.py calls create_app() once, when the server starts.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from nimbus import chat, health, pages
from nimbus.config import Settings, get_settings
from nimbus.constants import DOCS_IMAGES_DIR, STATIC_DIR
from nimbus.logger import configure_logging
from nimbus.middleware import RequestContextMiddleware, SecurityHeadersMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """The app, with the given settings (a test's), else the environment's."""
    # ① The settings, checked, and the logging, set up before anything logs.
    settings = settings or get_settings()
    configure_logging(settings)
    # ② The app, without FastAPI's own API pages: /docs is our documentation, and the API isn't public.
    app = FastAPI(title="Nimbus", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    # ③ The routes: the pages, the chat and the health check.
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(health.router)
    # ④ The files beside them: the docs' pictures, and, on a computer only, the stylesheet. On Vercel, its CDN serves
    # public/ itself, with the headers vercel.json gives it; Vercel's docs say never to mount public/ there.
    app.mount("/docs/images", StaticFiles(directory=DOCS_IMAGES_DIR), name="docs-images")
    if not settings.is_vercel:
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    # ⑤ A missing page gets our own 404 page.
    app.add_exception_handler(StarletteHTTPException, pages.http_error_response)
    # ⑥ Every request: its id and its log line, then, outermost, the security headers on its response.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    return app
