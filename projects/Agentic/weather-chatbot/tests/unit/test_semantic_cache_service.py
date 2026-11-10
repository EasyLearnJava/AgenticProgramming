"""Qdrant wire contracts, independent reuse validation and bounded fail-open behavior, with no external calls."""

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr, ValidationError
from structlog.testing import capture_logs

from nimbus.config import Settings
from nimbus.open_meteo import Place
from nimbus.semantic_cache.identity import signature
from nimbus.semantic_cache.models import MODEL, VERSION, CacheEntry, CachePolicy, WeatherEvidence
from nimbus.semantic_cache.policy import digest, normalized
from nimbus.semantic_cache.service import MAX_POINTS, SemanticCacheService
from nimbus.tools import CurrentWeatherOutput, GeocodeOutput

NOW = 1794240000.0
KEY = "private-test-credential"
SCOPE = "a" * 64
CONTEXT = "b" * 64
QUESTION = "Dallas weather"


def settings(**overrides: Any) -> Settings:
    """An enabled, isolated deployment with no ambient credentials or network services."""
    return Settings(
        _env_file=None,
        **{
            "qdrant_url": "https://cache.us-east-1.aws.cloud.qdrant.io",
            "qdrant_api_key": SecretStr(KEY),
            "qdrant_collection": "nimbus_weather_cache",
            "semantic_cache_mode": "on",
            "semantic_cache_threshold": 0.9,
            **overrides,
        },
    )


def entry(**overrides: Any) -> CacheEntry:
    """A valid weather-only answer with a known original fetch time and two-minute deadline."""
    evidence = WeatherEvidence(
        places=GeocodeOutput(
            candidates=[
                Place(
                    name="Dallas",
                    region="Texas",
                    country="United States",
                    country_code="US",
                    latitude=32.78,
                    longitude=-96.81,
                    time_zone="America/Chicago",
                    population=1300000,
                )
            ],
            is_ambiguous=False,
        ),
        current=CurrentWeatherOutput(
            latitude=32.78,
            longitude=-96.81,
            time_zone="America/Chicago",
            observed_at="2026-11-09T12:00",
            condition="Clear sky",
            is_day=True,
            temperature=70,
            feels_like=69,
            temperature_unit="°F",
            wind_speed=5,
            wind_speed_unit="mph",
        ),
    )
    values = {
        "scope": SCOPE,
        "context": CONTEXT,
        "exact": digest(normalized(QUESTION)),
        "policy": CachePolicy(
            place="dallas",
            intent="overview",
            units="imperial",
            locale="en-US",
            time_zone="America/Chicago",
            day="2026-11-09",
        ),
        "label": "Dallas, Texas, US",
        "answer": "Dallas is clear with a temperature of 70 °F.",
        "evidence": evidence,
        "created_at": NOW,
        "expires_at": NOW + 120,
        "evidence_fetched_at": NOW - 15,
        **overrides,
    }
    return CacheEntry.model_validate(values)


def point(record: CacheEntry, score: object = 0.96) -> dict[str, object]:
    """The signed opaque record returned by Qdrant, with its candidate's own score."""
    text = record.model_dump_json()
    return {"id": "test-point", "score": score, "payload": {"record": text, "mac": signature(KEY, "entry", text)}}


def points(*records: dict[str, object]) -> httpx2.Response:
    """A successful Qdrant point query or scroll result."""
    return httpx2.Response(200, json={"status": "ok", "result": {"points": list(records)}})


class RecordingQdrant:
    """Supply queued HTTP results and capture the exact requests sent by the production adapter."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        """Start with the specified response sequence."""
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Record one request, then return or raise its prepared outcome."""
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def service(
    handler: Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]], **overrides: Any
) -> SemanticCacheService:
    """Use MockTransport with the real HTTP service and fixed clock."""
    return SemanticCacheService(
        settings(**overrides), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler)), clock=lambda: NOW
    )


