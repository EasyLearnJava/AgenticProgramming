"""
IT Knowledge Base: The Web App
==============================

Puts the API together: the routes, the error handlers, the trace middleware and the page's files, around an engine
it's handed. It builds nothing and calls nothing: main.py builds the engine first. It handles:
  1. The app's state: the settings, the engine and the trace store (None: traces aren't kept), which the routes read
  2. The order of the layers: trace middleware -> error handlers -> routes

Usage:
    app = create_app(settings, engine, trace_store)     # then uvicorn.run(app, ...), as main.py does
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.api.errors import register_error_handlers
from src.api.middleware import TraceMiddleware
from src.api.routes import STATIC_DIR, router
from src.config.settings import Settings
from src.observability.trace_store import TraceStore
from src.pipeline.rag_engine import RAGEngine


def create_app(settings: Settings, engine: RAGEngine, trace_store: TraceStore | None = None) -> FastAPI:
    """The FastAPI app around this engine; with a trace store, each API request's trace can be read back."""
    app = FastAPI(title=settings.app.name, summary="Answers IT questions from the knowledge base, with sources.")
    app.state.settings = settings
    app.state.engine = engine
    app.state.trace_store = trace_store
    register_error_handlers(app)
    app.add_middleware(TraceMiddleware)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
