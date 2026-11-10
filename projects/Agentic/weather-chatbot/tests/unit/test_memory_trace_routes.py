"""Real preference forms and chat reads link private-content-free traces across separate HTTP requests."""

from typing import cast

import httpx2
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.memory.client import Mem0Service
from nimbus.memory.identity import COOKIE
from tests.unit.test_memory_client import KEY, PROFILE
from tests.unit.test_memory_routes import ScopedRecorder, form, save, submit
from tests.unit.test_memory_tracing import assert_private, tracer


def test_save_read_chat_and_delete_trace_actual_request_operations(client: TestClient) -> None:
    """The forms' verified mutations and chat lookup use the traced service without uploading the user's data."""
    app = cast(FastAPI, client.app)
    app.state.settings.memory_enabled = True
    app.state.settings.memory_cookie_secret = SecretStr("synthetic-cookie-secret-for-trace-routes")
    tracing, recorded = tracer()
    provider = ScopedRecorder()
    app.state.mem0 = Mem0Service(
        SecretStr(KEY),
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)),
        tracer=tracing,
    )
    with capture_logs() as logs:
        save(client, **PROFILE.model_dump())
        private_record = provider.rows[0]
        private_values = (
            private_record["id"],
            private_record["user_id"],
            private_record["metadata"]["nimbus_revision"],
            client.cookies[COOKIE],
        )
        page = client.get("/preferences")
        assert page.status_code == 200
        response = client.post(
            "/api/chat", data={"question": "Show my preferences"}, headers={"origin": "http://testserver"}
        )
        assert response.status_code == 200
        deleted = submit(client, form(client, "forget"))
        assert deleted.status_code == 303
        assert provider.rows == []
        assert COOKIE not in client.cookies
    starts = [run for run in recorded.kept_runs if run.get("start_time")]
    ends = [run for run in recorded.kept_runs if run.get("end_time")]
    assert [run["name"] for run in starts] == ["mem0.save", "mem0.read", "mem0.read", "mem0.read", "mem0.delete"]
    assert len(ends) == len(starts)
    operations = [line for line in logs if line["event"] == "memory.operation"]
    assert [line["traceId"] for line in operations] == [run["id"] for run in starts]
    assert [line["status"] for line in operations] == ["ready", "ready", "ready", "ready", "empty"]
    assert_private([recorded.kept_runs, logs], *private_values, "Show my preferences")


def test_with_tracing_on_a_chats_mem0_read_is_a_step_of_the_chat_requests_trace(client: TestClient) -> None:
    """The chat's root holds its read; the read's line and the chat's ending name that one trace, for one link."""
    app = cast(FastAPI, client.app)
    app.state.settings.memory_enabled = True
    app.state.settings.memory_cookie_secret = SecretStr("synthetic-cookie-secret-for-trace-routes")
    tracing, recorded = tracer()
    provider = ScopedRecorder()
    app.state.mem0 = Mem0Service(
        SecretStr(KEY),
        lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(provider)),
        tracer=tracing,
    )
    save(client, **PROFILE.model_dump())
    app.state.tracer = tracing
    with capture_logs() as logs:
        response = client.post(
            "/api/chat", data={"question": "Show my preferences"}, headers={"origin": "http://testserver"}
        )
    assert response.status_code == 200
    [done] = [line for line in logs if line["event"] == "chat.done"]
    [operation] = [line for line in logs if line["event"] == "memory.operation"]
    root_id = done["traceId"]
    assert operation["traceId"] == root_id
    runs = [run for run in recorded.kept_runs if run.get("trace_id") == root_id]
    [root, read] = [run for run in runs if run.get("start_time")]
    assert (root["id"], root["name"]) == (root_id, "nimbus.chat")
    assert (read["name"], read["parent_run_id"]) == ("mem0.read", root_id)
    [ended] = [run for run in runs if run["id"] == root_id and run.get("end_time")]
    assert ended["extra"]["metadata"]["workflow"] == "memory"
    assert not ended.get("error")
    assert_private([recorded.kept_runs, logs], client.cookies[COOKIE], "Show my preferences")
