"""Exercise the actual visitor signal, its visibility, privacy limits and the manual regression promotion."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from nimbus.feedback import answer_ref
from nimbus.observability import to_activity_requests
from tools import harness_review
from tools.harness_replay import run_intake_case

REVIEW = harness_review.REGRESSIONS / "zion-sunday-deadline.json"
TURN = "00abc12300def456"


@pytest.mark.parametrize("question", ["Will it rain in Paris?", "Plan a trip to Zion"])
def test_voluntary_feedback_matches_the_actual_answer(client: TestClient, question: str) -> None:
    with capture_logs() as lines:
        answer = client.post("/api/chat", data={"question": question})
        [turn] = re.findall(r'name="turn" value="([a-f0-9]{16})"', answer.text)
        assert 'action="/api/feedback"' in answer.text
        assert "public Activity log" in answer.text
        assert not any(row["event"] == "answer.feedback" for row in lines)
        response = client.post("/api/feedback", data={"turn": turn, "category": "trip-dates"})
    [signal] = [row for row in lines if row["event"] == "answer.feedback"]
    [ending] = [row for row in lines if row["event"] == "chat.done"]
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert signal["answerRef"] == ending["answerRef"] == answer_ref(turn)
    assert set(signal) - {"event", "category", "answerRef", "log_level", "requestId"} == set()
    assert question not in str(lines)
    assert turn not in str(lines)
    rows = [{"_time": "2026-11-06T17:00:00Z", "requestId": TURN, **signal}]
    [entry] = to_activity_requests([TURN], rows)
    assert entry.summary.detail == "Wrong trip dates or times"
    assert entry.answer_ref == answer_ref(turn)


@pytest.mark.parametrize(
    ("body", "headers", "status"),
    [
        (f"turn={TURN}&category=weather&question=private", {}, 400),
        (f"turn={TURN}&category=weather&category=weather", {}, 400),
        (f"turn={TURN}&category=private", {}, 400),
        ("turn=private&category=weather", {}, 400),
        (f"turn={TURN}&category=weather", {"origin": "https://foreign.example"}, 403),
        (f"turn={TURN}&category=weather", {"content-type": "application/json"}, 415),
        ("private" * 22, {}, 413),
    ],
)
def test_feedback_rejects_unconsented_content_before_logging(
    client: TestClient, body: str, headers: dict[str, str], status: int
) -> None:
    with capture_logs() as lines:
        response = client.post(
            "/api/feedback", content=body, headers={"content-type": "application/x-www-form-urlencoded", **headers}
        )
    assert response.status_code == status
    assert "private" not in response.text
    assert not any(row["event"] == "answer.feedback" for row in lines)
    assert "private" not in str(lines)


def test_public_feedback_is_rate_limited(client: TestClient) -> None:
    with capture_logs() as lines:
        for _ in range(12):
            assert client.post("/api/feedback", data={"turn": TURN, "category": "helpful"}).status_code == 200
        last = client.post("/api/feedback", data={"turn": TURN, "category": "safety"})
    assert last.status_code == 429
    assert last.headers["retry-after"] == "60"
    assert len([line for line in lines if line["event"] == "answer.feedback"]) == 12


def test_reviewed_failures_become_persistent_checked_regressions(tmp_path: Path) -> None:
    doc = json.loads(REVIEW.read_text(encoding="utf-8"))
    doc["case"]["case_id"] = "reviewed-return-mismatch"
    doc["case"]["expected"]["return_window"] = "morning"
    proposed = tmp_path / "draft.json"
    proposed.write_text(json.dumps(doc), encoding="utf-8")
    approved = harness_review.read_review(proposed)
    location = tmp_path / "regressions"
    harness_review.promote(approved, location)
    [case] = harness_review.reviewed_cases(location)
    result = run_intake_case(case)
    assert result["outcome"] != "pass"
    assert result["checks"] == ["return_window"]
    assert doc["case"]["question"] not in json.dumps(result)
    assert harness_review.main(["preview", str(proposed)]) == 1
    assert harness_review.main(["preview", str(REVIEW)]) == 0


def test_concurrent_promotions_publish_once_without_clobbering(tmp_path: Path) -> None:
    review = harness_review.read_review(REVIEW)
    ready = Barrier(2)

    def publish() -> bool:
        ready.wait()
        try:
            harness_review.promote(review, tmp_path)
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(publish) for _ in range(2)]
        assert sorted(future.result() for future in results) == [False, True]
    assert list(tmp_path.glob("*.tmp")) == []
    assert harness_review.reviewed_cases(tmp_path) == [review.case]


def test_review_import_fails_closed_without_printing_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    draft = tmp_path / "bad.json"
    draft.write_text('{"visitor_question":"private text"}', encoding="utf-8")
    assert harness_review.main(["promote", str(draft), "--synthetic"]) == 1
    assert "private text" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        harness_review.main(["promote", str(REVIEW)])
