"""Real LangSmith serialization receives operation metadata, never private Mem0 inputs, outputs or exceptions."""

import asyncio
import json
from collections.abc import Coroutine
from typing import Any, cast
from uuid import UUID

import httpx2
import pytest
from langsmith import tracing_context
from langsmith import utils as smith
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.app import create_app
from nimbus.config import Settings
from nimbus.memory.client import Mem0Service
from nimbus.memory.models import MemoryReason, MemoryStatus
from nimbus.memory.tracing import memory_trace
from nimbus.model import Tracer
from nimbus.utils import hide_error_text
from tests.unit.test_memory_client import KEY, PROFILE, USER, MemoryRecorder, row
from tests.unit.test_privacy import KeepingClient


def tracer() -> tuple[Tracer, KeepingClient]:
    """Use the actual SDK serializer with an in-memory HTTP recorder instead of a live tracing service."""
    client = KeepingClient(
        api_key="synthetic-langsmith-key", hide_inputs=True, hide_outputs=True, anonymizer=hide_error_text
    )
    return Tracer(client, "synthetic-memory"), client


def service(provider: MemoryRecorder, tracing: Tracer | None) -> Mem0Service:
    """Exercise the real Mem0 boundary with a synthetic provider and optional explicit tracer."""
    return Mem0Service(
        SecretStr(KEY), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)), tracer=tracing
    )


def assert_private(values: object, *extra: str) -> None:
    """Check every synthetic secret, preference field and provider identifier across the serialized content."""
    encoded = json.dumps(values, default=str)
    for secret in (KEY, USER, "synthetic-langsmith-key", *PROFILE.model_dump().values(), *extra):
        if secret:
            assert secret not in encoded


def test_read_save_and_delete_have_independent_safe_root_traces() -> None:
    """Each completed operation links its exact SDK root without creating model calls or capturing its payload."""
    tracing, client = tracer()
    provider = MemoryRecorder()
    api = service(provider, tracing)
    with capture_logs() as logs:
        saved = asyncio.run(api.save(USER, PROFILE, ""))
        read = asyncio.run(api.read(USER))
        assert asyncio.run(api.forget(USER))
    assert saved.preferences == read.preferences == PROFILE
    posts = [run for run in client.kept_runs if "name" in run and run.get("start_time")]
    assert [run["name"] for run in posts] == ["mem0.save", "mem0.read", "mem0.delete"]
    assert len({run["id"] for run in posts}) == 3
    assert len(client.kept_runs) == 6
    endings = [run for run in client.kept_runs if run.get("end_time")]
    assert [run["extra"]["metadata"]["status"] for run in endings] == ["ready", "ready", "empty"]
    for post, end, log in zip(posts, endings, logs, strict=True):
        assert post["run_type"] == "tool"
        assert post.get("parent_run_id") is None
        assert post["trace_id"] == post["id"] == end["id"] == log["traceId"]
        assert UUID(post["id"]).version == 4
        assert post["dotted_order"] == end["dotted_order"]
        assert post["inputs"] == {}
        assert end["outputs"] == {}
        assert not end.get("error")
        assert post["session_name"] == "synthetic-memory"
        assert post["start_time"] <= end["end_time"]
        assert log["event"] == "memory.operation"
    assert_private(client.kept_runs, saved.revision, *saved.memory_ids)
    assert_private(logs, saved.revision, *saved.memory_ids)


@pytest.mark.parametrize("operation", ["read", "save", "forget"])
def test_provider_failures_are_failed_spans_with_safe_reasons(operation: str) -> None:
    """A swallowed provider error is still a failed memory operation in LangSmith, with no error body."""
    tracing, client = tracer()
    api = Mem0Service(
        SecretStr(KEY),
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(lambda _: httpx2.Response(401, text=KEY))),
        tracer=tracing,
    )
    args = (USER, PROFILE, "") if operation == "save" else (USER,)
    with capture_logs() as logs:
        asyncio.run(getattr(api, operation)(*args))
    end = client.kept_runs[-1]
    assert end["error"] == "hidden"
    assert end["extra"]["metadata"]["status"] == "unavailable"
    assert end["extra"]["metadata"]["reason"] == "authentication_failed"
    assert logs[-1]["traceId"] == end["id"]
    assert_private([client.kept_runs, logs])


