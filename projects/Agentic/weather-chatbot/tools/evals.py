"""
tools/evals.py: the golden questions (step 13), asked of a running Nimbus, each answer graded by rules: the tools it
called, and what its words say or never say. A question is asked as the page asks it, with the browser's language and
time zone, on a lane; its tools are read from the chips, its words from the finished answer. With --langsmith, and
LangSmith's key in your settings, the questions are kept in LangSmith as the dataset nimbus-golden, and the run as an
experiment named for the commit that answered, each question's grade beside it. With --save, the run is kept in
evals/last-run.json, which the Evaluations page shows (step 14). From the project's folder, in bash:

    uv run python -m tools.evals https://weather-chatbot-hazel.vercel.app --save
    uv run python -m tools.evals http://127.0.0.1:8000 --langsmith
"""

import asyncio
import html
import json
import re
import sys
import urllib.parse
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx2

from nimbus.config import Settings
from nimbus.constants import LAST_RUN_FILE
from nimbus.goldens import Golden, GoldenResult, LastRun, read_goldens

DATASET: Final = "nimbus-golden"
# Gemini's free tier takes 15 requests a minute: an answer is up to three calls, so the questions wait between them.
PAUSE_SECONDS: Final = 8
ANSWER_SECONDS: Final = 90
USAGE = "usage: uv run python -m tools.evals <the app's address> [--langsmith] [--save]"
FLAGS: Final = frozenset({"--langsmith", "--save"})
ANSWER_FRAGMENT: Final = re.compile(r'<div class="answer"[^>]*>(.*?)</div>', re.S)


@dataclass(frozen=True)
class Answer:
    """An answer as the page shows it: the tools its chips name, in order, its words, and whether it failed."""

    tools: list[str]
    text: str
    failed: bool
    request_id: str
    citations: list[str] = field(default_factory=list)


def to_text(fragment: str) -> str:
    """
    An HTML fragment's words: an inline tag (bold, a link) gone where it was, any other a space, as a page shows them;
    the spaces made one.
    """
    inline = re.sub(r"</?(?:strong|em|a|code|span)\b[^>]*>", "", fragment)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inline)).split())


def read_answer(events: Sequence[str], request_id: str = "") -> Answer:
    """An answer from its stream's events: the last holds the finished turn, its chips and its words."""
    last = events[-1] if events else ""
    tools = re.findall(r'<code class="tool-chip-name">(.*?)</code>', last)
    failed = bool(re.search(r'class="[^"]*\bmessage-error\b[^"]*"', last)) or not events
    fragment = ANSWER_FRAGMENT.search(last)
    words = fragment[1] if fragment else ""
    if failed and (note := re.search(r'<p class="message-note">(.*?)</p>', last, re.S)):
        words += " " + note[1]
    citations = list(dict.fromkeys(html.unescape(href) for href in re.findall(r'<a\b[^>]*href=["\'](.*?)["\']', words)))
    return Answer(tools, to_text(words), failed, request_id, citations)


def grade(golden: Golden, answer: Answer) -> list[str]:
    """What the answer got wrong, a sentence each; none when it's right."""
    misses = ["the answer failed"] if answer.failed else []
    called = iter(answer.tools)
    if not all(tool in called for tool in golden.expect.tools):
        misses.append(f"called {answer.tools}, not {golden.expect.tools} in that order")
    misses += [f"called {tool}" for tool in golden.expect.no_tools if tool in answer.tools]
    misses += [f"doesn't say /{words}/" for words in golden.expect.says if not re.search(words, answer.text, re.I)]
    misses += [f"says /{words}/" for words in golden.expect.never_says if re.search(words, answer.text, re.I)]
    misses += [f"missing citation {url}" for url in golden.expect.cites if url not in answer.citations]
    if golden.expect.only_cites:
        misses += [f"unexpected citation {url}" for url in answer.citations if url not in golden.expect.only_cites]
    return misses


