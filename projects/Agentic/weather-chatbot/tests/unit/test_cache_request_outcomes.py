"""The chat's real LangSmith trace explains cache decisions without exposing request or cache contents."""

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.tracers.langchain import wait_for_all_tracers

from nimbus.semantic_cache.service import SemanticCacheService
from tests.fakes import FakeModel
from tests.unit.test_memory_tracing import tracer
from tests.unit.test_privacy import KeepingClient
from tests.unit.test_request_trace import ended, started
from tests.unit.test_semantic_cache_chat import (
    NARRATIVE,
    QUESTION,
    RECEIPT,
    CacheProvider,
    DallasWeather,
    ask_cache,
    configure_cache,
    history_fields,
)


@pytest.fixture
def traced_cache(
    client: TestClient, chat_model: FakeModel
) -> tuple[TestClient, FakeModel, CacheProvider, DallasWeather, KeepingClient]:
    """Run chat against synthetic weather/Qdrant with the actual LangSmith serializer recorded offline."""
    provider, weather = CacheProvider(), DallasWeather()
    assert isinstance(client.app, FastAPI)
    configure_cache(client.app, chat_model, provider, weather)
    tracing, recorded = tracer()
    client.app.state.tracer = tracing
    return client, chat_model, provider, weather, recorded


def finished(recorded: KeepingClient) -> dict[str, dict[str, Any]]:
    """Return the newest request's named span endings after its graph tracing has finished."""
    wait_for_all_tracers()
    roots = [run for run in started(recorded.kept_runs) if run["name"] == "nimbus.chat"]
    root = roots[-1]["id"]
    runs = [run for run in started(recorded.kept_runs) if run.get("trace_id") == root]
    result = {run["name"]: ended(recorded.kept_runs, run["id"])[-1] for run in runs}
    # FakeModel's serialized constructor includes its scripted answer; the production model has no such field.
    # Inspect all operational fields, and assert our own spans never serialize a model or any cache contents.
    owned_ids = {run["id"] for run in runs if run["name"].startswith(("nimbus.chat", "weather_cache.", "qdrant."))}
    assert all(not run.get("serialized") for run in recorded.kept_runs if run["id"] in owned_ids)
    encoded = json.dumps(
        [{key: value for key, value in run.items() if key != "serialized"} for run in recorded.kept_runs]
    )
    for private in (QUESTION, NARRATIVE, "synthetic-cache-test-key", "synthetic-langsmith-key"):
        assert private not in encoded
    return result


@pytest.mark.parametrize("missing", ["forecast_coverage", "weather_tools"])
def test_store_explains_unreusable_answer_without_claiming_a_qdrant_write(
    traced_cache: tuple[TestClient, FakeModel, CacheProvider, DallasWeather, KeepingClient], missing: str
) -> None:
    """A complete response can retain its history receipt while its store span reports no reusable evidence."""
    client, model, provider, weather, recorded = traced_cache
    if missing == "forecast_coverage":
        weather.forecast_days = 1
    else:
        model.tool_steps = []
    response = ask_cache(client)
    runs = finished(recorded)
    assert RECEIPT.search(response)
    assert provider.points == {}
    assert runs["weather_cache.lookup"]["extra"]["metadata"]["outcome"] == "miss"
    assert runs["weather_cache.store"]["extra"]["metadata"]["outcome"] == "not_reusable"
    assert not runs["weather_cache.store"].get("error")
    assert not any(name in runs for name in ("qdrant.remove_expired", "qdrant.count", "qdrant.save"))
    assert not runs["nimbus.chat"].get("error")


def test_qdrant_outage_fails_cache_steps_but_not_the_successful_chat(
    traced_cache: tuple[TestClient, FakeModel, CacheProvider, DallasWeather, KeepingClient],
) -> None:
    """A fail-open service result must appear as a failed cache span instead of a successful operation."""
    client, _model, provider, _weather, recorded = traced_cache
    provider.status = 503
    response = ask_cache(client)
    runs = finished(recorded)
    assert "cloudy skies" in response
    for name in ("weather_cache.lookup", "qdrant.exact_match", "weather_cache.store", "qdrant.remove_expired"):
        assert runs[name].get("error")
        assert runs[name]["extra"]["metadata"]["outcome"] == "error"
    assert runs["nimbus.chat"]["extra"]["metadata"]["cache_outcome"] == "error"
    assert not runs["nimbus.chat"].get("error")


@pytest.mark.parametrize(
    ("scenario", "reason"),
    [
        ("disabled", "disabled"),
        ("unconfigured", "unconfigured"),
        ("unsafe", "ineligible"),
        ("trip", "workflow"),
        ("unverified", "unverified_history"),
        ("changed_intent", "incompatible_history"),
    ],
)
def test_bypassed_cache_records_a_fixed_reason_on_the_request_without_fake_provider_spans(
    traced_cache: tuple[TestClient, FakeModel, CacheProvider, DallasWeather, KeepingClient], scenario: str, reason: str
) -> None:
    """Even early trip routing or rejected history explains why this request did not contact Qdrant."""
    client, _model, provider, _weather, recorded = traced_cache
    assert isinstance(client.app, FastAPI)
    question, fields = QUESTION, {}
    if scenario == "disabled":
        client.app.state.semantic_cache.mode = "off"
    elif scenario == "unconfigured":
        settings = client.app.state.settings.model_copy(update={"qdrant_api_key": None})
        client.app.state.semantic_cache = SemanticCacheService(settings)
    elif scenario == "unsafe":
        question = "Will it be safe in Dallas?"
    elif scenario == "trip":
        question = "Plan a trip to Dallas"
    elif scenario in {"unverified", "changed_intent"}:
        prior = QUESTION if scenario == "unverified" else "Dallas weather now"
        fields = history_fields(ask_cache(client, prior), prior)
        if scenario == "unverified":
            fields["cache_receipt"] = "0" * 64
    before = len(provider.requests)
    ask_cache(client, question, **fields)
    runs = finished(recorded)
    metadata = runs["nimbus.chat"]["extra"]["metadata"]
    assert metadata["cache_outcome"] == "bypass"
    assert metadata.get("cache_bypass_reason") == reason
    assert not any(name.startswith(("weather_cache.", "qdrant.")) for name in runs)
    assert len(provider.requests) == before
