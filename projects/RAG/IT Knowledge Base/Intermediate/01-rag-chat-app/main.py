"""
IT Knowledge Base: The RAG Chat App
===================================

The app's one way in. It checks the settings and the API key, sets up logging, and builds the engine (reads, chunks,
embeds and stores the knowledge base, under a trace ID of its own); then it serves the chat page and the API, or
answers questions in the terminal. It handles:
  1. The command line: serve (the default) or ask, with --config and --log-level before either
  2. Stopping with one clear line and exit code 1 when the settings, the key, the data or a provider fails at
     start-up: a problem you can fix isn't shown as a traceback (an unexpected error is, in the log)
  3. The trace store, when serving with tracing.enabled on: each API request's log lines, kept for the page, and the
     build's, kept for good. The log file is the server's: ask logs to the console only
  4. Serving with uvicorn under the app's logging: uvicorn's own access log is off, since the app logs each request
     with its trace ID

Usage:
    python main.py                               # serve the chat page and the API at http://127.0.0.1:8000
    python main.py ask                           # answer the sample questions in the terminal
    python main.py ask "printer not found"       # answer your own question
    python main.py --log-level DEBUG ask "vpn"   # also log the question, the answer and each chunk found
"""
import argparse
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from src.api.app import create_app
from src.config.settings import CONFIG_FILE, load_api_key, load_settings
from src.exceptions import AppError, ConfigError
from src.observability.logging_setup import setup_logging
from src.observability.trace_store import TraceStore
from src.observability.tracing import trace_context
from src.pipeline.factory import create_engine
from src.pipeline.rag_engine import RAGEngine
from src.utils.helpers import print_result

logger = logging.getLogger("main")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The command and its options; with none, the server."""
    parser = argparse.ArgumentParser(
        description="The IT Knowledge Base RAG chat app: serve the chat page and the API, or ask in the terminal.")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Check, set up and build, then serve or answer. Returns the exit code: 0 (a server stopped with Ctrl+C included:
    it shut down cleanly), 1 if something failed, 130 if Ctrl+C stopped the build or a question."""
    args = parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):          # a character the console can't show is escaped, not a crash
            stream.reconfigure(errors="backslashreplace")

    # Step 1: The settings and the key, checked before anything runs; logging isn't set up yet, so a problem is printed
    try:
        settings = load_settings(args.config)
        api_key = load_api_key()
    except ConfigError as err:
        print(f"Can't start: {err}", file=sys.stderr)
        return 1
    if args.log_level:
        logging_settings = settings.logging.model_copy(update={"level": args.log_level})
        settings = settings.model_copy(update={"logging": logging_settings})

    # Step 2: Logging, with the key masked in every line; and the trace store, for the page, when serving. The log
    # file is the server's: ask logs to the console only, so the two never write (and rotate) one file at once
    serving = args.command != "ask"
    trace_store = (TraceStore(max_traces=settings.tracing.max_traces, secrets=[api_key])
                   if serving and settings.tracing.enabled else None)
    log_settings = settings.logging if serving else settings.logging.model_copy(update={"file": None})
    try:
        setup_logging(log_settings, secrets=[api_key], trace_store=trace_store)
    except OSError as err:
        print(f"Can't start: the log file can't be opened ({err.strerror}): {err.filename}", file=sys.stderr)
        return 1

    # Step 3: Build the engine, under a trace of its own: the page shows it as how the knowledge base was built
    with trace_context() as build_trace_id:
        if trace_store is not None:
            trace_store.pin(build_trace_id)
        try:
            engine = create_engine(settings, api_key)
            engine.build()
        except AppError as err:
            logger.error("Start-up failed: %s: %s", err.code, err)
            return 1
        except KeyboardInterrupt:
            logger.warning("Start-up stopped (Ctrl+C)")
            return 130
        except Exception:
            logger.exception("Start-up failed with an unexpected error")
            return 1
        logger.info("Engine ready", extra=engine.stats())

    # Step 4: Answer in the terminal, or serve
    if args.command == "ask":
        question = " ".join(args.question).strip()
        return ask(engine, [question] if question else settings.app.sample_questions)
    serve(create_app(settings, engine, trace_store), settings.api.host, settings.api.port)
    return 0


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


def serve(app: FastAPI, host: str, port: int) -> None:
    """Run the server until Ctrl+C. log_config=None keeps the app's logging; access_log=False leaves each request's
    line to the trace middleware, which knows its trace ID."""
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)


if __name__ == "__main__":
    sys.exit(main())