def test_exact_hit_uses_no_embedding_request_and_sends_private_filters() -> None:
    """The literal repeat takes one scroll request and independently retains its original expiry."""
    record = entry()
    qdrant = RecordingQdrant(points(point(record)))
    result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, record.policy))
    assert (result.status, result.entry) == ("exact_hit", record)
    assert len(qdrant.requests) == 1
    request = qdrant.requests[0]
    assert request.url.path == "/collections/nimbus_weather_cache/points/scroll"
    assert request.headers["api-key"] == KEY
    assert KEY not in str(request.url)
    body = json.loads(request.content)
    assert body["limit"] == 1
    assert body["with_vector"] is False
    assert "query" not in body
    filters = body["filter"]["must"][0]["must"]
    assert {"key": "scope", "match": {"value": SCOPE}} in filters
    assert {"key": "context", "match": {"value": CONTEXT}} in filters
    assert {"key": "guard", "match": {"value": digest(record.policy.model_dump())}} in filters
    assert {"key": "expires_at", "range": {"gt": NOW}} in filters


def test_semantic_hit_uses_hosted_minilm_and_threshold_after_exact_miss() -> None:
    """A reworded query is sent once for remote inference within the same independent policy guards."""
    record = entry()
    qdrant = RecordingQdrant(points(), points(point(record)))
    result = asyncio.run(service(qdrant).lookup("Weather in Dallas", SCOPE, CONTEXT, record.policy))
    assert result.status == "semantic_hit"
    assert result.entry is not None
    assert result.entry.expires_at == NOW + 120
    request = qdrant.requests[1]
    assert request.url.path.endswith("/points/query")
    body = json.loads(request.content)
    assert body["query"] == {"text": "weather in dallas", "model": MODEL}
    assert body["score_threshold"] == 0.9
    assert body["filter"]["must"][-1] == {"key": "expires_at", "range": {"gt": NOW}}


@pytest.mark.parametrize("score", [None, True, "0.99", 0.89, -1, float("nan"), float("inf"), 2])
def test_unacceptable_semantic_scores_cannot_skip_gemini(score: object) -> None:
    """The client does not trust Qdrant's threshold filtering or score types."""
    record = entry()
    # Raw JSON intentionally exercises malformed-provider NaN/Infinity as well as ordinary JSON values.
    response = httpx2.Response(
        200, content=json.dumps({"status": "ok", "result": {"points": [point(record, score)]}}).encode()
    )
    qdrant = RecordingQdrant(points(), response)
    result = asyncio.run(service(qdrant).lookup("Weather in Dallas", SCOPE, CONTEXT, record.policy))
    assert result.entry is None
    assert result.status in {"miss", "error"}


def test_threshold_is_inclusive_for_the_actual_candidate() -> None:
    """A score at the configured boundary can qualify; below it cannot."""
    record = entry()
    qdrant = RecordingQdrant(points(), points(point(record, 0.9)))
    result = asyncio.run(service(qdrant).lookup("weather in dallas", SCOPE, CONTEXT, record.policy))
    assert result.status == "semantic_hit"


def test_one_candidates_score_cannot_authorize_another_candidates_entry() -> None:
    """A forged first candidate with a high score cannot lend it to a valid low-score record."""
    record = entry()
    tampered = {"score": 0.99, "payload": {"record": "tampered", "mac": "0" * 64}}
    qdrant = RecordingQdrant(points(), points(tampered, point(record, 0.1)))
    result = asyncio.run(service(qdrant).lookup("weather in dallas", SCOPE, CONTEXT, record.policy))
    assert result.entry is None
    assert result.status in {"miss", "error"}


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "c" * 64},
        {"context": "c" * 64},
        {"expires_at": NOW},
        {"expires_at": NOW + 121},
        {"created_at": NOW + 1},
        {"evidence_fetched_at": NOW + 1},
        {"policy": entry().policy.model_copy(update={"place": "austin"})},
        {"policy": entry().policy.model_copy(update={"intent": "today"})},
        {"policy": entry().policy.model_copy(update={"units": "metric"})},
        {"policy": entry().policy.model_copy(update={"day": "2026-11-10"})},
    ],
)
def test_remote_filter_mistakes_do_not_override_local_scope_and_freshness_checks(changes: dict[str, Any]) -> None:
    """Even an authenticated entry is not reusable for a different browser, context, date or unit request."""
    record = entry(**changes)
    qdrant = RecordingQdrant(points(point(record)), points(point(record)))
    result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, entry().policy))
    assert result.entry is None
    assert result.status in {"miss", "error"}


