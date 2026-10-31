"""
nimbus/axiom.py: the app's log lines, to Axiom (step 12). Vercel's Hobby plan keeps logs for an hour and can't forward
them, so the app does it itself: each line is kept as it's written, and a request's end sends what's kept, in one
batch, within 2 s, while Vercel keeps the function alive for it (middleware.py). Sending never fails a request: a
batch Axiom doesn't take is said on stderr, which Vercel's logs keep, and dropped.
"""

import asyncio
import json
import sys
from collections.abc import Callable
from urllib.parse import quote

import httpx2
from pydantic import SecretStr

from nimbus.config import Settings
from nimbus.constants import AXIOM_INGEST_HOST, AXIOM_MAX_WAITING_LINES, AXIOM_SEND_SECONDS


def to_ingest_url(dataset: str) -> str:
    """Axiom's ingest address for the dataset; the time of each event is its line's own ts."""
    return f"https://{AXIOM_INGEST_HOST}/v1/ingest/{quote(dataset, safe='')}?timestamp-field=ts"


def report(event: str, **fields: object) -> None:
    """A line about the sending itself, on stderr: never through the logger, whose lines come back here."""
    print(json.dumps({"level": "warning", "event": event, **fields}), file=sys.stderr, flush=True)


class LogShipper:
    """
    Keeps each line it's given; send() posts them to Axiom as NDJSON, with the token, in one request. Past 1,000 lines
    waiting, a line is dropped and counted, so a send that never comes can't fill the memory.
    """

    def __init__(
        self, dataset: str, token: SecretStr, make_client: Callable[[], httpx2.AsyncClient] = httpx2.AsyncClient
    ) -> None:
        """A shipper into the dataset, with its token; each send gets a new HTTP client (the tests give their own)."""
        self.url = to_ingest_url(dataset)
        self._token = token
        self._make_client = make_client
        self._waiting: list[str] = []
        self._dropped = 0

    def write(self, line: str) -> None:
        """Keeps a line as it was written, unless 1,000 are waiting already."""
        if len(self._waiting) >= AXIOM_MAX_WAITING_LINES:
            self._dropped += 1
            return
        self._waiting.append(line)

    async def send(self) -> None:
        """
        Sends every line waiting, in one request within 2 s. A batch Axiom refuses, or can't be reached for, is said on
        stderr, by its status or its class, never with the token, and dropped; so are lines that didn't fit, counted.
        """
        # Taken before the first await: a request that ends meanwhile sends only what comes after.
        lines, dropped = self._waiting, self._dropped
        self._waiting, self._dropped = [], 0
        if dropped:
            report("axiom.dropped", lines=dropped)
        if not lines:
            return
        headers = {"authorization": f"Bearer {self._token.get_secret_value()}", "content-type": "application/x-ndjson"}
        try:
            async with asyncio.timeout(AXIOM_SEND_SECONDS), self._make_client() as http:
                response = await http.post(self.url, content="\n".join(lines) + "\n", headers=headers)
        except Exception as error:
            report("axiom.failed", reason=type(error).__name__, lines=len(lines))
            return
        if not response.is_success:
            report("axiom.failed", httpStatus=response.status_code, lines=len(lines))


def make_log_shipper(settings: Settings) -> LogShipper | None:
    """Axiom's shipper, when the settings have its token and its dataset; else None, and lines stay in Vercel's logs."""
    if settings.axiom_token is None or settings.axiom_dataset is None:
        return None
    return LogShipper(settings.axiom_dataset, settings.axiom_token)
