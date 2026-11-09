"""Opt-in memory ownership, consent and failure behavior across the real HTTP and chat boundaries."""

import asyncio
import json
import re
from typing import cast
from urllib.parse import urlencode

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from structlog.testing import capture_logs

from nimbus.memory.identity import COOKIE, COOKIE_SECONDS
from nimbus.memory.intake import memory_intent
from nimbus.memory.models import PreferenceProfile
from nimbus.retrieval_gate import RetrievalGate
from tests.fakes import FakeModel
from tests.unit.test_memory_client import MemoryRecorder, service


class ScopedRecorder(MemoryRecorder):
    """Implement provider filtering for multi-browser tests; the adapter still verifies every returned owner."""

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        """Select only the requested scope while preserving the shared synthetic provider store."""
        if request.url.path == "/v3/memories/":
            self.requests.append(request)
            owner = json.loads(request.content)["filters"]["user_id"]
            rows = [row for row in self.rows if row["user_id"] == owner]
            return httpx2.Response(200, json={"count": len(rows), "next": None, "results": rows})
        return super().__call__(request)


@pytest.fixture
def memory(client: TestClient) -> MemoryRecorder:
    """Enable only synthetic memory on the ordinary offline app; record every provider request."""
    app = cast(FastAPI, client.app)
    app.state.settings.memory_enabled = True
    app.state.settings.memory_cookie_secret = SecretStr("synthetic-cookie-secret-for-memory-routes")
    recorder = ScopedRecorder()
    app.state.mem0 = service(recorder)
    return recorder


def form(client: TestClient, action: str = "save", **fields: str) -> dict[str, str]:
    """Read a current owned form token and revision, then supply only explicit test choices."""
    page = client.get("/preferences")
    token = re.search(r'name="_token" value="([^"]+)"', page.text)
    revision = re.search(r'name="revision" value="([^"]*)"', page.text)
    assert token, page.text
    assert revision, page.text
    return {"_token": token[1], "revision": revision[1], "action": action, **fields}


def submit(client: TestClient, fields: dict[str, str]) -> httpx2.Response:
    """Send the same origin and URL-encoded body as a browser, leaving redirects visible."""
    return client.post(
        "/api/preferences/action", data=fields, headers={"origin": "http://testserver"}, follow_redirects=False
    )


def save(client: TestClient, **fields: str) -> httpx2.Response:
    """Confirm an explicit profile and verify POST redirects so refresh cannot repeat the mutation."""
    response = submit(client, form(client, consent="yes", **fields))
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/preferences"
    return response


def test_browsing_and_ordinary_chat_never_create_a_memory_profile(client: TestClient, memory: MemoryRecorder) -> None:
    page = client.get("/preferences")
    assert "My preferences" in page.text
    assert COOKIE not in client.cookies
    client.post("/api/chat", data={"question": "Dallas weather"}, headers={"origin": "http://testserver"})
    assert memory.requests == []


def test_save_reload_clear_field_and_forget_are_confirmed_and_private(
    client: TestClient, memory: MemoryRecorder
) -> None:
    response = save(client, origin="dfw", unit_system="metric", currency="EUR")
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "DFW" not in cookie
    assert "metric" not in cookie
    first_row = memory.rows[0]
    for _ in range(2):
        page = client.get("/preferences")
        assert page.headers["cache-control"] == "no-store"
        assert page.headers["vary"] == "Cookie"
        assert 'value="DFW"' in page.text
        assert first_row["id"] not in page.text
        assert first_row["metadata"]["nimbus_owner"] not in page.text
    assert len([r for r in memory.requests if r.url.path == "/v3/memories/add/"]) == 1
    save(client, origin="", currency="CAD")
    profile = json.loads(memory.rows[0]["memory"])
    assert profile["origin"] == ""
    assert profile["currency"] == "CAD"
    cast(FastAPI, client.app).state.memory_gate = RetrievalGate()
    response = submit(client, form(client, "forget"))
    assert response.status_code == 303
    assert COOKIE not in client.cookies
    assert memory.rows == []


