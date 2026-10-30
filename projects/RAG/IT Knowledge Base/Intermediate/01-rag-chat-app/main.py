"""
IT Knowledge Base: The RAG Chat App
===================================

The app's one way in. It checks the settings and the API key, sets up logging, and builds the engine (reads and
chunks the knowledge base, loads the chunks' saved vectors or embeds them, and stores them, under a trace ID of its
own); then it serves the chat page and the API, or answers questions in the terminal. It handles:
  1. The command line: serve (the default), ask or index, with --config and --log-level before any of them
  2. Stopping with one clear line and exit code 1 when the settings, the key, the data or a provider fails at
     start-up: a problem you can fix isn't shown as a traceback (an unexpected error is, in the log)
  3. The trace store, when serving with tracing.enabled on: each API request's log lines, kept for the page, and the
     build's, kept for good. The log file is the server's: ask and index log to the console only
  4. Serving with uvicorn under the app's logging: uvicorn's own access log is off, since the app logs each request
     with its trace ID
  5. `app`, for a host that imports this file rather than running it (Vercel, or uvicorn main:app): importing builds
     nothing; the same start-up runs when the host starts the app (its lifespan), and if it fails, the host's start
     fails, with the reason in the host's log. On Vercel, which sets VERCEL, the log goes to the console only
  6. index: the chunks embedded once, and their vectors saved in embeddings.vector_file for each start-up to load
     instead. Vercel's build runs it (vercel.json): if it fails, it exits 1, and the deployment stops there. A start
     on Vercel with no saved vectors logs a warning: each instance would embed the chunks

Usage:
    python main.py                               # serve the chat page and the API at http://127.0.0.1:8000
    python main.py ask                           # answer the sample questions in the terminal
    python main.py ask "printer not found"       # answer your own question
    python main.py --log-level DEBUG ask "vpn"   # also log the question, the answer and each chunk found
    python main.py index                         # embed the chunks once and save their vectors, for each start-up
    uvicorn main:app                             # serve main.py's app, started the way Vercel starts it
"""
import argparse
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import SecretStr

from src.api.app import attach, create_app
from src.config.settings import CONFIG_FILE, Settings, load_api_key, load_settings
from src.exceptions import AppError, ConfigError
from src.observability.logging_setup import setup_logging
from src.observability.trace_store import TraceStore
from src.observability.tracing import trace_context
from src.pipeline.factory import create_engine
from src.pipeline.rag_engine import RAGEngine
from src.utils.helpers import print_result

logger = logging.getLogger("main")


