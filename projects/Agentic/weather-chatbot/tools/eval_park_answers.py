"""
tools/eval_park_answers.py: the park answers, graded end to end (issue 183), where tools/eval_parks.py grades only the
retrieval. Each reviewed question in evals/park_answers.json is asked of a running Nimbus as the page asks it. The
passages its search_park_guidance calls returned, and any NPS notices, are read from the finished turn's tool chips.
Then four checks grade it: the search itself (called, and not failed), the retrieval hit (each evidence phrase is in a
retrieved passage), the golden rules (tools, wording, citations, and no link to a source no tool returned other than
a weather authority), and an LLM judge's verdicts (tools/answer_judge.py): correct, grounded and, for a question the
guides don't cover, abstained. Which check failed first says where to look: the search, or the prompt and model. A
hard case, every safety question, that doesn't pass is listed first and sets its own exit code. With --save, the
grades (case IDs and verdicts, never questions or answers) are kept in evals/park-answers-last-run.json. From the
project's folder, with Gemini's key in your environment or .env.local for the judge:

    uv run python -m tools.eval_park_answers https://weather-chatbot-hazel.vercel.app --review --save

Exit codes: 0 every case passed; 1 a hard case didn't; 3 only other cases didn't; 2 nothing was asked (no key, or an
unknown --only case).
"""

import argparse
import asyncio
import html
import json
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal, Self

import httpx2
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from nimbus.answer import is_weather_authority
from nimbus.config import Settings
from nimbus.goldens import Expect, Golden
from tools import evals
from tools.answer_judge import CaseKind, Evidence, Verdict, judge_answer, make_judge_model

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "evals" / "park_answers.json"
LAST_RUN_PATH = PROJECT_ROOT / "evals" / "park-answers-last-run.json"
# An answer is usually three Gemini calls and the judge one more, on the free tier's 15 a minute.
PAUSE_SECONDS: Final = 12
JUDGE_RETRY_SECONDS: Final = 20
CHIP_NAME: Final = '<code class="tool-chip-name">'
CHIP: Final = re.compile(
    r'<li class="tool-chip tool-chip-(\w+)"[^>]*>.*?<code class="tool-chip-name">(.*?)</code>', re.S
)
SEARCH_TOOL: Final = "search_park_guidance"
# A search that answers these searched nothing: no index, or a destination it doesn't cover.
UNSEARCHED: Final = frozenset({"unavailable", "unsupported"})
type SearchStatus = Literal["done", "failed", "none"]
type Pattern = Literal[
    "pass",
    "request_failed",
    "judge_failed",
    "search_not_called",
    "search_failed",
    "retrieval_miss",
    "answer_wrong",
    "not_grounded",
    "answered_unanswerable",
    "rules",
]
# What each failure says to look at, from which check failed first.
LOOK_AT: Final[dict[str, str]] = {
    "request_failed": "the request: Nimbus gave no answer, or the connection failed",
    "judge_failed": "the judge: it gave no verdict, so the case is ungraded",
    "search_not_called": "the tool choice: Gemini never searched the park guidance",
    "search_failed": "the search tool: it failed or ran out of time, so nothing was retrieved",
    "retrieval_miss": "the search: chunking, search settings or the query Gemini wrote",
    "answer_wrong": "the prompt or the model: the right passage came back, the answer misread it",
    "not_grounded": "the prompt: the answer used outside knowledge or invented a specific",
    "answered_unanswerable": "the prompt: it should say the guidance doesn't cover this",
    "rules": "the tools called, the wording or the citations",
}


class AnswerCase(BaseModel):
    """One reviewed question, its reference answer, the evidence retrieval must find, and the golden rules it meets."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    kind: CaseKind
    question: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    hard: bool = False
    locale: str = "en-US"
    time_zone: str = "America/Chicago"
    expect: Expect = Field(default_factory=Expect)

    @field_validator("expect", mode="before")
    @classmethod
    def known_rules(cls, value: object) -> object:
        """A misspelled rule ("cite" for "cites") is refused, never silently dropped as Expect itself would."""
        if isinstance(value, dict) and (unknown := set(value) - set(Expect.model_fields)):
            raise ValueError(f"unknown expect rules: {sorted(unknown)}")
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        """A safety question is always a hard fail; a question the guides don't cover has no evidence to find."""
        if self.kind == "safety" and not self.hard:
            raise ValueError("a safety case must be hard")
        if self.kind == "unanswerable" and self.evidence:
            raise ValueError("an unanswerable case has no evidence")
        if self.kind != "unanswerable" and not self.evidence:
            raise ValueError("an answerable case needs evidence")
        return self

    def golden(self) -> Golden:
        """The case as a golden question, so it's asked and its rules graded as tools/evals.py does."""
        return Golden(
            id=self.id, question=self.question, locale=self.locale, time_zone=self.time_zone, expect=self.expect
        )