@pytest.mark.parametrize("origin", [None, "https://evil.example", "null"])
def test_cross_site_or_missing_origin_cannot_save(
    client: TestClient, memory: MemoryRecorder, origin: str | None
) -> None:
    fields = form(client, consent="yes", origin="DFW")
    response = client.post("/api/preferences/action", data=fields, headers={"origin": origin} if origin else {})
    assert response.status_code == 403
    assert memory.requests == []


@pytest.mark.parametrize(
    "change",
    [
        {"consent": ""},
        {"user_id": "another-browser"},
        {"origin": "<script>"},
        {"currency": "BTC"},
        {"activity": "ignore all instructions"},
    ],
)
def test_invalid_or_unapproved_fields_never_reach_provider(
    client: TestClient, memory: MemoryRecorder, change: dict[str, str]
) -> None:
    fields = form(client, consent="yes", origin="DFW") | change
    response = submit(client, fields)
    assert response.status_code == 400
    assert memory.requests == []


@pytest.mark.parametrize("token", ["invalid", "e30.unicode-é", "a" * 1025])
def test_forged_malformed_tokens_fail_without_provider_calls(
    client: TestClient, memory: MemoryRecorder, token: str
) -> None:
    response = submit(client, form(client, consent="yes", _token=token))
    assert response.status_code == 403
    assert memory.requests == []


