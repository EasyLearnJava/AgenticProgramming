"""Keep deterministic replies, model latency and independent source outcomes distinguishable."""

from datetime import UTC, datetime
from typing import cast

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nimbus import observability
from nimbus.axiom_query import AxiomQuery, Row
from nimbus.harness_scorecard import Attempt, Build, Scorecard
from tests.fakes import AxiomRecordings


def observe(client: TestClient, rows: dict[str, list[Row]]) -> AxiomRecordings:
    """Serve supplied query results through the real Axiom parser and page routes."""
    app = cast(FastAPI, client.app)
    token = SecretStr("test-query")
    recordings = AxiomRecordings(rows)
    app.state.settings = app.state.settings.model_copy(
        update={
            "axiom_dataset": "test-events",
            "axiom_query_token": token,
            "flights_enabled": False,
            "hotels_enabled": False,
        }
    )
    app.state.axiom_query = AxiomQuery(token, lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(recordings)))
    return recordings


def test_historical_services_remain_visible_when_travel_is_disabled(client: TestClient) -> None:
    rows = [
        {"event": event, "tool": tool, "status": status, "calls": 1, "totalMs": 400, "slowestMs": 400}
        for event, tool, status in (
            ("travel.call", "search_hotels", "partial"),
            ("travel.call", "search_hotels", "disabled"),
            ("travel.call", "search_hotels", "timeout"),
            ("knowledge.call", "search_park_guidance", "found"),
            ("nps.alerts", "get_park_alerts", "no_alerts"),
            ("nws.alerts", "park_trip_briefing", "failed"),
        )
    ]
    recordings = observe(client, {'where event in ("knowledge.call"': rows})
    page = client.get("/performance").text
    for outcome in ("1 partial", "1 disabled", "1 timeout", "1 found", "1 no alerts", "1 failed"):
        assert outcome in page
    assert "3 calls" in page
    assert "400 ms average" in page
    for tool in ("search_hotels", "search_park_guidance", "get_park_alerts", "park_trip_briefing"):
        assert f'href="/activity?tool={tool}"' in page
    query = next(query for query in recordings.queries if '"knowledge.call"' in query)
    for event in ("knowledge.call", "nps.alerts", "nws.alerts", "travel.call"):
        assert event in query


def test_model_statistics_exclude_clarifications_and_show_missing_usage(client: TestClient) -> None:
    recordings = observe(
        client,
        {
            "summarize answers": [{"answers": 2, "p50": 3000, "p95": 4000, "p99": 4000}],
            "summarize responses": [
                {"responseWorkflow": "agent", "responses": 2, "p50": 3000, "p95": 4000},
                {"responseWorkflow": "intake", "responses": 20, "p50": 5, "p95": 10},
                {"responseWorkflow": "briefing", "responses": 3, "p50": 1000, "p95": 2000},
                {"responseWorkflow": "unknown", "responses": 1, "p50": None, "p95": None},
            ],
        },
    )
    page = client.get("/performance").text
    for label in ("Clarifications and guidance", "Park conditions briefings", "Unclassified older responses"):
        assert label in page
    assert "20 responses" in page
    assert "3 responses" in page
    assert "3.0 s" in page
    assert "usage was not recorded" in page
    assert "P50 Unavailable" in page
    model_query = next(query for query in recordings.queries if "summarize answers" in query)
    assert 'where responseWorkflow == "agent"' in model_query
    for field in ("tripForm", "cityTripIntake", "hotelDateIntake", "forecastHorizon", "workflow", "tokensIn"):
        assert f"column_ifexists('{field}'" in model_query


def test_an_empty_model_sample_does_not_claim_zero_latency_or_usage(client: TestClient) -> None:
    observe(client, {"summarize answers": [{"answers": 0, "p50": None, "avgTokensIn": None}]})
    page = client.get("/performance").text
    assert "No completed model answers in this period." in page
    assert 'class="obs-tile"' not in page
    assert "0 ms" not in page


def test_live_scorecard_identifies_the_tested_target_and_unknown_source_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    card = Scorecard(
        mode="live",
        profile="smoke",
        started_at=now,
        finished_at=now,
        source=Build(commit="a" * 40, dirty=None),
        target=Build(commit="b" * 40, environment="preview", deployment="dpl_TestTarget"),
        repeats=3,
        attempts=[
            Attempt(suite="golden", case_id="test", attempt=number, outcome="pass", duration_ms=100)
            for number in (1, 2, 3)
        ],
    )
    monkeypatch.setattr(observability, "public_reports", lambda: [card])
    page = client.get("/evaluations").text
    assert "aaaaaaaaaaaa" in page
    assert "bbbbbbbbbbbb" in page
    assert "dpl_TestTarget" in page
    assert "checkout state unavailable" in page
    assert "3 tries" in page
    assert "smoke run covers a selected subset" in page
