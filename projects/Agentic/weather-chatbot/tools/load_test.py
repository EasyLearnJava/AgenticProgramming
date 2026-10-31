"""
tools/load_test.py: a small load test (step 13), against a running Nimbus: the chat page and the health check, many at
once, and a few questions among them; each request timed to its last byte, then, for each kind, how many, how many
failed, and the p50, p95 and slowest. A question is a few calls to Gemini, so only a few are asked: its free tier takes
15 a minute. Once the firewall's rate limit is on, more than 20 calls a minute to /api/* from one address get its 429,
counted as failures, which is the limit working. From the project's folder, in bash:

    uv run python -m tools.load_test https://weather-chatbot-hazel.vercel.app
    uv run python -m tools.load_test http://127.0.0.1:8000 40 3 8
"""

import asyncio
import math
import sys
import time
import urllib.parse
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Final

import httpx2

PAGES: Final = 40
QUESTIONS: Final = 3
AT_ONCE: Final = 8
REQUEST_SECONDS: Final = 90
QUESTION: Final = "Will it rain in Paris tomorrow?"
USAGE = "usage: uv run python -m tools.load_test <the app's address> [pages and health checks] [questions] [at once]"


@dataclass(frozen=True)
class Timed:
    """One request: its kind, whether it worked, and how long it took, to its last byte."""

    kind: str
    ok: bool
    seconds: float


async def timed(kind: str, send: Callable[[], Awaitable[bool]]) -> Timed:
    """A request, timed: it worked when it says so; one that can't be made is a failure, with its time."""
    started = time.perf_counter()
    try:
        ok = await send()
    except httpx2.HTTPError:
        ok = False
    return Timed(kind, ok, time.perf_counter() - started)


async def get_ok(http: httpx2.AsyncClient, url: str) -> bool:
    """A GET, read to its last byte: it worked with a 200."""
    response = await http.get(url)
    return response.status_code == 200


async def ask_ok(http: httpx2.AsyncClient, base: str) -> bool:
    """A question on REST · no auth, its stream read to its end: it worked when the answer ended well."""
    form = {"question": QUESTION, "locale": "en-US", "time_zone": "America/Chicago", "lane": "rest-no-auth"}
    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with http.stream("POST", f"{base}/api/chat", content=urllib.parse.urlencode(form), headers=headers) as sent:
        body = "".join([chunk async for chunk in sent.aiter_text()])
    return sent.status_code == 200 and "tool-chip-done" in body and "message-error" not in body


async def run_load(http: httpx2.AsyncClient, base: str, pages: int, questions: int, at_once: int) -> list[Timed]:
    """The page and the health check, each so many times, and the questions, at most so many at once."""
    limit = asyncio.Semaphore(at_once)

    async def one(kind: str, send: Callable[[], Awaitable[bool]]) -> Timed:
        """One request, once a place is free."""
        async with limit:
            return await timed(kind, send)

    jobs = [one("question", lambda: ask_ok(http, base)) for _ in range(questions)]
    for _ in range(pages):
        jobs.append(one("page", lambda: get_ok(http, f"{base}/")))
        jobs.append(one("health", lambda: get_ok(http, f"{base}/api/health")))
    return list(await asyncio.gather(*jobs))


def percentile(seconds: Sequence[float], share: float) -> float:
    """The time below which that share of the requests ended (the nearest rank)."""
    ordered = sorted(seconds)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def to_summary(results: Sequence[Timed]) -> list[str]:
    """For each kind: how many, how many failed, and the p50, p95 and slowest, in seconds."""
    lines = []
    for kind in ("page", "health", "question"):
        times = [result.seconds for result in results if result.kind == kind]
        if not times:
            continue
        failed = sum(not result.ok for result in results if result.kind == kind)
        lines.append(
            f"{kind:8} {len(times):3} sent, {failed} failed · p50 {percentile(times, 0.5):.2f} s, "
            f"p95 {percentile(times, 0.95):.2f} s, slowest {max(times):.2f} s"
        )
    return lines


async def run(base: str, pages: int, questions: int, at_once: int) -> int:
    """The load, then its summary; 1 if any request failed."""
    async with httpx2.AsyncClient(timeout=REQUEST_SECONDS) as http:
        started = time.perf_counter()
        results = await run_load(http, base, pages, questions, at_once)
        seconds = time.perf_counter() - started
    print(f"{base}: {len(results)} requests, at most {at_once} at once, in {seconds:.1f} s")
    print("\n".join(to_summary(results)))
    return 0 if all(result.ok for result in results) else 1


def main() -> int:
    """The app's address, and the counts, from the command line."""
    arguments = sys.argv[1:]
    if not 1 <= len(arguments) <= 4 or not all(argument.isdigit() for argument in arguments[1:]):
        print(USAGE)
        return 2
    counts = [int(argument) for argument in arguments[1:]] + [PAGES, QUESTIONS, AT_ONCE][len(arguments) - 1 :]
    return asyncio.run(run(arguments[0].rstrip("/"), *counts))


if __name__ == "__main__":
    sys.exit(main())
