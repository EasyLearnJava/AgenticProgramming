"""
Tests for feedback.py: an answered request is kept, redacted, and can be rated by the caller it was given to, while
it's kept; rating again replaces the rating; old answers are deleted; the counts and the rated answers are read back;
and a file that isn't a database is named.
"""
from types import SimpleNamespace

import pytest

from feedback import DAY_SECONDS, FeedbackError, FeedbackStore


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def answered(question: str = "My VPN keeps timing out", answer: str = "Open UDP 500 and 4500.") -> SimpleNamespace:
    """What FeedbackStore reads of an EngineAnswer."""
    grounded = SimpleNamespace(answer=answer, status="answered", cited=["kb-1:resolution:a"],
                               prompt_version="answer-v1")
    return SimpleNamespace(question=question, asked=question, answer=grounded, cached="")


def test_an_answer_is_rated_by_its_own_caller_and_rating_again_replaces_it(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3", clock=Clock())
    store.record("r1", "chat-page", answered(), model="fake/m")
    assert store.rate("r1", "chat-page", "up") and store.rate("r1", "chat-page", "down", "Not for Mac")
    assert not store.rate("r1", "reports", "up") and not store.rate("r2", "chat-page", "up")
    assert store.counts() == {"answers_kept": 1, "rated_up": 0, "rated_down": 1}
    (row,) = store.rated("down")
    assert (row["request_id"], row["comment"], row["cited"], row["model"]) == (
        "r1", "Not for Mac", ["kb-1:resolution:a"], "fake/m")
    assert store.rated("up") == []


def test_nothing_sensitive_is_kept(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3", clock=Clock())
    store.record("r1", "chat-page", answered("I'm jane.doe@example.com, my VPN times out"), model="fake/m")
    store.rate("r1", "chat-page", "down", "call me on 555-010-0142")
    (row,) = store.rated()
    assert row["question"] == "I'm [REDACTED:EMAIL], my VPN times out" and row["comment"] == "call me on " \
                                                                                           "[REDACTED:PHONE]"


def test_an_answer_older_than_keep_days_cant_be_rated_and_is_deleted(tmp_path):
    clock = Clock()
    store = FeedbackStore(tmp_path / "feedback.sqlite3", keep_days=2, clock=clock)
    store.record("old", "chat-page", answered(), model="fake/m")
    clock.now += 3 * DAY_SECONDS
    assert not store.rate("old", "chat-page", "up")
    store.record("new", "chat-page", answered(), model="fake/m")
    assert store.counts()["answers_kept"] == 1


def test_with_no_file_yet_there_is_nothing(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.sqlite3")
    assert (store.counts(), store.rated()) == ({"answers_kept": 0, "rated_up": 0, "rated_down": 0}, [])


def test_a_file_that_isnt_a_database_is_named(tmp_path):
    path = tmp_path / "feedback.sqlite3"
    path.write_text("not a database", encoding="utf-8")
    with pytest.raises(FeedbackError, match="The feedback file can't be used"):
        FeedbackStore(path).counts()
