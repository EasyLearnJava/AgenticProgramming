"""Adapters from Nimbus's reviewed golden, travel and lexical park evals to public harness attempt records."""

import asyncio
import html
import math
import re
import time
from datetime import date, datetime
from typing import Any, Final
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx2

from nimbus.errors import ANSWER_TOO_SLOW, MODEL_BUSY, NOT_SET_UP
from nimbus.goldens import Golden, read_goldens
from nimbus.parks import ParkKnowledge
from nimbus.travel.models import TravelReport
from tools import eval_parks, eval_travel, evals

SMOKE: Final = {"golden": "rain-tomorrow", "travel": "trivago-direct"}
_CASE_ID = re.compile(r"[a-z0-9][a-z0-9-]*")


class _DeploymentMismatchError(Exception):
    """The response cannot be attributed to the preview requested for this run."""


def _catalog(suites: tuple[str, ...], smoke: bool) -> dict[str, list[Golden | eval_travel.TravelCase]]:
    if not suites or len(set(suites)) != len(suites) or set(suites) - SMOKE.keys():
        raise ValueError("Choose golden, travel, or both as live suites.")
    catalog: dict[str, list[Golden | eval_travel.TravelCase]] = {}
    for suite in suites:
        cases: list[Golden | eval_travel.TravelCase] = (
            list(read_goldens()) if suite == "golden" else list(eval_travel.read_cases())
        )
        ids = [case.id for case in cases]
        if not cases or len(set(ids)) != len(ids) or not all(_CASE_ID.fullmatch(key) for key in ids):
            raise ValueError(f"Invalid case IDs in {suite}.")
        if smoke:
            cases = [case for case in cases if case.id == SMOKE[suite]]
            if not cases:
                raise ValueError(f"Missing smoke case in {suite}.")
        catalog[suite] = cases
    return catalog


def live_catalog(suites: tuple[str, ...], *, smoke: bool = False) -> dict[str, set[str]]:
    """The expected population of a live scorecard, taken from the versioned fixtures."""
    return {suite: {case.id for case in cases} for suite, cases in _catalog(suites, smoke).items()}


def _response_issue(answer: evals.Answer, status: int, final: str) -> str | None:
    """Tell an incomplete stream, missing setup or server timeout apart from a grading failure."""
    note = evals.to_text(final) if answer.failed else ""
    if status == 429 or MODEL_BUSY in note:
        return "request_throttled"
    if status == 504 or ANSWER_TOO_SLOW in note:
        return "answer_timeout_after_tools" if answer.tools else "answer_timeout_before_tools"
    if NOT_SET_UP in note:
        return "model_not_configured"
    if status != 200 or answer.failed:
        return "answer_failed"
    if evals.ANSWER_FRAGMENT.search(final) is None or 'aria-busy="true"' in final:
        return "incomplete_response"
    return None


def _provider_calls(final: str) -> list[dict[str, str]]:
    """Report each travel tool chip's validated provider and status, without parameters or offer data."""
    calls = []
    for chip in eval_travel.CHIP.findall(final):
        name = eval_travel.NAME.search(chip)
        if name is None or name[1] not in eval_travel.PROVIDERS:
            continue
        provider = eval_travel.PROVIDERS[name[1]]
        output = eval_travel.OUTPUT.search(chip)
        status = "unverified"
        if output:
            try:
                report = TravelReport.model_validate_json(html.unescape(output[1]))
                if report.provider == provider:
                    status = report.status
            except (ValueError, RecursionError):
                pass  # Include the missing evidence in the denominator without exposing its contents.
        calls.append({"provider": provider, "status": status})
    return calls


def _golden_outcome(case: Golden, answer: evals.Answer, final: str) -> str:
    """Apply the exact existing golden rules to the final narrative; exclude adjacent source and quote cards."""
    if not answer.text:
        return "incomplete_response"
    misses = evals.grade(case, answer)
    if 'class="tool-chip tool-chip-failed"' in final:
        return "tool_failed"
    for reason in misses:
        if reason.startswith("called ["):
            return "required_tool_sequence"
        if reason.startswith("called "):
            return "forbidden_tool"
        if reason.startswith(("missing citation", "unexpected citation")):
            return "source_mismatch"
    return "wording_failed" if misses else "pass"