@pytest.mark.parametrize("operation", ["save", "forget"])
def test_unconfirmed_mutations_are_failed_not_successful_traces(operation: str) -> None:
    """An HTTP acknowledgement without verified state cannot become a successful span."""
    tracing, client = tracer()
    provider = MemoryRecorder([row()] if operation == "forget" else None)
    provider.confirm_writes = False
    api = service(provider, tracing)
    args = (USER, PROFILE, "") if operation == "save" else (USER,)
    asyncio.run(getattr(api, operation)(*args))
    end = client.kept_runs[-1]
    assert end["error"] == "hidden"
    assert end["extra"]["metadata"]["status"] == "pending"
    assert end["extra"]["metadata"]["reason"] == "pending_confirmation"
    assert_private(client.kept_runs)


def test_stale_revision_is_failed_and_never_traced() -> None:
    """Rejected changes retain an honest conflict outcome without sending the compared revision to LangSmith."""
    tracing, client = tracer()
    record = row()
    result = asyncio.run(service(MemoryRecorder([record]), tracing).save(USER, PROFILE, "private-stale-revision"))
    assert result.status == "conflict"
    end = client.kept_runs[-1]
    assert end["error"] == "hidden"
    assert end["extra"]["metadata"]["reason"] == "stale_revision"
    assert_private(client.kept_runs, "private-stale-revision", record["id"], record["metadata"]["nimbus_revision"])


def test_no_tracer_means_no_spans_even_with_an_enabled_ambient_context() -> None:
    """Application opt-out wins over an unrelated LangSmith context; empty reads still work normally."""
    _, client = tracer()
    with (
        tracing_context(enabled=True, client=client, metadata={"private": "ambient-private-value"}),
        capture_logs() as logs,
    ):
        result = asyncio.run(service(MemoryRecorder(), None).read(USER))
    assert result.status == "empty"
    assert client.kept_runs == []
    assert "traceId" not in logs[0]


def test_explicit_tracer_does_not_capture_ambient_metadata() -> None:
    """Context metadata and tags cannot smuggle a value into the standalone memory root."""
    tracing, client = tracer()
    with tracing_context(enabled=True, client=client, metadata={"private": KEY}, tags=["private-browser-cookie"]):
        asyncio.run(service(MemoryRecorder(), tracing).read(USER))
    assert len(client.kept_runs) == 2
    assert_private(client.kept_runs, "private-browser-cookie")


@pytest.mark.parametrize("stage", ["create_run", "update_run"])
def test_tracing_failures_do_not_break_saves_or_leak_the_exception(stage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tracing is best-effort; safe diagnostics distinguish an absent root from a queued but unfinished root."""
    tracing, client = tracer()

    def fail(*args: Any, **kwargs: Any) -> None:
        """Simulate an SDK failure whose exception must never be logged."""
        raise RuntimeError("private-tracing-failure " + KEY)

    monkeypatch.setattr(client, stage, fail)
    with capture_logs() as logs:
        saved = asyncio.run(service(MemoryRecorder(), tracing).save(USER, PROFILE, ""))
    assert saved.status == "ready"
    operation = next(log for log in logs if log["event"] == "memory.operation")
    assert ("traceId" in operation) == (stage == "update_run")
    assert any(log["event"] == "trace.memory_write_failed" for log in logs)
    assert_private([client.kept_runs, logs], "private-tracing-failure")


@pytest.mark.parametrize("cancelled", [True, False])
def test_interruption_finishes_the_span_and_preserves_exception_semantics(cancelled: bool) -> None:
    """Cancellation and unexpected failures propagate after a generic error ends the operation, without a traceback."""
    tracing, client = tracer()

    async def fail(_: httpx2.Request) -> httpx2.Response:
        """Raise a private provider failure outside the service's handled operational errors."""
        if cancelled:
            raise asyncio.CancelledError("private-interruption " + KEY)
        raise RuntimeError("private-interruption " + KEY)

    api = Mem0Service(SecretStr(KEY), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(fail)), tracer=tracing)
    with capture_logs() as logs, pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
        asyncio.run(api.read(USER))
    end = client.kept_runs[-1]
    assert end["error"] == "hidden"
    assert end["extra"]["metadata"]["status"] == "unavailable"
    assert logs[-1]["traceId"] == end["id"]
    assert logs[-1]["status"] == "unavailable"
    assert_private([client.kept_runs, logs], "private-interruption")