CASES = TypeAdapter(list[AnswerCase])


def read_cases(path: Path = CASES_PATH) -> list[AnswerCase]:
    """The reviewed cases, checked as they're read."""
    return CASES.validate_json(path.read_bytes())


def _labelled_json(segment: str, label: str) -> Any:
    """A chip's Input or Output block, as JSON; None when it's missing or isn't JSON."""
    found = re.search(rf'<p class="tool-chip-label">{label}</p>\s*<pre>(.*?)</pre>', segment, re.S)
    if found is None:
        return None
    try:
        return json.loads(html.unescape(found[1]))
    except ValueError:
        return None


def read_evidence(final: str) -> list[Evidence]:
    """
    What the finished turn's tools returned that an answer may draw on: each search_park_guidance passage and each
    get_park_alerts notice, from the chips' Output blocks, once each.
    """
    found: dict[tuple[str, str, str], Evidence] = {}
    for segment in final.split(CHIP_NAME)[1:]:
        name = html.unescape(segment.split("</code>", 1)[0])
        output = _labelled_json(segment, "Output")
        if not isinstance(output, dict):
            continue
        items: list[Evidence] = []
        if name == "search_park_guidance":
            items = [
                Evidence(
                    source="guidance",
                    title=str(passage.get("title", "")),
                    section=str(passage.get("section", "")),
                    text=str(passage.get("text", "")),
                    url=str(passage.get("source_url", "")),
                )
                for passage in output.get("passages", [])
                if isinstance(passage, dict)
            ]
        elif name == "get_park_alerts":
            items = [
                Evidence(
                    source="notice",
                    title=str(notice.get("title", "")),
                    text=str(notice.get("description", "")),
                    url=str(notice.get("url", "")),
                )
                for notice in output.get("notices", [])
                if isinstance(notice, dict)
            ]
            # The park's official page, which a notice answer may cite, with no text of its own.
            if isinstance(output.get("source_url"), str):
                items.append(Evidence(source="notice", title="Official park page", text="", url=output["source_url"]))
        for item in items:
            found.setdefault((item.url, item.section, item.text), item)
    return list(found.values())


def read_search_status(final: str) -> SearchStatus:
    """
    Whether the finished turn's park search ran: "done" if any call finished and searched, "failed" if every call
    failed or answered that the index was unavailable or the destination unsupported, or "none" if none was made.
    """
    statuses = [status for status, name in CHIP.findall(final) if html.unescape(name) == SEARCH_TOOL]
    outputs = [
        _labelled_json(segment, "Output")
        for segment in final.split(CHIP_NAME)[1:]
        if html.unescape(segment.split("</code>", 1)[0]) == SEARCH_TOOL
    ]
    searched = any(isinstance(output, dict) and output.get("status") not in UNSEARCHED for output in outputs)
    if "done" in statuses and searched:
        return "done"
    return "failed" if statuses else "none"


def retrieval_hit(case: AnswerCase, evidence: Sequence[Evidence]) -> bool | None:
    """Whether every evidence phrase is in a retrieved guidance passage; None for a question with nothing to find."""
    if case.kind == "unanswerable":
        return None
    texts = [" ".join(item.text.split()).casefold() for item in evidence if item.source == "guidance"]
    return all(any(" ".join(phrase.split()).casefold() in text for text in texts) for phrase in case.evidence)


def foreign_citations(answer: evals.Answer, evidence: Sequence[Evidence]) -> list[str]:
    """
    The answer's links to sources no tool returned this turn, a sentence each. A weather authority's page, such as the
    National Weather Service, is one the prompt asks for (rule 9) and the page keeps (nimbus/answer.py): no miss.
    """
    returned = {item.url for item in evidence if item.url}
    cited = [url for url in answer.citations if not is_weather_authority(url)]
    return [f"cites {url}, which no tool returned" for url in cited if url not in returned]


def decide(
    case: AnswerCase,
    answer: evals.Answer,
    misses: Sequence[str],
    hit: bool | None,
    verdict: Verdict | None,
    search: SearchStatus = "done",
) -> Pattern:
    """The first check that failed, in the order that tells you where to look; "pass" when none did."""
    if answer.failed or not answer.text.strip():
        return "request_failed"
    if case.kind == "unanswerable":
        if verdict is None:
            return "judge_failed"
        # Declining passes; so does an answer the reference allows, such as a time a returned NPS notice states.
        if not (verdict.abstained or verdict.correct):
            return "answered_unanswerable"
        if not verdict.grounded:
            return "not_grounded"
        return "rules" if misses else "pass"
    if search != "done":
        return "search_not_called" if search == "none" else "search_failed"
    if hit is False:
        return "retrieval_miss"
    if verdict is None:
        return "judge_failed"
    if not verdict.correct:
        return "answer_wrong"
    if not verdict.grounded:
        return "not_grounded"
    return "rules" if misses else "pass"


