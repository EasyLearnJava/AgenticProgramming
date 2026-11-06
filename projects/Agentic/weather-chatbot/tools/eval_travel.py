"""Run the opt-in synthetic chat travel suite. Only case IDs, run numbers and fixed outcome codes reach stdout."""

import argparse
import asyncio
import html
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

import httpx2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from nimbus.constants import PROJECT_ROOT
from nimbus.errors import ANSWER_TOO_SLOW, MODEL_BUSY
from nimbus.goldens import Expect, Golden
from nimbus.travel.models import FlightSearch, HotelSearch, TravelReport
from tools.evals import ANSWER_FRAGMENT, ANSWER_SECONDS, PAUSE_SECONDS, Answer, ask, grade, to_text
from tools.travel_claims import check_claims

CASES: Final = PROJECT_ROOT / "evals" / "travel.json"
PROVIDERS: Final = {"search_flights": "kiwi", "search_hotels": "trivago"}
CHIP: Final = re.compile(r'<li class="tool-chip tool-chip-[^"]+"[^>]*>.*?</details>\s*</li>', re.S)
NAME: Final = re.compile(r'<code class="tool-chip-name">([^<]+)</code>')
INPUT: Final = re.compile(r'<p class="tool-chip-label">Input</p>\s*<pre>(.*?)</pre>', re.S)
OUTPUT: Final = re.compile(r'<p class="tool-chip-label">Output</p>\s*<pre>(.*?)</pre>', re.S)
LINK: Final = re.compile(r'<a\b[^>]*\bhref="([^"]+)"')


def _dates(today: date) -> dict[str, str]:
    """The date placeholders shared by the synthetic question and its expected tool calls."""
    return {
        key: (today + timedelta(days=days)).isoformat()
        for key, days in (("arrival", 5), ("departure", 8), ("far_arrival", 40), ("far_departure", 43))
    }


class TravelCase(BaseModel):
    """Expected behavior defined before any provider or model is called."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    question: str
    expected_args: dict[str, dict[str, object]] = Field(default_factory=dict)
    requires: tuple[str, ...] = ()
    forbids: tuple[str, ...] = ()
    says: list[str] = Field(default_factory=list)
    intake: dict[str, str] = Field(default_factory=dict)
    history: list[dict[str, str]] = Field(default_factory=list)

    def golden(self, today: date) -> Golden:
        """Resolve dates once per run so future searches keep their intended forecast-window relationship."""
        return Golden(
            id=self.id,
            question=self.question.format(**_dates(today)),
            expect=Expect(no_tools=list(self.forbids), says=self.says),
        )


def read_cases(path: Path = CASES) -> list[TravelCase]:
    """Reject ambiguous fixture IDs and contradictory tool expectations."""
    cases = TypeAdapter(list[TravelCase]).validate_json(path.read_bytes())
    if len({case.id for case in cases}) != len(cases) or any(set(c.requires) & set(c.forbids) for c in cases):
        raise ValueError("invalid travel evaluation cases")
    for case in cases:
        if set(case.expected_args) != set(case.requires).intersection(PROVIDERS):
            raise ValueError(f"missing or extra expected travel arguments for {case.id}")
    return cases


def _place(value: object) -> str:
    """Compare case and punctuation while allowing a country suffix on the named US cities in the fixtures."""
    words = re.sub(r"[,.]", " ", str(value).casefold()).split()
    for suffix in (["united", "states", "of", "america"], ["united", "states"], ["u", "s", "a"], ["usa"], ["us"]):
        if words[-len(suffix) :] == suffix:
            words = words[: -len(suffix)]
            break
    return " ".join(words)


def _arguments_match(tool: str, actual: dict[str, object], expected: dict[str, object], today: date) -> bool:
    """Compare the complete validated query, including default occupancy and any unrequested filters."""
    fields = {
        key: value.format(**_dates(today)) if isinstance(value, str) else value for key, value in expected.items()
    }
    schema = FlightSearch if tool == "search_flights" else HotelSearch
    for key in ("origin", "destination"):
        if key not in fields:
            continue
        value = fields[key]
        accepted = value if isinstance(value, list) else [value]
        if _place(actual.get(key)) not in {_place(place) for place in accepted}:
            return False
        fields[key] = actual[key]
    return schema.model_validate(fields) == schema.model_validate(actual)


def _evidence(case: TravelCase, final: str, tools: list[str], today: date) -> tuple[list[TravelReport], str | None]:
    """Bind each normalized result and actual input to its own named tool chip, independently of call order."""
    reports = []
    for chip in CHIP.findall(final):
        name = NAME.search(chip)
        if not name or name[1] not in PROVIDERS:
            continue
        tool = name[1]
        sent, returned = INPUT.search(chip), OUTPUT.search(chip)
        if not sent or not returned:
            return [], "missing_travel_artifact"
        try:
            args = json.loads(html.unescape(sent[1]))
            if not isinstance(args, dict) or tool not in case.expected_args:
                return [], "wrong_search_arguments"
            if not _arguments_match(tool, args, case.expected_args[tool], today):
                return [], "wrong_search_arguments"
            report = TravelReport.model_validate_json(html.unescape(returned[1]))
        except (ValueError, RecursionError):
            return [], "invalid_travel_artifact"
        if report.provider != PROVIDERS[tool]:
            return [], "invalid_travel_artifact"
        reports.append(report)
    expected = Counter(PROVIDERS[name] for name in tools if name in PROVIDERS)
    if Counter(report.provider for report in reports) != expected:
        return [], "missing_travel_artifact"
    return reports, None


class _PlannerForm(HTMLParser):
    """Inspect the action, method and preselected fields the visitor would submit."""

    def __init__(self) -> None:
        super().__init__()
        self.count = 0
        self.active = False
        self.method = ""
        self.select = ""
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track only controls belonging to the planner form."""
        fields = dict(attrs)
        if tag == "form":
            self.active = (
                fields.get("action") == "/api/parks/briefing" and "trip-form" in (fields.get("class") or "").split()
            )
            if self.active:
                self.count += 1
                self.method = (fields.get("method") or "get").lower()
        if not self.active or "disabled" in fields:
            return
        name = fields.get("name") or ""
        if tag == "input" and name:
            self.values[name] = fields.get("value") or ""
        elif tag == "select":
            self.select = name
        elif tag == "option" and self.select and "selected" in fields:
            self.values[self.select] = fields.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        """Ignore controls outside the current form or select."""
        if tag == "form":
            self.active = False
        if tag in {"form", "select"}:
            self.select = ""


