"""
IT Knowledge Base: Feedback on Answers
======================================

Keeps what users think of the answers, so real judgements can feed the evaluation set. It handles:
  1. Each answered request, kept for `keep_days` so it can be rated: its request ID, the caller, the question as asked
     and as searched, the answer, its status and the chunks it cites, the prompt's version and the model. The
     question is redacted first (the answer already is): nothing sensitive is kept
  2. A rating, thumbs up or down, with a comment (redacted too), for a request the same caller made; rating it again
     replaces the rating
  3. counts() for the stats, and rated(): the rated answers, to review and add to data/eval_questions.csv

    store.record("9f2c...", "chat-page", engine_answer, model="google/gemini-3.5-flash-lite")
    store.rate("9f2c...", "chat-page", "down", "It didn't cover Mac")   ->  True
"""
import json
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

from sensitive_data import redact

KEEP_DAYS = 30.0                     # the default: kb_settings.toml's [api] keep_answered_days can change it
DAY_SECONDS = 86_400


class FeedbackError(RuntimeError):
    """The feedback file can't be used; the message says why."""


class FeedbackStore:
    """Answered requests and their ratings, in SQLite."""

    def __init__(self, path: str | Path, *, keep_days: float = KEEP_DAYS, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.keep_days = keep_days
        self.clock = clock

    def record(self, request_id: str, caller: str, answered, *, model: str) -> None:
        """Keep an answered request (an EngineAnswer, from the chat model `model`) so it can be rated; answers past
        keep_days are deleted."""
        grounded = answered.answer
        now = self.clock()
        with self._connection() as db, db:
            db.execute("DELETE FROM answers WHERE answered_at < ?", (now - self.keep_days * DAY_SECONDS,))
            db.execute("INSERT OR REPLACE INTO answers (request_id, caller, question, asked, answer, status, cited, "
                       "prompt_version, model, cached, answered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (request_id, caller, redact(answered.question)[0], redact(answered.asked)[0], grounded.answer,
                        grounded.status, json.dumps(grounded.cited), grounded.prompt_version, model,
                        answered.cached, now))

    def rate(self, request_id: str, caller: str, rating: str, comment: str = "") -> bool:
        """Rate an answer the caller was given: True when it's kept, False when there's none with that ID for this
        caller (or it's older than keep_days)."""
        now = self.clock()
        with self._connection() as db, db:
            changed = db.execute("UPDATE answers SET rating = ?, comment = ?, rated_at = ? WHERE request_id = ? AND "
                                 "caller = ? AND answered_at >= ?",
                                 (rating, redact(comment)[0], now, request_id, caller,
                                  now - self.keep_days * DAY_SECONDS)).rowcount
        return changed == 1

    def counts(self) -> dict[str, int]:
        if not self.path.exists():
            return {"answers_kept": 0, "rated_up": 0, "rated_down": 0}
        with self._connection() as db:
            kept, up, down = db.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE rating = 'up'), COUNT(*) FILTER "
                                        "(WHERE rating = 'down') FROM answers").fetchone()
        return {"answers_kept": kept, "rated_up": up, "rated_down": down}

    def rated(self, rating: str | None = None) -> list[dict[str, Any]]:
        """The rated answers, newest first; only those rated `rating` ("up" or "down") when it's given."""
        if not self.path.exists():
            return []
        with self._connection() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT request_id, caller, question, asked, answer, status, cited, prompt_version, "
                              "model, rating, comment, rated_at FROM answers WHERE rating IS NOT NULL AND "
                              "(? IS NULL OR rating = ?) ORDER BY rated_at DESC", (rating, rating)).fetchall()
        return [{**dict(row), "cited": json.loads(row["cited"])} for row in rows]

    def _connection(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=10)
            db.execute("CREATE TABLE IF NOT EXISTS answers (request_id TEXT PRIMARY KEY, caller TEXT NOT NULL, "
                       "question TEXT NOT NULL, asked TEXT NOT NULL, answer TEXT NOT NULL, status TEXT NOT NULL, "
                       "cited TEXT NOT NULL, prompt_version TEXT NOT NULL, model TEXT NOT NULL, cached TEXT NOT NULL, "
                       "answered_at REAL NOT NULL, rating TEXT, comment TEXT, rated_at REAL)")
            db.execute("CREATE INDEX IF NOT EXISTS answered_at ON answers (answered_at)")
            return closing(db)
        except (sqlite3.Error, OSError) as err:
            raise FeedbackError(f"The feedback file can't be used ({err}): {self.path.resolve()}") from None