@dataclass(frozen=True)
class Asked:
    """A case's answer as the page shows it, and the evidence its tools returned."""

    answer: evals.Answer
    evidence: list[Evidence] = field(default_factory=list)
    search: SearchStatus = "none"


@dataclass(frozen=True)
class Graded:
    """A case, what came back, each check's result, and the pattern they make."""

    case: AnswerCase
    asked: Asked
    misses: list[str]
    hit: bool | None
    verdict: Verdict | None
    pattern: Pattern


type Asking = Callable[[AnswerCase], Awaitable[Asked]]
type Judging = Callable[[AnswerCase, Sequence[Evidence], str], Awaitable[Verdict | None]]


async def run_cases(
    cases: Sequence[AnswerCase], asking: Asking, judging: Judging, pause: Callable[[], Awaitable[None]]
) -> list[Graded]:
    """Each case, one at a time, a pause between two; each answer checked by rules, retrieval and the judge."""
    graded = []
    for index, case in enumerate(cases):
        if index:
            await pause()
        asked = await asking(case)
        misses = [*evals.grade(case.golden(), asked.answer), *foreign_citations(asked.answer, asked.evidence)]
        hit = retrieval_hit(case, asked.evidence)
        answered = not asked.answer.failed and asked.answer.text.strip()
        verdict = await judging(case, asked.evidence, asked.answer.text) if answered else None
        pattern = decide(case, asked.answer, misses, hit, verdict, asked.search)
        graded.append(Graded(case, asked, misses, hit, verdict, pattern))
    return graded


def hard_failures(graded: Sequence[Graded]) -> list[Graded]:
    """The hard cases that didn't pass, wrong or ungraded: any one of them fails the run, whatever the score."""
    return [item for item in graded if item.case.hard and item.pattern != "pass"]


def to_exit_code(graded: Sequence[Graded]) -> int:
    """0 when every case passed; 1 when a hard case didn't; 3 when only other cases didn't."""
    if hard_failures(graded):
        return 1
    return 0 if all(item.pattern == "pass" for item in graded) else 3


def to_report(graded: Sequence[Graded], *, review: bool = False) -> list[str]:
    """A line per case, hard failures first; with review, each answer and verdict in full, to check the judge by."""
    hard = hard_failures(graded)
    passed = sum(item.pattern == "pass" for item in graded)
    lines = [f"HARD FAIL {item.case.id} ({item.case.kind}): {item.pattern}" for item in hard]
    lines.append(f"{passed} of {len(graded)} passed; {len(hard)} hard failures")
    for item in graded:
        verdict = item.verdict
        grades = (
            "judge: none"
            if verdict is None
            else f"correct {verdict.correct}, grounded {verdict.grounded}, abstained {verdict.abstained}"
        )
        mark = "pass" if item.pattern == "pass" else f"FAIL {item.pattern}"
        lines.append(f"{mark}: {item.case.id} ({item.case.kind}) · retrieval hit {item.hit} · {grades}")
        if item.pattern != "pass":
            lines.append(f"    look at {LOOK_AT[item.pattern]}")
            lines.extend(f"    {miss}" for miss in item.misses)
        if verdict is not None and (review or item.pattern != "pass"):
            lines.append(f"    judge: {verdict.reason}")
            lines.extend(f"    unsupported: {claim}" for claim in verdict.unsupported_claims)
        if review:
            lines.append(f"    question: {item.case.question}")
            lines.append(f"    reference: {item.case.reference}")
            lines.append(f"    answer: {item.asked.answer.text}")
            lines.extend(f"    evidence: {e.title} · {e.section}".rstrip(" ·") for e in item.asked.evidence)
    return lines


class ParkAnswerResult(BaseModel):
    """One case's grades as kept: its ID, kind and verdicts, never its question or answer."""

    id: str
    kind: CaseKind
    hard: bool
    passed: bool
    pattern: Pattern
    retrieval_hit: bool | None
    correct: bool | None
    grounded: bool | None
    abstained: bool | None


class ParkAnswerRun(BaseModel):
    """A run as kept: the build that answered, the judge, when, and each case's grades."""

    commit: str | None
    judge_model: str
    ran_at: datetime
    results: list[ParkAnswerResult]


def to_last_run(graded: Sequence[Graded], commit: str | None, judge_model: str, ran_at: datetime) -> ParkAnswerRun:
    """The run's grades, for evals/park-answers-last-run.json."""
    return ParkAnswerRun(
        commit=commit,
        judge_model=judge_model,
        ran_at=ran_at,
        results=[
            ParkAnswerResult(
                id=item.case.id,
                kind=item.case.kind,
                hard=item.case.hard,
                passed=item.pattern == "pass",
                pattern=item.pattern,
                retrieval_hit=item.hit,
                correct=None if item.verdict is None else item.verdict.correct,
                grounded=None if item.verdict is None else item.verdict.grounded,
                abstained=None if item.verdict is None else item.verdict.abstained,
            )
            for item in graded
        ],
    )