def test_wrong_exact_fingerprint_is_not_an_exact_hit() -> None:
    """An exact-filter error is never silently promoted into an exact cache hit."""
    record = entry(exact="c" * 64)
    qdrant = RecordingQdrant(points(point(record)), points())
    result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, record.policy))
    assert result.status != "exact_hit"
    assert result.entry is None


def test_tampered_payload_and_wrong_key_mac_are_discarded() -> None:
    """A cache writer without Nimbus's signing credential cannot inject an answer."""
    record = entry()
    text = record.model_dump_json()
    tampered = {"score": 1.0, "payload": {"record": text, "mac": signature("wrong-key", "entry", text)}}
    qdrant = RecordingQdrant(points(tampered), points(tampered))
    result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, record.policy))
    assert result.status == "miss"
    assert result.entry is None


@pytest.mark.parametrize("mode", ["off", "shadow", "on"])
def test_modes_have_explicit_behavior(mode: str) -> None:
    """Off makes no calls; shadow observes reuse without returning a saved answer; on permits it."""
    record = entry()
    qdrant = RecordingQdrant(points(point(record)))
    result = asyncio.run(service(qdrant, semantic_cache_mode=mode).lookup(QUESTION, SCOPE, CONTEXT, record.policy))
    assert result.status == {"off": "bypass", "shadow": "shadow_hit", "on": "exact_hit"}[mode]
    assert (result.entry is not None) == (mode == "on")
    assert len(qdrant.requests) == (0 if mode == "off" else 1)


@pytest.mark.parametrize("override", [{"qdrant_url": ""}, {"qdrant_api_key": None}])
def test_incomplete_configuration_is_a_network_free_bypass(override: dict[str, Any]) -> None:
    """An unconfigured optimization leaves normal chat available."""
    qdrant = RecordingQdrant()
    cache = service(qdrant, **override)
    result = asyncio.run(cache.lookup(QUESTION, SCOPE, CONTEXT, entry().policy))
    assert result.status == "bypass"
    assert not qdrant.requests
    assert asyncio.run(cache.list_entries(SCOPE)).status == "disabled"


@pytest.mark.parametrize(
    "failure",
    [
        httpx2.Response(401),
        httpx2.Response(429),
        httpx2.Response(503),
        httpx2.ConnectError("private upstream detail"),
        httpx2.Response(200, text="not json"),
        httpx2.Response(200, json=[]),
        httpx2.Response(200, json={"status": "ok", "result": {"points": "invalid"}}),
    ],
)
def test_provider_failures_fail_open_without_leaking_sensitive_data(failure: httpx2.Response | Exception) -> None:
    """Credentials, questions, answers and provider error bodies never enter operational cache logs."""
    qdrant = RecordingQdrant(failure)
    with capture_logs() as logs:
        result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, entry().policy))
    assert result.status == "error"
    assert result.entry is None
    serialized = json.dumps(logs)
    for private in (KEY, QUESTION, SCOPE, CONTEXT, entry().answer, "private upstream detail"):
        assert private not in serialized
    assert logs[-1]["status"] == "error"
    assert isinstance(logs[-1]["ms"], int)


