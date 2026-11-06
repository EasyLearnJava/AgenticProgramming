"""A green scorecard requires every expected trial on the same build. No service credentials are needed."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nimbus import harness_scorecard
from nimbus.harness_scorecard import Attempt, Build, ProviderCall, Scorecard, load_report, release_errors
from tools.harness import origin, save

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)
REV = "a" * 40
DEPLOYMENT = "dpl_TestDeploy"


def sample(*, live: bool = False, mixed: bool = False) -> Scorecard:
    rows = [
        Attempt(
            suite="golden" if live else "weekend",
            case_id=case,
            attempt=trial,
            outcome="timeout" if mixed and case == "timing-dfw-fri" and trial == 2 else "pass",
            duration_ms=10 * trial,
            provider_calls=[ProviderCall(provider="kiwi", status="timeout" if trial == 2 else "found")] if live else [],
        )
        for case in ("timing-dfw-fri", "typo-lax-sat")
        for trial in range(1, 4 if live else 2)
    ]
    return Scorecard(
        mode="live" if live else "replay",
        profile="full",
        started_at=NOW,
        finished_at=NOW,
        source=Build(commit=REV, dirty=False, environment="ci"),
        target=Build(commit=REV, deployment=DEPLOYMENT, environment="preview") if live else None,
        repeats=3 if live else 1,
        attempts=rows,
    )


def test_scorecard_measures_each_attempt_and_preserves_service_failures(tmp_path: Path) -> None:
    card = sample(live=True, mixed=True)
    path = tmp_path / "result.json"
    save(card, path)
    loaded = load_report(path)
    assert loaded == card
    [suite] = loaded.suites()
    assert (suite.first_pass, suite.all_three, suite.p50_ms, suite.p95_ms) == (2, 1, 20, 30)
    assert suite.failures == {"timeout": 1}
    assert card.providers() == {"kiwi": {"found": 4, "timeout": 2}}
    assert card.summary()["tokens"] is None
    assert card.summary()["provider_incomplete_fraction"] == {"kiwi": 0.3333}
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["summary"]["passed"] = True
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="summary"):
        load_report(path)


def test_duplicate_or_incomplete_trials_cannot_inflate_passes() -> None:
    data = sample(live=True).model_dump()
    for wrong in (data["attempts"][:-1], [data["attempts"][0], *data["attempts"]]):
        with pytest.raises(ValidationError, match="missing or duplicate"):
            Scorecard.model_validate({**data, "attempts": wrong})


@pytest.mark.parametrize(
    "invalid", ["", "smoke", "wrong_preview", "wrong_commit", "dirty", "stale", "skipped", "one_trial", "failed"]
)
def test_release_evidence_must_be_fresh_complete_and_match_the_exact_clean_build(invalid: str) -> None:
    replay, live = sample(), sample(live=True, mixed=invalid == "failed")
    data = live.model_dump()
    if invalid == "smoke":
        data["profile"] = "smoke"
    if invalid == "one_trial":
        data["repeats"] = 1
        data["attempts"] = [r for r in data["attempts"] if r["attempt"] == 1]
    if invalid == "skipped":
        data["attempts"] = data["attempts"][:3]
    if invalid == "wrong_preview":
        data["target"]["deployment"] = "dpl_Other"
    if invalid == "wrong_commit":
        data["target"]["commit"] = "b" * 40
    if invalid == "dirty":
        data["source"]["dirty"] = True
    if invalid == "stale":
        data["started_at"] = NOW - timedelta(days=2)
    errors = release_errors(
        replay,
        Scorecard.model_validate(data),
        REV,
        DEPLOYMENT,
        replay_catalog=replay.catalog(),
        live_catalog=live.catalog(),
        now=NOW,
    )
    assert bool(errors) == bool(invalid)


def test_evaluations_displays_saved_replay_grid_and_live_misses(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(harness_scorecard, "REPORT_DIR", tmp_path)
    save(sample(), tmp_path / "last-replay.json")
    save(sample(live=True, mixed=True), tmp_path / "last-live.json")
    response = client.get("/evaluations")
    assert response.status_code == 200
    assert "Explore the weekend matrix" in response.text
    assert "All three tries" in response.text
    assert "golden/timing-dfw-fri" in response.text
    assert "try 2" in response.text
    assert "timeout" in response.text


def test_build_identity_is_uncached_and_no_upstream_checks_are_needed(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.settings = app.state.settings.model_copy(
        update={"vercel_git_commit_sha": REV, "vercel_deployment_id": DEPLOYMENT, "vercel_env": "preview"}
    )
    resp = client.get("/api/build")
    assert resp.json() == {"commit": REV, "deployment": DEPLOYMENT, "environment": "preview"}
    assert resp.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "bad",
    [
        "http://example.org",
        "https://user:abc@example.org/",
        "https://example.org/?q=x",
        "https://example.org/route",
        "file:///c:/tmp",
    ],
)
def test_live_cli_sends_only_to_an_explicit_origin(bad: str) -> None:
    with pytest.raises(ValueError, match="use"):
        origin(bad)


def test_public_parser_rejects_private_text_in_a_report() -> None:
    row: dict[str, Any] = {"suite": "golden", "case_id": "alpha", "outcome": "pass", "duration_ms": 1}
    for extra in ({"question": "private text"}, {"outcome": "a private sentence"}):
        with pytest.raises(ValidationError):
            Attempt.model_validate({**row, **extra})