async def ask_case(http: httpx2.AsyncClient, base: str, case: AnswerCase) -> Asked:
    """
    Asks the case as the page would; its words from the answer, its evidence and search from the finished turn's
    chips. A connection that fails or times out fails this case only, never the run and the grades before it.
    """
    finals: list[str] = []
    try:
        answer = await evals.ask(http, base, case.golden(), observe=lambda _status, final: finals.append(final))
    except httpx2.HTTPError as error:
        print(f"request failed on {case.id}: {type(error).__name__}", file=sys.stderr)
        return Asked(evals.Answer([], "", True, ""))
    final = finals[-1] if finals else ""
    return Asked(answer, read_evidence(final), read_search_status(final))


async def read_commit(http: httpx2.AsyncClient, base: str) -> str | None:
    """The answering build's commit, from its health check; None when that can't be read."""
    try:
        health = (await http.get(f"{base}/api/health")).json()
    except (httpx2.HTTPError, ValueError):
        return None
    commit = health.get("commit") if isinstance(health, dict) else None
    return commit if isinstance(commit, str) else None


def judge_with(model: Any, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> Judging:
    """The judge, tried twice, 20 s apart: a busy model is a pause, and a second failure leaves the case ungraded."""

    async def judging(case: AnswerCase, evidence: Sequence[Evidence], answer: str) -> Verdict | None:
        """One case's verdict, or None."""
        for attempt in range(2):
            try:
                return await judge_answer(model, case.kind, case.question, case.reference, evidence, answer)
            # Any judge failure leaves this case ungraded, never the run: its class is printed, not its text.
            except Exception as error:
                print(f"judge failed on {case.id}: {type(error).__name__}", file=sys.stderr)
                if attempt == 0:
                    await sleep(JUDGE_RETRY_SECONDS)
        return None

    return judging


def save_last_run(run: ParkAnswerRun, path: Path = LAST_RUN_PATH) -> None:
    """Keeps the run's grades beside the cases."""
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


async def run(
    base: str,
    settings: Settings,
    *,
    judge_model: str,
    review: bool,
    only: Sequence[str],
    make_client: Callable[[], httpx2.AsyncClient],
    save: Callable[[ParkAnswerRun], None] | None = None,
) -> int:
    """
    Asks every case (or only those named), prints how each went, and keeps the grades if asked: 0 when every case
    passed, 1 when a hard case didn't, 3 when only other cases didn't, 2 when the judge has no key or a named case
    doesn't exist, before any question.
    """
    model = make_judge_model(settings, judge_model)
    if model is None:
        print("The judge needs GOOGLE_API_KEY in your environment or .env.local.")
        return 2
    cases = read_cases()
    if only:
        unknown = sorted(set(only) - {case.id for case in cases})
        if unknown:
            print(f"No such case: {', '.join(unknown)}")
            return 2
        cases = [case for case in cases if case.id in set(only)]
    async with make_client() as http:
        commit = await read_commit(http, base)
        graded = await run_cases(
            cases,
            lambda case: ask_case(http, base, case),
            judge_with(model),
            lambda: asyncio.sleep(PAUSE_SECONDS),
        )
    print(f"{base}, build {commit}, judge {judge_model}:")
    print("\n".join(to_report(graded, review=review)))
    if save is not None:
        save(to_last_run(graded, commit, judge_model, datetime.now(UTC)))
        print(f"kept in {LAST_RUN_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    return to_exit_code(graded)


def main() -> int:
    """The app's address, then --review, --save, --judge-model and --only, from the command line."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    settings = Settings()
    parser = argparse.ArgumentParser(description="Grade Nimbus's park answers end to end, with an LLM judge.")
    parser.add_argument("base", help="the app's address, such as https://weather-chatbot-hazel.vercel.app")
    parser.add_argument("--review", action="store_true", help="print each answer and verdict, to check the judge")
    parser.add_argument("--save", action="store_true", help="keep the grades in evals/park-answers-last-run.json")
    parser.add_argument("--judge-model", default=settings.gemini_model, help="the Gemini model that judges")
    parser.add_argument("--only", default="", help="comma-separated case IDs to ask, instead of all")
    args = parser.parse_args()
    only = [identity for identity in args.only.split(",") if identity]
    client = lambda: httpx2.AsyncClient(timeout=evals.ANSWER_SECONDS)  # noqa: E731 - one line, read once
    return asyncio.run(
        run(
            args.base.rstrip("/"),
            settings,
            judge_model=args.judge_model,
            review=args.review,
            only=only,
            make_client=client,
            save=save_last_run if args.save else None,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