def test_lookup_deadline_cancels_the_underlying_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deadline cancels an async request instead of leaving an embedding thread running."""
    monkeypatch.setattr("nimbus.semantic_cache.service.TIMEOUT_SECONDS", 0.02)
    stopped = False

    async def slow(_request: httpx2.Request) -> httpx2.Response:
        nonlocal stopped
        try:
            await asyncio.sleep(30)
            return points()
        finally:
            stopped = True

    result = asyncio.run(service(slow).lookup(QUESTION, SCOPE, CONTEXT, entry().policy))
    assert result.status == "error"
    assert stopped


def test_request_cancellation_is_not_swallowed_as_a_cache_miss() -> None:
    """A visitor disconnect still aborts the request and releases the gate."""

    async def cancelled(_request: httpx2.Request) -> httpx2.Response:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service(cancelled).lookup(QUESTION, SCOPE, CONTEXT, entry().policy))


def test_oversized_provider_response_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bounded response prevents accidental memory expansion in a serverless function."""
    monkeypatch.setattr("nimbus.semantic_cache.service.MAX_RESPONSE_BYTES", 64)
    qdrant = RecordingQdrant(points(point(entry())))
    result = asyncio.run(service(qdrant).lookup(QUESTION, SCOPE, CONTEXT, entry().policy))
    assert result.status == "error"
    assert result.entry is None


def test_store_uses_inference_payload_mac_and_absolute_expiry() -> None:
    """Only the upsert receives question text, while the record carries a bounded authenticated lifetime."""
    record = entry()
    success = httpx2.Response(200, json={"status": "ok", "result": {}})
    count = httpx2.Response(200, json={"status": "ok", "result": {"count": 0}})
    qdrant = RecordingQdrant(success, count, success)
    assert asyncio.run(service(qdrant).store(QUESTION, record)).status == "saved"
    assert [r.method for r in qdrant.requests] == ["POST", "POST", "PUT"]
    cleanup = json.loads(qdrant.requests[0].content)
    assert {"key": "expires_at", "range": {"lte": NOW}} in cleanup["filter"]["must"]
    assert not any(clause.get("key") == "version" for clause in cleanup["filter"]["must"])
    write = json.loads(qdrant.requests[-1].content)["points"][0]
    assert write["vector"] == {"text": "dallas weather", "model": MODEL}
    payload = write["payload"]
    assert payload["expires_at"] == record.expires_at
    assert payload["scope"] == SCOPE
    assert payload["version"] == VERSION
    assert payload["mac"] == signature(KEY, "entry", payload["record"])
    assert CacheEntry.model_validate_json(payload["record"]) == record


def test_full_collection_does_not_issue_an_upsert() -> None:
    """Capacity exhaustion keeps normal model operation available without adding more records."""
    qdrant = RecordingQdrant(
        httpx2.Response(200, json={"status": "ok", "result": {}}),
        httpx2.Response(200, json={"status": "ok", "result": {"count": MAX_POINTS}}),
    )
    assert asyncio.run(service(qdrant).store(QUESTION, entry())).status == "cache_full"
    assert len(qdrant.requests) == 2


def test_expired_answer_is_not_sent_for_storage() -> None:
    """An answer expiring while Gemini responds cannot gain time from a cache write."""
    qdrant = RecordingQdrant()
    assert asyncio.run(service(qdrant).store(QUESTION, entry(expires_at=NOW))).status == "not_reusable"
    assert not qdrant.requests


def test_listing_rechecks_scope_signature_and_absolute_expiry() -> None:
    """The sidebar page cannot expose another browser's records even if remote filters are broken."""
    valid = entry()
    qdrant = RecordingQdrant(points(point(entry(scope="d" * 64)), point(entry(expires_at=NOW)), point(valid)))
    result = asyncio.run(service(qdrant).list_entries(SCOPE))
    assert result.status == "ready"
    assert result.entries == (valid,)
    body = json.loads(qdrant.requests[0].content)
    assert body["limit"] <= 50
    assert {"key": "scope", "match": {"value": SCOPE}} in body["filter"]["must"]


def test_list_failure_is_distinct_from_an_empty_cache() -> None:
    """An unavailable provider must not make the UI falsely report a verified empty cache."""
    qdrant = RecordingQdrant(httpx2.Response(503))
    result = asyncio.run(service(qdrant).list_entries(SCOPE))
    assert result.status == "unavailable"
    assert not result.entries