class StartUpError(Exception):
    """The start-up failed, and why is already printed or logged: whoever started it only has to stop."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The command and its options; with none, the server."""
    parser = argparse.ArgumentParser(
        description="The IT Knowledge Base RAG chat app: serve the chat page and the API, ask in the terminal, or "
                    "index: embed the chunks once and save their vectors.")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE,
                        help="the settings file (default: config.yaml, next to main.py)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="overrides logging.level in the settings file; DEBUG adds each question, answer and "
                             "chunk found")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.add_parser("serve", help="serve the chat page and the API (the default)")
    ask_parser = commands.add_parser("ask", help="answer questions in the terminal")
    ask_parser.add_argument("question", nargs="*",
                            help="your question; with none, the sample questions in the settings file")
    commands.add_parser("index", help="embed the chunks and save their vectors in embeddings.vector_file, for each "
                                      "start-up to load instead (Vercel's build runs it)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Check, set up and build, then serve or answer; or, for index, embed the chunks and save their vectors. Returns
    the exit code: 0 (a server stopped with Ctrl+C included: it shut down cleanly), 1 if something failed, 130 if
    Ctrl+C stopped the build, a question or the indexing."""
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):          # a character the console can't show is escaped, not a crash
            stream.reconfigure(errors="backslashreplace")
    if args.command == "index":
        return index(args.config, log_level=args.log_level)

    # Steps 1 to 3: the settings and the key, logging, and the engine's build; start_up() says why if one fails
    try:
        settings, engine, trace_store = start_up(args.config, log_level=args.log_level,
                                                 serving=args.command != "ask")
    except StartUpError:
        return 1
    except KeyboardInterrupt:
        return 130

    # Step 4: Answer in the terminal, or serve
    if args.command == "ask":
        question = " ".join(args.question).strip()
        return ask(engine, [question] if question else settings.app.sample_questions)
    serve(create_app(settings, engine, trace_store), settings.api.host, settings.api.port)
    return 0


def start_up(config: Path, *, log_level: str | None = None,
             serving: bool = True) -> tuple[Settings, RAGEngine, TraceStore | None]:
    """
    Steps 1 to 3, the same for python main.py and for a host: prepare() (the settings and the key; logging, and the
    trace store when serving), then the engine, built under a trace ID of its own. Returns the settings, the built
    engine and the trace store (None: traces aren't kept).

    Raises:
        StartUpError: the settings, the key, the log file or the build failed; why is already printed (when logging
            isn't set up yet) or logged (under the build's trace ID)
        KeyboardInterrupt: Ctrl+C stopped the build (logged)
    """
    settings, api_key, trace_store = prepare(config, log_level=log_level, serving=serving)

    # Step 3: Build the engine, under a trace of its own: the page shows it as how the knowledge base was built
    with trace_context() as build_trace_id:
        if trace_store is not None:
            trace_store.pin(build_trace_id)
        vector_file = settings.embeddings.vector_file
        if os.getenv("VERCEL") and vector_file and not vector_file.exists():
            logger.warning("No saved vectors on Vercel (%s): each instance embeds the chunks as it starts, and "
                           "instances starting together can use up Gemini's quota. vercel.json has the build save "
                           "them with python main.py index", vector_file)
        try:
            engine = create_engine(settings, api_key)
            engine.build()
        except AppError as err:
            logger.error("Start-up failed: %s: %s", err.code, err)
            raise StartUpError(f"{err.code}: {err}") from None
        except KeyboardInterrupt:
            logger.warning("Start-up stopped (Ctrl+C)")
            raise
        except Exception as err:
            logger.exception("Start-up failed with an unexpected error")
            raise StartUpError(f"an unexpected error: {type(err).__name__}") from None
        logger.info("Engine ready", extra=engine.stats())
    return settings, engine, trace_store


def prepare(config: Path, *, log_level: str | None = None,
            serving: bool = True) -> tuple[Settings, SecretStr, TraceStore | None]:
    """
    Steps 1 and 2, for every command and for a host: the settings and the key; then logging, and the trace store when
    serving. Returns the settings, the key and the trace store (None: traces aren't kept).

    Raises:
        StartUpError: the settings, the key or the log file can't be used; why is already printed (logging isn't set
            up yet)
    """
    # Step 1: The settings and the key, checked before anything runs; logging isn't set up yet, so a problem is printed
    try:
        settings = load_settings(config)
        api_key = load_api_key()
    except ConfigError as err:
        print(f"Can't start: {err}", file=sys.stderr)
        raise StartUpError(str(err)) from None
    if log_level:
        logging_settings = settings.logging.model_copy(update={"level": log_level})
        settings = settings.model_copy(update={"logging": logging_settings})

    # Step 2: Logging, with the key masked in every line; and the trace store, for the page, when serving. The log
    # file is the server's: ask and index log to the console only, so two never write (and rotate) one file at once. On
    # Vercel (it sets VERCEL) there's no file either: a deployment's files are read-only, and Vercel keeps the console
    trace_store = (TraceStore(max_traces=settings.tracing.max_traces, secrets=[api_key])
                   if serving and settings.tracing.enabled else None)
    log_settings = settings.logging
    if not serving or os.getenv("VERCEL"):
        log_settings = log_settings.model_copy(update={"file": None})
    try:
        setup_logging(log_settings, secrets=[api_key], trace_store=trace_store)
    except OSError as err:
        reason = f"the log file can't be opened ({err.strerror}): {err.filename}"
        print(f"Can't start: {reason}", file=sys.stderr)
        raise StartUpError(reason) from None
    return settings, api_key, trace_store


def ask(engine: RAGEngine, questions: list[str]) -> int:
    """Answer each question in the terminal, each under a trace ID of its own. Stops at the first that fails."""
    for question in questions:
        with trace_context() as trace_id:
            try:
                result = engine.query(question)
            except AppError as err:
                logger.error("Couldn't answer: %s: %s", err.code, err)
                return 1
            except KeyboardInterrupt:
                logger.warning("Stopped (Ctrl+C)")
                return 130
            except Exception:
                logger.exception("Couldn't answer: an unexpected error")
                return 1
        print_result(question, result, trace_id)
    return 0


def index(config: Path, *, log_level: str | None = None) -> int:
    """python main.py index: Steps 1 and 2, then the chunks embedded and their vectors saved in embeddings.vector_file,
    under a trace ID of its own. Returns the exit code: 0; 1 if something failed (on Vercel, the deployment then
    stops); 130 if Ctrl+C stopped it."""
    try:
        settings, api_key, _ = prepare(config, log_level=log_level, serving=False)
    except StartUpError:
        return 1
    except KeyboardInterrupt:
        return 130
    with trace_context():
        try:
            saved = create_engine(settings, api_key).index()
        except AppError as err:
            logger.error("Indexing failed: %s: %s", err.code, err)
            return 1
        except KeyboardInterrupt:
            logger.warning("Indexing stopped (Ctrl+C)")
            return 130
        except Exception:
            logger.exception("Indexing failed with an unexpected error")
            return 1
        logger.info("Vectors saved: each start-up loads them instead of embedding the chunks",
                    extra={"chunks": saved, "file": str(settings.embeddings.vector_file)})
    return 0


def serve(app: FastAPI, host: str, port: int) -> None:
    """Run the server until Ctrl+C. log_config=None keeps the app's logging; access_log=False leaves each request's
    line to the trace middleware, which knows its trace ID."""
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """The start-up, when a host starts the app: the same steps as python main.py's, with config.yaml. A failure
    stops the host's start, so the app never answers without its engine; why is already in the host's log."""
    settings, engine, trace_store = start_up(CONFIG_FILE)
    attach(app, settings, engine, trace_store)
    yield


# For a host that imports this file and serves `app` (Vercel looks for it here): importing builds nothing, since the
# lifespan above does the start-up. python main.py doesn't use it: main() builds first, then serves an app of its own
app = create_app(lifespan=lifespan)


if __name__ == "__main__":
    sys.exit(main())