def outcome(
    case: TravelCase, today: date, answer: Answer, status: int, final: str, *, checks: list[str] | None = None
) -> str:
    """Grade one completed attempt, checking dynamic source identity and independent, unordered tool calls."""
    # ① An aborted answer says nothing about tools the model would have selected next.
    if status == 429 or (answer.failed and MODEL_BUSY in answer.text):
        return "request_throttled"
    if answer.failed and ANSWER_TOO_SLOW in answer.text:
        return "answer_timeout_after_tools" if answer.tools else "answer_timeout_before_tools"
    body = ANSWER_FRAGMENT.search(final)
    if status != 200 or answer.failed or body is None:
        return "answer_failed"
    form = _PlannerForm()
    form.feed(final)
    if form.count != int(bool(case.intake)):
        return "wrong_planner_routing"
    if case.intake and (form.method != "post" or not case.intake.items() <= form.values.items()):
        return "wrong_planner_intake"
    if set(case.forbids) & set(answer.tools):
        return "forbidden_tool"
    if set(case.requires) - set(answer.tools):
        return "missed_tool"
    # ② Check only words the model actually wrote. Static card labels must not satisfy a wording requirement.
    narrative = Answer(answer.tools, to_text(body[1]), False, answer.request_id)
    if not narrative.text.strip() or grade(case.golden(today), narrative):
        return "wording_failed"
    reports, failure = _evidence(case, final, answer.tools, today)
    if failure:
        return failure
    if reason := check_claims(body[1], reports):
        if reason.startswith("quote_review_"):
            if checks is not None:
                checks.append(reason)
            return "quote_needs_review"
        return reason
    if reports:
        # ③ A direct travel answer may link only to returned offers; a displayed quote link must be clickable.
        sources = {offer.url for report in reports for offer in report.offers if offer.url}
        cards = re.findall(r'<section class="travel-results"[^>]*>(.*?)</section>', final, re.S)
        card_links = {html.unescape(url) for card in cards for url in LINK.findall(card)}
        narrative_links = {html.unescape(url) for url in LINK.findall(body[1])}
        if card_links != sources or not narrative_links <= sources:
            return "source_mismatch"
    if any(report.status == "timeout" for report in reports):
        return "provider_timeout"
    if any(report.status == "rate_limited" for report in reports):
        return "provider_throttled"
    if any(report.status == "partial" for report in reports):
        return "provider_partial"
    if any(report.status not in {"found", "no_results"} for report in reports):
        return "provider_failed"
    if any(report.status == "no_results" for report in reports):
        return "empty_inventory"
    return "pass"


async def _attempt(http: httpx2.AsyncClient, base: str, case: TravelCase, today: date) -> str:
    """Keep all private HTML local to a single attempt and expose only its fixed outcome code."""
    golden = case.golden(today)
    raw: list[tuple[int, str]] = []

    def observe(status: int, final: str) -> None:
        """Retain the final provider artifacts until the grader checks display provenance."""
        raw.append((status, final))

    try:
        result = await ask(http, base, golden, history=case.history, observe=observe)
        return outcome(case, today, result, *raw[-1])
    except httpx2.TimeoutException:
        return "client_timeout"
    except httpx2.HTTPError:
        return "connection_failed"


async def run(base: str, cases: list[TravelCase], repeats: int, *, pause: float = PAUSE_SECONDS) -> int:
    """Run every scheduled attempt without replacing failures with later passes or persisting questions or offers."""
    today = datetime.now(ZoneInfo("America/Chicago")).date()
    counts: Counter[str] = Counter()
    async with httpx2.AsyncClient(timeout=ANSWER_SECONDS) as http:
        for repeat in range(1, repeats + 1):
            for case in cases:
                if counts:
                    await asyncio.sleep(pause)
                code = await _attempt(http, base, case, today)
                counts[code] += 1
                print(f"{case.id} attempt={repeat} {code}", flush=True)
    print(" ".join(f"{code}={count}" for code, count in sorted(counts.items())))
    return int(any(code != "pass" for code in counts))


def main() -> int:
    """Parse an explicit target URL; by default repeat all ten synthetic cases three times."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="Address of a running Nimbus with flights and hotels enabled")
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=3)
    cases = read_cases()
    parser.add_argument("--case", choices=[case.id for case in cases], action="append")
    args = parser.parse_args()
    selected = [case for case in cases if not args.case or case.id in args.case]
    return asyncio.run(run(args.base.rstrip("/"), selected, args.repeats))


if __name__ == "__main__":
    raise SystemExit(main())
