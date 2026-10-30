"""tests/unit/test_health.py: GET /api/health: up, with the build that answers, and never cached."""

from datetime import datetime

from fastapi.testclient import TestClient


def test_says_the_app_is_up_and_which_build_answers(client: TestClient) -> None:
    answer = client.get("/api/health")
    assert answer.status_code == 200
    body = answer.json()
    assert body["status"] == "ok"
    assert body["commit"] == "c7165ac"
    assert body["environment"] == "production"
    assert datetime.fromisoformat(body["checkedAt"]).tzinfo is not None


def test_is_never_cached(client: TestClient) -> None:
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_answers_head_as_uptime_monitors_send_it(client: TestClient) -> None:
    answer = client.head("/api/health")
    assert answer.status_code == 200
    assert answer.content == b""