async def _attempt(
    http: httpx2.AsyncClient, base: str, case: Golden | eval_travel.TravelCase, today: date, checks: list[str]
) -> tuple[str, list[dict[str, str]]]:
    observed: list[tuple[int, str]] = []
    golden = case.golden(today) if isinstance(case, eval_travel.TravelCase) else case
    history = case.history if isinstance(case, eval_travel.TravelCase) else ()
    try:
        # The HTTP read timeout covers inactivity; this also bounds a slow, continuously streaming answer.
        async with asyncio.timeout(evals.ANSWER_SECONDS):
            answer = await evals.ask(
                http, base, golden, history=history, observe=lambda code, body: observed.append((code, body))
            )
    except _DeploymentMismatchError:
        return "deployment_mismatch", []
    except (TimeoutError, httpx2.TimeoutException):
        return "client_timeout", []
    except httpx2.HTTPError:
        return "connection_failed", []
    status, final = observed[0]
    calls = _provider_calls(final)
    issue = _response_issue(answer, status, final)
    if issue:
        return issue, calls
    if isinstance(case, eval_travel.TravelCase):
        return eval_travel.outcome(case, today, answer, status, final, checks=checks), calls
    return _golden_outcome(case, answer, final), calls


async def live_cases(
    base_url: str,
    *,
    suites: tuple[str, ...] = ("golden", "travel"),
    repeats: int = 3,
    pause: float = 40,
    smoke: bool = False,
    expected_deployment: str | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> list[dict[str, Any]]:
    """Run synthetic questions against one Nimbus origin, retaining all attempts including transport failures."""
    target = urlsplit(base_url)
    if (
        target.scheme not in {"http", "https"}
        or not target.hostname
        or target.username is not None
        or target.password is not None
        or target.query
        or target.fragment
        or target.path not in {"", "/"}
    ):
        raise ValueError("Use a Nimbus origin without credentials, path, query, or fragment.")
    if repeats not in range(1, 6) or not math.isfinite(pause) or pause < 0:
        raise ValueError("Choose one to five attempts and a finite nonnegative pause.")
    if expected_deployment is not None and not re.fullmatch(r"dpl_[a-zA-Z0-9_-]{1,96}", expected_deployment):
        raise ValueError("Invalid preview deployment identifier.")

    async def verify_preview(response: httpx2.Response) -> None:
        if response.headers.get("x-nimbus-deployment") != expected_deployment:
            raise _DeploymentMismatchError

    catalog = _catalog(suites, smoke)
    rows: list[dict[str, Any]] = []
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    async with httpx2.AsyncClient(
        timeout=evals.ANSWER_SECONDS,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        event_hooks={"response": [verify_preview]} if expected_deployment else None,
    ) as http:
        for attempt in range(1, repeats + 1):
            for suite, cases in catalog.items():
                for case in cases:
                    if rows and pause:
                        await asyncio.sleep(pause)
                    start = time.perf_counter()
                    checks: list[str] = []
                    outcome, providers = await _attempt(http, base_url.rstrip("/"), case, today, checks)
                    rows.append(
                        {
                            "suite": suite,
                            "case_id": case.id,
                            "attempt": attempt,
                            "outcome": outcome,
                            "duration_ms": round((time.perf_counter() - start) * 1000),
                            "provider_calls": providers,
                            "checks": checks,
                        }
                    )
    return rows


async def park_cases() -> list[dict[str, Any]]:
    """Run the existing graded retrieval cases once on the bundled SQLite index with local keyword retrieval."""
    knowledge = ParkKnowledge(eval_parks.INDEX_PATH)
    rows = []
    cases = eval_parks.read_cases()  # The existing reader rejects duplicate IDs.
    if not cases or not all(_CASE_ID.fullmatch(case.id) for case in cases):
        raise ValueError("Invalid case IDs in parks.")
    for case in cases:
        start = time.perf_counter()
        (result,) = await eval_parks.run_cases(knowledge, [case])
        rows.append(
            {
                "suite": "parks",
                "case_id": case.id,
                "attempt": 1,
                "outcome": "pass" if result.passed else "retrieval_mismatch",
                "duration_ms": round((time.perf_counter() - start) * 1000),
            }
        )
    return rows
