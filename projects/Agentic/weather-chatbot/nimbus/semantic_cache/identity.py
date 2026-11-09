"""Anonymous cache scopes and authenticated neutral-history receipts, separate from preference consent."""

import hashlib
import hmac
import re
import time
from collections.abc import Sequence
from html.parser import HTMLParser
from uuid import uuid4

from fastapi import Request, Response

from nimbus.semantic_cache.policy import digest, normalized

COOKIE = "nimbus_weather_cache"
COOKIE_SECONDS = 86400


def signature(secret: str, purpose: str, value: str) -> str:
    """Domain-separate cache authentication from every other use of the database credential."""
    return hmac.new(secret.encode(), f"nimbus-cache:{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def read_scope(request: Request) -> str | None:
    """Verify a bounded anonymous cookie before deriving a private, opaque Qdrant partition."""
    key = request.app.state.settings.qdrant_api_key
    token = request.cookies.get(COOKIE, "")
    if key is None or re.fullmatch(r"[a-f0-9]{32}\.\d{10}\.[a-f0-9]{64}", token) is None:
        return None
    value, signed = token.rsplit(".", 1)
    expires = int(value.split(".")[1])
    if not time.time() < expires <= time.time() + COOKIE_SECONDS + 60:
        return None
    secret = key.get_secret_value()
    if not hmac.compare_digest(signature(secret, "cookie", value), signed):
        return None
    return signature(secret, "scope", value)


def new_scope(request: Request) -> tuple[str, str]:
    """Prepare a one-day cache identity without enabling Mem0 or recording a person's identity."""
    secret = request.app.state.settings.qdrant_api_key.get_secret_value()
    value = f"{uuid4().hex}.{int(time.time()) + COOKIE_SECONDS}"
    return signature(secret, "scope", value), f"{value}.{signature(secret, 'cookie', value)}"


def set_scope(response: Response, request: Request, token: str) -> None:
    """Set a script-inaccessible, same-site cookie only for an eligible cache request."""
    if token:
        response.set_cookie(
            COOKIE,
            token,
            max_age=COOKIE_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )


class _Text(HTMLParser):
    """Extract rendered Markdown text with the block boundaries the browser includes in innerText."""

    def __init__(self) -> None:
        """Start with no rendered text."""
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        """Preserve inline text exactly."""
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Separate visible block content while preserving adjacent inline markup."""
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "pre", "blockquote", "tr", "td", "th"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        """Separate block endings consistently with their starts."""
        self.handle_starttag(tag, [])


def plain_answer(html: str) -> str:
    """Normalize only rendered text; receipts never trust browser-authored assistant instructions."""
    parser = _Text()
    parser.feed(html)
    return normalized("".join(parser.parts))


def history_digest(history: Sequence[tuple[str, str]]) -> str:
    """Bind the complete bounded conversation, including every role and answer."""
    return digest([(role, normalized(text)) for role, text in history])


def receipt(secret: str, scope: str, context: str, history: Sequence[tuple[str, str]]) -> str:
    """Authenticate an exclusively cache-eligible conversation under its browser and preference context."""
    return signature(secret, "history", f"{scope}:{context}:{history_digest(history[-10:])}")


def valid_receipt(secret: str, scope: str, context: str, history: Sequence[tuple[str, str]], supplied: str) -> bool:
    """No history is neutral by default; a forged or changed conversation must use Gemini."""
    return not history or (
        re.fullmatch(r"[a-f0-9]{64}", supplied) is not None
        and hmac.compare_digest(receipt(secret, scope, context, history), supplied)
    )