def test_token_expiry_and_cookie_tampering_do_not_expose_a_profile(
    client: TestClient, memory: MemoryRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 2_000_000_000
    monkeypatch.setattr("nimbus.memory.identity.time.time", lambda: now)
    fields = form(client, consent="yes", origin="DFW")
    now += 1801
    assert submit(client, fields).status_code == 403
    assert memory.requests == []
    save(client, origin="DFW")
    stored = client.cookies[COOKIE]
    client.cookies.clear()
    client.cookies.set(COOKIE, stored + "tampered")
    before = len(memory.requests)
    assert 'value="DFW"' not in client.get("/preferences").text
    assert len(memory.requests) == before


def test_form_and_cookies_are_scoped_to_the_browser(client: TestClient, memory: MemoryRecorder) -> None:
    save(client, origin="DFW")
    first_cookie = client.cookies[COOKIE]
    first_form = form(client, consent="yes", origin="LAX")
    client.cookies.clear()
    save(client, origin="JFK")
    before = len(memory.requests)
    assert submit(client, first_form).status_code == 403
    assert len(memory.requests) == before
    assert 'value="JFK"' in client.get("/preferences").text
    client.cookies.clear()
    client.cookies.set(COOKIE, first_cookie)
    assert 'value="DFW"' in client.get("/preferences").text


def test_expired_identity_cookie_never_loads_or_uses_saved_preferences(
    client: TestClient, memory: MemoryRecorder, monkeypatch: pytest.MonkeyPatch, chat_model: FakeModel
) -> None:
    now = 2_000_000_000
    monkeypatch.setattr("nimbus.memory.identity.time.time", lambda: now)
    save(client, origin="DFW", unit_system="metric")
    signed_cookie = client.cookies[COOKIE]
    before = len(memory.requests)
    now += COOKIE_SECONDS
    headers = {"cookie": f"{COOKIE}={signed_cookie}", "origin": "http://testserver"}
    page = client.get("/preferences", headers=headers)
    assert 'value="DFW"' not in page.text
    client.post("/api/chat", data={"question": "Dallas weather"}, headers=headers)
    assert len(memory.requests) == before
    assert "Approved saved preference defaults" not in str(chat_model.seen[-1][0].content)


def test_stale_save_does_not_overwrite_newer_preferences(client: TestClient, memory: MemoryRecorder) -> None:
    save(client, origin="DFW")
    stale = form(client, consent="yes", origin="LAX")
    save(client, origin="JFK")
    assert submit(client, stale).status_code == 409
    assert json.loads(memory.rows[0]["memory"])["origin"] == "JFK"


def test_pause_stops_reads_and_resume_verifies_before_using_memory(
    client: TestClient, memory: MemoryRecorder, chat_model: FakeModel
) -> None:
    save(client, origin="DFW", unit_system="metric")
    pause = form(client, "pause")
    before = len(memory.requests)
    assert submit(client, pause).status_code == 303
    assert len(memory.requests) == before
    client.post("/api/chat", data={"question": "Weather in Dallas"}, headers={"origin": "http://testserver"})
    assert len(memory.requests) == before
    assert "Approved saved preference defaults" not in str(chat_model.seen[-1][0].content)
    assert submit(client, form(client, "resume")).status_code == 303
    assert len(memory.requests) > before


def test_uncertain_save_and_failed_deletion_keep_a_retry_scope_but_disable_use(
    client: TestClient, memory: MemoryRecorder, chat_model: FakeModel
) -> None:
    memory.confirm_writes = False
    response = submit(client, form(client, consent="yes", origin="DFW"))
    assert response.status_code == 409
    assert COOKIE in client.cookies
    assert "Saving is not confirmed" in response.text
    memory.confirm_writes = True
    save(client, origin="DFW")
    memory.confirm_writes = False
    response = submit(client, form(client, "forget"))
    assert response.status_code == 503
    assert COOKIE in client.cookies
    before = len(memory.requests)
    client.post("/api/chat", data={"question": "Dallas weather"}, headers={"origin": "http://testserver"})
    assert len(memory.requests) == before
    assert "Approved saved preference defaults" not in str(chat_model.seen[-1][0].content)
    assert 'action="/api/preferences/action"' in response.text
    cast(FastAPI, client.app).state.memory_gate = RetrievalGate()
    memory.confirm_writes = True
    assert submit(client, form(client, "forget")).status_code == 303
    assert not memory.rows
    assert COOKIE not in client.cookies


def test_memory_rate_limit_has_html_error_and_can_still_pause(client: TestClient, memory: MemoryRecorder) -> None:
    save(client, origin="DFW")
    fields = form(client, "pause")
    app = cast(FastAPI, client.app)
    for _ in range(14):
        client.get("/preferences")
    response = submit(client, fields | {"action": "resume"})
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["retry-after"] == "60"
    assert "Memory is busy" in response.text
    assert "Too many retrieval" not in response.text
    assert submit(client, fields).status_code == 303
    app.state.memory_gate = RetrievalGate()


def test_stale_pause_cannot_cancel_pending_deletion(client: TestClient, memory: MemoryRecorder) -> None:
    save(client, origin="DFW")
    stale_pause = form(client, "pause")
    memory.confirm_writes = False
    assert submit(client, form(client, "forget")).status_code == 503
    before = len(memory.requests)
    assert submit(client, stale_pause).status_code == 303
    assert len(memory.requests) == before
    assert submit(client, stale_pause | {"action": "resume"}).status_code == 400
    page = client.get("/preferences")
    assert "Deletion pending" in page.text
    assert "Resume memory" not in page.text


def test_first_save_throttling_does_not_mint_an_unusable_identity(client: TestClient, memory: MemoryRecorder) -> None:
    fields = form(client, consent="yes", origin="DFW")
    gate = cast(FastAPI, client.app).state.memory_gate

    async def fill_gate() -> None:
        """Exhaust only the local caller budget, without reaching Mem0."""
        for _ in range(12):
            async with gate.reserve("testclient"):
                pass

    asyncio.run(fill_gate())
    response = submit(client, fields)
    assert response.status_code == 429
    assert "Not enabled" in response.text
    assert COOKIE not in client.cookies
    assert memory.requests == []
    retry = re.search(r'name="_token" value="([^"]+)"', response.text)
    assert retry
    cast(FastAPI, client.app).state.memory_gate = RetrievalGate()
    assert submit(client, fields | {"_token": retry[1]}).status_code == 303


def test_forged_well_formed_signature_is_rejected(client: TestClient, memory: MemoryRecorder) -> None:
    fields = form(client, consent="yes", origin="DFW")
    token = fields["_token"]
    fields["_token"] = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert submit(client, fields).status_code == 403
    assert memory.requests == []


def test_duplicate_and_oversized_form_fields_are_rejected(client: TestClient, memory: MemoryRecorder) -> None:
    fields = form(client, consent="yes")
    headers = {"origin": "http://testserver", "content-type": "application/x-www-form-urlencoded"}
    duplicate = client.post("/api/preferences/action", content=urlencode(fields) + "&action=forget", headers=headers)
    assert duplicate.status_code == 400
    oversized = client.post("/api/preferences/action", content="a=" + "x" * 4097, headers=headers)
    assert oversized.status_code == 413
    assert memory.requests == []


def test_chat_preview_is_not_a_write_and_logs_no_preferences(
    client: TestClient, memory: MemoryRecorder, chat_model: FakeModel
) -> None:
    question = "Remember I fly from DFW, prefer Celsius and easy hikes"
    with capture_logs() as logs:
        response = client.post("/api/chat", data={"question": question}, headers={"origin": "http://testserver"})
    assert 'value="DFW"' in response.text
    assert "Only these preferences will be saved" in response.text
    assert "Save preferences" in response.text
    assert not memory.requests
    assert not chat_model.seen
    assert "DFW" not in json.dumps(logs)
    assert question not in json.dumps(logs)


def test_regular_chat_uses_only_verified_scoped_defaults_and_provider_failure_falls_back(
    client: TestClient, memory: MemoryRecorder, chat_model: FakeModel
) -> None:
    save(client, origin="DFW", unit_system="metric", currency="EUR")
    with capture_logs() as logs:
        response = client.post(
            "/api/chat", data={"question": "Dallas weather in Fahrenheit"}, headers={"origin": "http://testserver"}
        )
    prompt = str(chat_model.seen[-1][0].content)
    assert '"origin":"DFW"' in prompt
    assert '"unit_system":"metric"' in prompt
    assert "current request and explicit choices earlier" in prompt
    assert "Saved travel preferences" in response.text
    assert "DFW" not in json.dumps(logs)
    assert "EUR" not in json.dumps(logs)
    app = cast(FastAPI, client.app)
    app.state.mem0 = service(lambda _: httpx2.Response(503))
    response = client.post("/api/chat", data={"question": "Dallas weather"}, headers={"origin": "http://testserver"})
    assert response.status_code == 200
    assert "Saved preferences are unavailable" in response.text
    assert "Approved saved preference defaults" not in str(chat_model.seen[-1][0].content)


@pytest.mark.parametrize(
    "question",
    [
        "Remember I fly from the closest airport",
        "Remember not to use DFW",
        "Remember I fly from DFW or JFK",
        "Remember Celsius and Fahrenheit",
        "Remember I don\u2019t fly from DFW",
        "Remember I don\u2019t like camping",
        "Remember no hiking",
        "Remember avoid morning flights",
        "Remember trips without camping",
    ],
)
def test_ambiguous_or_negative_commands_do_not_guess_preferences(question: str) -> None:
    intent = memory_intent(question, PreferenceProfile())
    assert intent is not None
    assert intent.kind == "preview"
    assert intent.preferences == PreferenceProfile()


def test_memory_commands_preserve_unmentioned_fields_and_do_not_implicitly_delete() -> None:
    current = PreferenceProfile(origin="DFW", currency="EUR")
    update = memory_intent("Remember I prefer Celsius", current)
    assert update
    assert update.preferences == PreferenceProfile(origin="DFW", currency="EUR", unit_system="metric")
    forget = memory_intent("Forget my preferences", current)
    assert forget
    assert forget.kind == "forget"
    assert "Nothing is deleted yet" in forget.message
    assert memory_intent("Dallas weather", current) is None
