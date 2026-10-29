"""
IT Knowledge Base: The Web App
==============================

Puts the API together: the routes, the error handlers, the trace middleware and the page's files, around an engine
it's handed. It builds nothing and calls nothing: main.py builds the engine, either before it makes the app (python
main.py) or in the app's start-up, its lifespan (main.py's app, for a host that imports it). It handles:
  1. The app's state: the settings, the engine and the trace store (None: traces aren't kept), which the routes read
  2. The order of the layers: trace middleware -> error handlers -> routes

Usage:
    app = create_app(settings, engine, trace_store)     # then uvicorn.run(app, ...), as python main.py does
    app = create_app(lifespan=lifespan)                 # the lifespan builds the engine, then calls attach()
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.types import Lifespan

from src.api.errors import register_error_handlers
from src.api.middleware import TraceMiddleware
from src.api.routes import STATIC_DIR, router
from src.config.settings import Settings
from src.observability.trace_store import TraceStore
from src.pipeline.rag_engine import RAGEngine


def create_app(settings: Settings | None = None, engine: RAGEngine | None = None,
               trace_store: TraceStore | None = None, *, lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    """The FastAPI app around this engine; with a trace store, each API request's trace can be read back. Made with
    no engine, it gets one at start-up: its lifespan must attach() the settings, the engine and the trace store."""
    app = FastAPI(summary="Answers IT questions from the knowledge base, with sources.", lifespan=lifespan)
    if settings is not None and engine is not None:
        attach(app, settings, engine, trace_store)
    register_error_handlers(app)
    app.add_middleware(TraceMiddleware)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def attach(app: FastAPI, settings: Settings, engine: RAGEngine, trace_store: TraceStore | None = None) -> None:
    """Hand the app what its routes read: the settings, the engine and the trace store; and its title, for /docs."""
    app.title = settings.app.name
    app.state.settings = settings
    app.state.engine = engine
    app.state.trace_store = trace_store
