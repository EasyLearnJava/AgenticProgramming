"""Signed, expiring anonymous browser scopes and form tokens; no personal values go into a cookie."""

import base64
import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from fastapi import Request, Response
from pydantic import SecretStr

COOKIE = "nimbus_preferences"
COOKIE_SECONDS = 180 * 24 * 60 * 60
FORM_SECONDS = 30 * 60
USER_ID = re.compile(r"nimbus_[0-9a-f]{32}")
type Mode = Literal["active", "paused", "deleting"]


@dataclass(frozen=True)
class BrowserIdentity:
    """A browser bearer credential, distinct from a person or an account."""

    user_id: str
    mode: Mode = "active"
    expires: int = 0


def new_identity() -> BrowserIdentity:
    """Mint an unguessable scope only after an explicit save request."""
    return BrowserIdentity(f"nimbus_{uuid4().hex}", expires=int(time.time()) + COOKIE_SECONDS)


def _sign(payload: dict[str, object], secret: SecretStr, purpose: str) -> str:
    """Authenticate compact data with a purpose-specific signature."""
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(
        secret.get_secret_value().encode(), f"{purpose}:{encoded}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{encoded}.{signature}"


def _verify(token: str, secret: SecretStr | None, purpose: str) -> dict[str, object] | None:
    """Reject forged, oversized or expired claims before using their scope."""
    if secret is None or len(token) > 1024 or token.count(".") != 1:
        return None
    encoded, supplied = token.split(".")
    if re.fullmatch(r"[0-9a-f]{64}", supplied) is None:
        return None
    expected = hmac.new(secret.get_secret_value().encode(), f"{purpose}:{encoded}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    expires = payload.get("expires")
    if type(expires) is not int or not int(time.time()) < expires <= int(time.time()) + COOKIE_SECONDS + 60:
        return None
    return payload


def read_identity(request: Request) -> BrowserIdentity | None:
    """Resolve the browser scope only from the signed HTTP-only cookie, never submitted IDs."""
    secret = getattr(request.app.state.settings, "memory_cookie_secret", None)
    payload = _verify(request.cookies.get(COOKIE, ""), secret, "identity")
    if payload is None or set(payload) != {"user", "mode", "expires"}:
        return None
    user, mode, expires = payload["user"], payload["mode"], payload["expires"]
    if not isinstance(user, str) or USER_ID.fullmatch(user) is None or mode not in {"active", "paused", "deleting"}:
        return None
    if not isinstance(expires, int):
        return None
    return BrowserIdentity(user, mode, expires)


def set_identity(response: Response, request: Request, identity: BrowserIdentity) -> None:
    """Persist only a signed scope/mode, protected from script access and cross-site requests."""
    secret = request.app.state.settings.memory_cookie_secret
    if secret is None:
        return
    token = _sign({"user": identity.user_id, "mode": identity.mode, "expires": identity.expires}, secret, "identity")
    response.set_cookie(
        COOKIE,
        token,
        max_age=max(0, identity.expires - int(time.time())),
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


def form_token(request: Request, identity: BrowserIdentity | None) -> str:
    """A short-lived token bound to the current browser scope and separate from its cookie signature."""
    secret = request.app.state.settings.memory_cookie_secret
    if secret is None:
        return ""
    return _sign(
        {"user": identity.user_id if identity else "", "expires": int(time.time()) + FORM_SECONDS},
        secret,
        "preferences-form",
    )


def valid_form_token(request: Request, token: str, identity: BrowserIdentity | None) -> bool:
    """A form for one browser cannot edit another browser's preferences."""
    payload = _verify(token, request.app.state.settings.memory_cookie_secret, "preferences-form")
    return (
        payload is not None
        and set(payload) == {"user", "expires"}
        and payload["user"] == (identity.user_id if identity else "")
    )
