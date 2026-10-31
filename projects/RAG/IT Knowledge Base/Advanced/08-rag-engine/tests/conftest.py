"""
Shared test setup: no test can reach Google. Every HTTP request an httpx client tries to send (Google's client uses
httpx) fails at once, so a test that would call Gemini by mistake fails instead of spending the key's quota.
"""
import httpx
import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("Blocked: a test tried to reach the network")

    monkeypatch.setattr(httpx.Client, "send", refuse)
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