def test_concurrent_reads_keep_roots_and_outcomes_request_local() -> None:
    """One shared Mem0 service cannot reuse an operation's state across concurrent visitors."""
    tracing, client = tracer()

    async def respond(_: httpx2.Request) -> httpx2.Response:
        """Yield while another read starts, then return a valid empty result."""
        await asyncio.sleep(0)
        return httpx2.Response(200, json={"count": 0, "next": None, "results": []})

    api = Mem0Service(
        SecretStr(KEY), lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(respond)), tracer=tracing
    )

    async def run() -> None:
        """Race two independent browser scopes through the same configured client."""
        outcomes = await asyncio.gather(api.read(USER), api.read("nimbus_" + "b" * 32))
        assert all(outcome.status == "empty" for outcome in outcomes)

    with capture_logs() as logs:
        asyncio.run(run())
    posts = [run for run in client.kept_runs if run.get("start_time")]
    endings = [run for run in client.kept_runs if run.get("end_time")]
    assert len(posts) == len(endings) == len(logs) == 2
    assert len({log["traceId"] for log in logs}) == 2
    assert {log["traceId"] for log in logs} == {run["id"] for run in posts} == {run["id"] for run in endings}
    assert all(run["extra"]["metadata"]["status"] == "empty" and not run.get("error") for run in endings)
    assert_private([client.kept_runs, logs], "nimbus_" + "b" * 32)


def test_memory_operation_defers_existing_vercel_flush(monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory-only requests use the same bounded post-response flushing mechanism as chat."""
    tracing, client = tracer()
    tracing = Tracer(client, tracing.project, is_vercel=True)
    waiting: list[Coroutine[Any, Any, None]] = []
    monkeypatch.setattr("nimbus.model.wait_until", waiting.append)
    asyncio.run(service(MemoryRecorder(), tracing).read(USER))
    assert len(waiting) == 1
    waiting[0].close()


def test_unconfigured_and_invalid_identity_attempts_are_failed_without_private_inputs() -> None:
    """Rejected operations are observable but never send the supplied identity or invented profile to tracing."""
    tracing, client = tracer()
    asyncio.run(Mem0Service(None, tracer=tracing).read("private-invalid-user"))
    asyncio.run(service(MemoryRecorder(), tracing).read("private-invalid-user"))
    endings = [run for run in client.kept_runs if run.get("end_time")]
    assert [run["extra"]["metadata"]["reason"] for run in endings] == ["not_configured", "invalid_identity"]
    assert all(run["error"] == "hidden" for run in endings)
    assert_private(client.kept_runs, "private-invalid-user")


@pytest.mark.parametrize(
    ("enabled", "inputs_hidden", "outputs_hidden", "allowed"),
    [(True, True, True, True), (False, True, True, False), (True, False, True, False), (True, True, False, False)],
)
def test_application_wires_only_the_privacy_approved_tracer(
    enabled: bool, inputs_hidden: bool, outputs_hidden: bool, allowed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production constructor supplies memory's tracer only when the shared tracing privacy gate permits it."""
    monkeypatch.setattr("nimbus.model.Client", KeepingClient)
    app = create_app(
        Settings(
            _env_file=None,
            langsmith_tracing=enabled,
            langsmith_hide_inputs=inputs_hidden,
            langsmith_hide_outputs=outputs_hidden,
            langsmith_api_key=SecretStr("synthetic-langsmith-key"),
            mem0_api_key=SecretStr(KEY),
        )
    )
    provider = MemoryRecorder()
    app.state.mem0._make_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider))
    with capture_logs() as logs:
        assert asyncio.run(app.state.mem0.read(USER)).status == "empty"
    assert ("traceId" in logs[0]) == allowed
    if allowed:
        client = app.state.tracer.client
        assert isinstance(client, KeepingClient)
        assert len(client.kept_runs) == 2
        assert_private(client.kept_runs)