@pytest.mark.parametrize(
    "url",
    [
        "http://cache.cloud.qdrant.io",
        "https://attacker.example",
        "https://cloud.qdrant.io.attacker.example",
        "https://127.0.0.1",
        "https://user:secret@cache.cloud.qdrant.io",
        "https://cache.cloud.qdrant.io/api",
        "https://cache.cloud.qdrant.io?api-key=secret",
        "https://cache.cloud.qdrant.io#secret",
        "https://cache.cloud.qdrant.io:9000",
        "https://cache.cloud.qdrant.io:invalid",
    ],
)
def test_endpoint_validation_keeps_the_credential_on_qdrant_cloud(url: str) -> None:
    """A configuration mistake cannot send the database credential to an arbitrary or plaintext endpoint."""
    with pytest.raises(ValidationError):
        settings(qdrant_url=url)


@pytest.mark.parametrize("port", ["", ":443", ":6333"])
def test_both_documented_qdrant_https_rest_ports_are_accepted(port: str) -> None:
    """The endpoint copied from the console works with HTTPS or its documented explicit REST ports."""
    result = settings(qdrant_url=f"https://cache.cloud.qdrant.io{port}/")
    assert result.qdrant_url == f"https://cache.cloud.qdrant.io{port}"


@pytest.mark.parametrize("collection", ["../other", "weather/points", "weather?wait=false", "a" * 65])
def test_collection_names_cannot_modify_the_request_path(collection: str) -> None:
    """Only a short, safe collection identifier can be interpolated into an authenticated endpoint."""
    with pytest.raises(ValidationError):
        settings(qdrant_collection=collection)


@pytest.mark.parametrize("threshold", [0.79, 1.1, float("nan"), float("inf")])
def test_similarity_threshold_is_finite_and_bounded(threshold: float) -> None:
    """Configuration cannot accidentally turn reuse into unrestricted nearest-neighbor matching."""
    with pytest.raises(ValidationError):
        settings(semantic_cache_threshold=threshold)


def test_equivalent_questions_replace_one_record_instead_of_growing_the_collection() -> None:
    """A browser's same guarded request has one point ID regardless of its query wording."""
    success = httpx2.Response(200, json={"status": "ok", "result": {}})
    count = httpx2.Response(200, json={"status": "ok", "result": {"count": 1}})
    qdrant = RecordingQdrant(success, count, success, success, count, success)
    cache = service(qdrant)
    assert asyncio.run(cache.store(QUESTION, entry())).status == "saved"
    result = asyncio.run(cache.store("weather in Dallas", entry(exact=digest(normalized("weather in Dallas")))))
    assert result.status == "saved"
    first = json.loads(qdrant.requests[2].content)["points"][0]
    second = json.loads(qdrant.requests[5].content)["points"][0]
    assert first["id"] == second["id"]


@pytest.mark.parametrize("failure_step", [0, 1, 2])
def test_failure_at_any_store_stage_is_optional_and_stops_further_work(failure_step: int) -> None:
    """Cleanup, capacity checks and write failures cannot break a successful weather response."""
    results = [
        httpx2.Response(200, json={"status": "ok", "result": {}}),
        httpx2.Response(200, json={"status": "ok", "result": {"count": 0}}),
        httpx2.Response(200, json={"status": "ok", "result": {}}),
    ]
    results[failure_step] = httpx2.Response(503)
    qdrant = RecordingQdrant(*results)
    assert asyncio.run(service(qdrant).store(QUESTION, entry())).status == "error"
    assert len(qdrant.requests) == failure_step + 1


def test_rate_gate_fails_open_before_sending_excess_requests() -> None:
    """The thirteenth lookup cannot start another remote embedding request in the same minute."""
    qdrant = RecordingQdrant(*(points() for _ in range(24)))
    cache = service(qdrant)

    async def run() -> None:
        for _ in range(12):
            assert (await cache.lookup(QUESTION, SCOPE, CONTEXT, entry().policy)).status == "miss"
        assert (await cache.lookup(QUESTION, SCOPE, CONTEXT, entry().policy)).status == "error"

    asyncio.run(run())
    assert len(qdrant.requests) == 24
