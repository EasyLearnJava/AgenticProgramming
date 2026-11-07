"""
IT Knowledge Base: The API Server
=================================

Serves the API (api.py) on the knowledge base pipeline.py stored, and looks after its keys and its feedback. It
handles:
  1. serve (the default): the settings read and checked, logging set up (JSON lines by default), the engine built on
     the store, then the server started on [api] host and port; with no API key yet, it stops and says how to add one
  2. add-key NAME: a new API key for a caller, shown once; only its hash is kept, in [api] keys_file
  3. feedback: how the answers were rated, and the ones rated down, to review and add to data/eval_questions.csv

Usage:
    python pipeline.py                     # first: load the knowledge base into the store
    python main.py add-key chat-page       # a key for each caller
    python main.py                         # then serve it: http://127.0.0.1:8000/docs
    python main.py feedback --csv data/rated_down.csv
"""
import argparse
import csv
import logging
import sys
from pathlib import Path

import uvicorn

from config import MissingKeyError, load_api_key
from embedding import EmbeddingError
from feedback import FeedbackError, FeedbackStore
from knowledge_base_loader import MANIFEST_FILE, SETTINGS_FILE
from observability import setup_logging
from security import ApiKeys, KeysError, add_key
from settings import load_settings
from vector_store import StoreError
from wiring import from_folder, make_api

logger = logging.getLogger("main")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the IT knowledge base's API, add a caller's key, or read the "
                                                 "feedback on its answers.")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE,
                        help="the settings, [api] among them (default: kb_settings.toml)")
    parser.add_argument("--manifest-path", type=Path, default=MANIFEST_FILE,
                        help="the manifest pipeline.py wrote: the knowledge base's version (default: "
                             "data/manifest.json)")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="serve the API (the default)")
    adding = commands.add_parser("add-key", help="make a new API key for a caller, and show it once")
    adding.add_argument("name", help="the caller: 1 to 40 letters, digits, - or _ (e.g. chat-page)")
    reading = commands.add_parser("feedback", help="how the answers were rated; the ones rated down")
    reading.add_argument("--csv", type=Path, help="also write the answers rated down to this CSV file")
    return parser.parse_args(argv)


def serve(args: argparse.Namespace) -> int:
    settings = load_settings(args.settings)
    secrets = [load_api_key().get_secret_value()] if "google" in (settings.embeddings.provider,
                                                                 settings.answer.provider) else []
    setup_logging(settings.api.log_level, settings.api.log_format, secrets=secrets)
    keys_file = from_folder(settings.api.keys_file, args.settings)
    if not len(ApiKeys.load(keys_file)):
        logger.error("No API key yet, so no one could call the API: add one with python main.py add-key NAME "
                     "(it goes in %s)", keys_file)
        return 1
    app = make_api(settings, args.settings, manifest_path=args.manifest_path)
    # uvicorn keeps the logging set up above (log_config=None), and the app writes the access lines itself
    uvicorn.run(app, host=settings.api.host, port=settings.api.port, log_config=None, access_log=False)
    return 0


def add(args: argparse.Namespace) -> int:
    settings = load_settings(args.settings)
    keys_file = from_folder(settings.api.keys_file, args.settings)
    key = add_key(keys_file, args.name)
    print(f"A new API key for {args.name}. It's shown only now: keep it somewhere safe (only its hash is kept, in "
          f"{keys_file}).\nSend it as: Authorization: Bearer <key>\n")
    print(key)
    return 0


def show_feedback(args: argparse.Namespace) -> int:
    settings = load_settings(args.settings)
    store = FeedbackStore(from_folder(settings.api.feedback_path, args.settings),
                          keep_days=settings.api.keep_answered_days)
    counts = store.counts()
    print(f"Feedback: {counts['answers_kept']} answers kept (for {settings.api.keep_answered_days:g} days), "
          f"{counts['rated_up']} rated up, {counts['rated_down']} rated down")
    down = store.rated("down")
    for row in down:
        comment = f": {row['comment']}" if row["comment"] else ""
        print(f"  {row['request_id']} ({row['status']}, cited {len(row['cited'])}) {row['asked']}{comment}")
    if down:
        print("Review them: a question the knowledge base should answer belongs in data/eval_questions.csv, with "
              "the article that answers it")
    if args.csv is not None:
        with open(args.csv, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=["request_id", "question", "asked", "status", "answer", "cited",
                                                      "comment", "prompt_version", "model"], extrasaction="ignore")
            writer.writeheader()
            writer.writerows({**row, "cited": " ".join(row["cited"])} for row in down)
        print(f"Wrote {len(down)} to {args.csv}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    command = {"add-key": add, "feedback": show_feedback}.get(args.command, serve)
    try:
        return command(args)
    except (FileNotFoundError, ValueError, MissingKeyError, KeysError, StoreError, EmbeddingError,
            FeedbackError) as err:
        logging.basicConfig(format="%(levelname)s %(message)s")
        logger.error("%s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