@pytest.mark.parametrize("variable", ["LANGCHAIN_PROJECT", "HOSTED_LANGSERVE_PROJECT_NAME"])
def test_memory_preserves_sdk_project_fallbacks_used_by_chat_and_reader(
    variable: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no app override, legacy and hosted project selection must match the project's trace reader."""
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    monkeypatch.delenv("HOSTED_LANGSERVE_PROJECT_NAME", raising=False)
    monkeypatch.setenv(variable, "synthetic-legacy-project")
    cast(Any, smith.get_env_var).cache_clear()
    smith.get_tracer_project.cache_clear()
    try:
        _, client = tracer()
        tracing = Tracer(client, None)
        asyncio.run(service(MemoryRecorder(), tracing).read(USER))
        [post] = [run for run in client.kept_runs if run.get("start_time")]
        assert post["session_name"] == "synthetic-legacy-project"
        assert post["session_name"] == smith.get_tracer_project()
        assert_private(client.kept_runs)
    finally:
        cast(Any, smith.get_env_var).cache_clear()
        smith.get_tracer_project.cache_clear()


@pytest.mark.parametrize(
    ("status", "reason", "expected_status", "expected_reason"),
    [
        ("private-status-value", "", "unavailable", ""),
        ("ready", "private-reason-value", "ready", "unavailable"),
    ],
)
def test_runtime_outcomes_are_allowlisted_before_serialization_and_logging(
    status: str, reason: str, expected_status: str, expected_reason: str
) -> None:
    """Type hints alone do not protect the boundary: unexpected runtime strings are replaced before emission."""
    tracing, client = tracer()
    with capture_logs() as logs, memory_trace(tracing, "read") as operation:
        operation.outcome(cast(MemoryStatus, status), cast(MemoryReason, reason))
    end = client.kept_runs[-1]
    assert end["extra"]["metadata"]["status"] == logs[-1]["status"] == expected_status
    assert end["extra"]["metadata"]["reason"] == logs[-1]["reason"] == expected_reason
    assert_private([client.kept_runs, logs], "private-status-value", "private-reason-value")


def test_flush_failure_does_not_break_a_verified_save(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken post-response flush hook cannot turn a successful write into an application failure."""
    tracing, client = tracer()

    def fail(_tracer: Tracer) -> None:
        """Simulate a hook failure with a secret-bearing exception that must never be published."""
        raise RuntimeError("private-flush-failure " + KEY)

    monkeypatch.setattr(Tracer, "defer_flush", fail)
    with capture_logs() as logs:
        saved = asyncio.run(service(MemoryRecorder(), tracing).save(USER, PROFILE, ""))
    assert saved.status == "ready"
    end = client.kept_runs[-1]
    assert end["extra"]["metadata"]["status"] == "ready"
    assert not end.get("error")
    operation = next(log for log in logs if log["event"] == "memory.operation")
    assert operation["status"] == "ready"
    assert operation["traceId"] == end["id"]
    assert any(log["event"] == "trace.memory_write_failed" and log["stage"] == "flush" for log in logs)
    assert_private([client.kept_runs, logs], "private-flush-failure")
