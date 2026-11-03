"""
nimbus/goldens.py: the golden questions (step 13), and the last run of them kept beside them (step 14). tools/evals.py
asks them and, with --save, keeps its run in evals/last-run.json; the Evaluations page shows both. Each is checked as
it's read.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

from nimbus.constants import GOLDEN_FILE, LAST_RUN_FILE


class Expect(BaseModel):
    """A golden answer's required tools, forbidden tools, wording and citation targets."""

    tools: list[str] = Field(default_factory=list)
    no_tools: list[str] = Field(default_factory=list)
    says: list[str] = Field(default_factory=list)
    never_says: list[str] = Field(default_factory=list)
    cites: list[str] = Field(default_factory=list)
    only_cites: list[str] = Field(default_factory=list)


class Golden(BaseModel):
    """One golden question: its id, its words, the browser's language and time zone, the lane, and what's expected."""

    id: str
    question: str
    locale: str = "en-US"
    time_zone: str = "America/Chicago"
    lane: str = "rest-no-auth"
    expect: Expect


class GoldenResult(BaseModel):
    """How one golden question went in a run: whether it passed, the tools it called, and what it missed."""

    id: str
    passed: bool
    tools: list[str]
    misses: list[str]


class LastRun(BaseModel):
    """
    A run of the golden questions, as kept: the build that answered, when, and each result; never the address asked,
    which could name a preview and its team, in a file the public repository keeps.
    """

    commit: str | None
    ran_at: datetime
    results: list[GoldenResult]


GOLDENS = TypeAdapter(list[Golden])


def read_goldens(path: Path = GOLDEN_FILE) -> list[Golden]:
    """The golden questions, checked as they're read."""
    return GOLDENS.validate_json(path.read_bytes())


def read_last_run(path: Path = LAST_RUN_FILE) -> LastRun | None:
    """The last run kept, checked as it's read; None when no run has been kept."""
    if not path.is_file():
        return None
    return LastRun.model_validate_json(path.read_bytes())