async def ask(
    http: httpx2.AsyncClient,
    base: str,
    golden: Golden,
    *,
    history: Sequence[dict[str, str]] = (),
    observe: Callable[[int, str], None] | None = None,
    observe_event: Callable[[str], None] | None = None,
) -> Answer:
    """Asks the golden question as the page would, and reads the answer from its stream."""
    form = {"question": golden.question, "locale": golden.locale, "time_zone": golden.time_zone, "lane": golden.lane}
    if history:
        form["history"] = json.dumps(history)
    headers = {"content-type": "application/x-www-form-urlencoded"}
    async with http.stream("POST", f"{base}/api/chat", content=urllib.parse.urlencode(form), headers=headers) as sent:
        request_id = sent.headers.get("x-request-id", "")
        if sent.status_code != 200:
            # Rejections are plain HTML, before a stream opens. Only the fixed refusal text is needed by a grader.
            refusal = ""
            async for chunk in sent.aiter_text():
                refusal += chunk[: 8192 - len(refusal)]
                if len(refusal) >= 8192:
                    break
            if observe is not None:
                observe(sent.status_code, refusal)
            return read_answer([], request_id)
        final = ""
        lines: list[str] = []
        async for line in sent.aiter_lines():
            if line.startswith("data:"):
                lines.append(line[5:].removeprefix(" "))
            elif line == "" and lines:
                final = "\n".join(lines)
                lines.clear()
                if observe_event is not None:
                    observe_event(final)
        if observe is not None:
            observe(sent.status_code, final)
    return read_answer([final] if final else [], request_id)


@dataclass(frozen=True)
class Graded:
    """A golden question, its answer, and what the answer got wrong."""

    golden: Golden
    answer: Answer
    misses: list[str]


async def run_goldens(
    goldens: Sequence[Golden],
    asking: Callable[[Golden], Awaitable[Answer]],
    pause: Callable[[], Awaitable[None]],
) -> list[Graded]:
    """Each golden question, one at a time, a pause between two; each answer graded."""
    graded = []
    for index, golden in enumerate(goldens):
        if index:
            await pause()
        answer = await asking(golden)
        graded.append(Graded(golden, answer, grade(golden, answer)))
    return graded


def to_report(graded: Sequence[Graded]) -> list[str]:
    """A line for each question, its misses under it, then how many passed."""
    lines = []
    for item in graded:
        lines.append(
            f"{'pass' if not item.misses else 'FAIL'}  {item.golden.id}: {', '.join(item.answer.tools) or '-'}"
        )
        lines += [f"      {miss}" for miss in item.misses]
    passed = sum(not item.misses for item in graded)
    lines.append(f"{passed} of {len(graded)} passed")
    return lines


def to_last_run(graded: Sequence[Graded], commit: str | None, ran_at: datetime) -> LastRun:
    """The run, as evals/last-run.json keeps it: the build that answered, when, and each result."""
    results = [
        GoldenResult(id=item.golden.id, passed=not item.misses, tools=item.answer.tools, misses=item.misses)
        for item in graded
    ]
    return LastRun(commit=commit, ran_at=ran_at, results=results)


