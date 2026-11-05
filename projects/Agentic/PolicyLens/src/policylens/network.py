"""One HTTP client factory: OS certificate trust in the app, mock transport in tests."""

import ssl

import httpx


def create_http_client() -> httpx.Client:
    # Keep TLS verification enabled and respect enterprise roots installed in Windows.
    return httpx.Client(verify=ssl.create_default_context())