def save_last_run(last_run: LastRun, path: Path = LAST_RUN_FILE) -> None:
    """Keeps the run in its file, as indented JSON with LF line endings, for git and the Evaluations page."""
    path.write_text(last_run.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def to_examples(goldens: Sequence[Golden]) -> list[dict[str, Any]]:
    """The golden questions as LangSmith's examples: what's asked, with its id, and what's expected."""
    return [
        {
            "inputs": golden.model_dump(include={"id", "question", "locale", "time_zone", "lane"}),
            "outputs": golden.expect.model_dump(),
            "metadata": {"id": golden.id},
        }
        for golden in goldens
    ]


def keep_in_langsmith(
    client: Any, graded: Sequence[Graded], commit: str, evaluate: Callable[..., Any] | None = None
) -> None:
    """
    The golden questions as LangSmith's dataset, made once, a golden it lacks added on each run; and this run as an
    experiment on it, named for the commit: each answer, its tools and words, graded already, found by its golden's id,
    so nothing is asked twice. An example whose golden this run didn't ask, one since removed, is graded as not asked.
    An edited golden keeps its first example's expectations in LangSmith; its grade is this run's. LangSmith's own
    evaluate, unless one is given (the tests give theirs: importing LangSmith's warns on Python 3.13).
    """
    if evaluate is None:
        from langsmith import evaluate as evaluate_in_langsmith

        evaluate = evaluate_in_langsmith

    if not client.has_dataset(dataset_name=DATASET):
        client.create_dataset(DATASET, description="Nimbus's golden questions, and what each answer must do.")
    kept = {example.inputs.get("id") for example in client.list_examples(dataset_name=DATASET)}
    missing = [item.golden for item in graded if item.golden.id not in kept]
    if missing:
        client.create_examples(dataset_name=DATASET, examples=to_examples(missing))
    by_id = {item.golden.id: item for item in graded}

    def answered(inputs: dict[str, Any]) -> dict[str, Any]:
        """The answer this run already has for the golden; one it didn't ask, a miss that says so."""
        item = by_id.get(inputs.get("id", ""))
        if item is None:
            return {"tools": [], "text": "", "misses": ["not asked in this run"]}
        return {"tools": item.answer.tools, "text": item.answer.text, "misses": item.misses}

    def passed(outputs: dict[str, Any]) -> dict[str, Any]:
        """The grade: 1 when the answer did all it must, else 0, with what it missed."""
        return {"key": "passed", "score": int(not outputs["misses"]), "comment": "; ".join(outputs["misses"])}

    evaluate(answered, data=DATASET, evaluators=[passed], experiment_prefix=f"nimbus-{commit}", client=client)


async def run(
    base: str,
    settings: Settings,
    *,
    langsmith: bool,
    make_client: Callable[[], httpx2.AsyncClient],
    save: Callable[[LastRun], None] | None = None,
) -> int:
    """
    Asks every golden question, prints how each went, keeps the run in LangSmith if asked, and in its file if a save
    is given: 0 when every answer passed, 1 when one didn't, 2 when LangSmith is asked for without its key, before any
    question is asked.
    """
    if langsmith and settings.langsmith_api_key is None:
        print("--langsmith needs LANGSMITH_API_KEY in your environment or .env.local")
        return 2
    goldens = read_goldens()
    async with make_client() as http:
        health = (await http.get(f"{base}/api/health")).json()
        graded = await run_goldens(
            goldens, lambda golden: ask(http, base, golden), lambda: asyncio.sleep(PAUSE_SECONDS)
        )
    print(f"{base}, build {health.get('commit')}:")
    print("\n".join(to_report(graded)))
    if save is not None:
        save(to_last_run(graded, health.get("commit"), datetime.now(UTC)))
        print("kept in evals/last-run.json")
    if langsmith and settings.langsmith_api_key is not None:
        from langsmith import Client

        client = Client(api_key=settings.langsmith_api_key.get_secret_value())
        keep_in_langsmith(client, graded, str(health.get("commit") or "local"))
        print(f"kept in LangSmith: the dataset {DATASET}, and this run as an experiment on it")
    return 0 if all(not item.misses for item in graded) else 1


def main() -> int:
    """The app's address, from the command line; then --langsmith and --save, if given."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    flags = {argument for argument in sys.argv[1:] if argument in FLAGS}
    arguments = [argument for argument in sys.argv[1:] if argument not in FLAGS]
    if len(arguments) != 1:
        print(USAGE)
        return 2
    client = lambda: httpx2.AsyncClient(timeout=ANSWER_SECONDS)  # noqa: E731 - one line, read once
    save = save_last_run if "--save" in flags else None
    base = arguments[0].rstrip("/")
    return asyncio.run(run(base, Settings(), langsmith="--langsmith" in flags, make_client=client, save=save))


if __name__ == "__main__":
    sys.exit(main())
