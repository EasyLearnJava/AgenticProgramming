"""
tools/evals.py: the golden questions (step 13), asked of a running Nimbus, each answer graded by rules: the tools it
called, and what its words say or never say. A question is asked as the page asks it, with the browser's language and
time zone, on a lane; its tools are read from the chips, its words from the finished answer. With --langsmith, and
LangSmith's key in your settings, the questions are kept in LangSmith as the dataset nimbus-golden, and the run as an
experiment named for the commit that answered, each question's grade beside it. From the project's folder, in bash:

    uv run python -m tools.evals https://weather-chatbot-hazel.vercel.app
    uv run python -m tools.evals http://127.0.0.1:8000 --langsmith
"""

import asyncio
import html
import json
import re
import sys
import urllib.parse
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import httpx2
from pydantic import BaseModel, Field

from nimbus.config import Settings
from nimbus.constants import PROJECT_ROOT

GOLDEN_FILE: Final = PROJECT_ROOT / "evals" / "golden.json"
DATASET: Final = "nimbus-golden"
# Gemini's free tier takes 15 requests a minute: an answer is up to three calls, so the questions wait between them.
PAUSE_SECONDS: Final = 8
ANSWER_SECONDS: Final = 90
USAGE = "usage: uv run python -m tools.evals <the app's address> [--langsmith]"


class Expect(BaseModel):
    """What a golden answer must do: tools it calls, in order among its calls; tools it never calls; words it says."""

    tools: list[str] = Field(default_factory=list)
    no_tools: list[str] = Field(default_factory=list)
    says: list[str] = Field(default_factory=list)
    never_says: list[str] = Field(default_factory=list)


class Golden(BaseModel):
    """One golden question: its id, its words, the browser's language and time zone, the lane, and what's expected."""

    id: str
    question: str
    locale: str = "en-US"
    time_zone: str = "America/Chicago"
    lane: str = "rest-no-auth"
    expect: Expect


@dataclass(frozen=True)
class Answer:
    """An answer as the page shows it: the tools its chips name, in order, its words, and whether it failed."""

    tools: list[str]
    text: str
    failed: bool
    request_id: str


def read_goldens(path: Path = GOLDEN_FILE) -> list[Golden]:
    """The golden questions, checked as they're read."""
    return [Golden.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


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
    words = last.split('<div class="answer', 1)[-1] if '<div class="answer' in last else ""
    words = words.split(">", 1)[-1] if words else ""
    return Answer(tools, to_text(words), "message-error" in last or not events, request_id)


def grade(golden: Golden, answer: Answer) -> list[str]:
    """What the answer got wrong, a sentence each; none when it's right."""
    misses = ["the answer failed"] if answer.failed else []
    called = iter(answer.tools)
    if not all(tool in called for tool in golden.expect.tools):
        misses.append(f"called {answer.tools}, not {golden.expect.tools} in that order")
    misses += [f"called {tool}" for tool in golden.expect.no_tools if tool in answer.tools]
    misses += [f"doesn't say /{words}/" for words in golden.expect.says if not re.search(words, answer.text, re.I)]
    misses += [f"says /{words}/" for words in golden.expect.never_says if re.search(words, answer.text, re.I)]
    return misses


async def ask(http: httpx2.AsyncClient, base: str, golden: Golden) -> Answer:
    """Asks the golden question as the page would, and reads the answer from its stream."""
    form = {"question": golden.question, "locale": golden.locale, "time_zone": golden.time_zone, "lane": golden.lane}
    headers = {"content-type": "application/x-www-form-urlencoded"}
    events: list[str] = []
    async with http.stream("POST", f"{base}/api/chat", content=urllib.parse.urlencode(form), headers=headers) as sent:
        request_id = sent.headers.get("x-request-id", "")
        buffer = ""
        async for chunk in sent.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                events.append(
                    "\n".join(line[5:].removeprefix(" ") for line in raw.split("\n") if line.startswith("data:"))
                )
    return read_answer(events, request_id)


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


def to_examples(goldens: Sequence[Golden]) -> list[dict[str, Any]]:
    """The golden questions as LangSmith's examples: what's asked, and what's expected."""
    return [
        {
            "inputs": golden.model_dump(include={"question", "locale", "time_zone", "lane"}),
            "outputs": golden.expect.model_dump(),
            "metadata": {"id": golden.id},
        }
        for golden in goldens
    ]


def keep_in_langsmith(
    client: Any, graded: Sequence[Graded], commit: str, evaluate: Callable[..., Any] | None = None
) -> None:
    """
    The golden questions as LangSmith's dataset, made once; and this run as an experiment on it, named for the commit:
    each answer, its tools and words, graded already, so nothing is asked twice. LangSmith's own evaluate, unless one is
    given (the tests give theirs: importing LangSmith's warns on Python 3.13).
    """
    if evaluate is None:
        from langsmith import evaluate as evaluate_in_langsmith

        evaluate = evaluate_in_langsmith

    if not client.has_dataset(dataset_name=DATASET):
        client.create_dataset(DATASET, description="Nimbus's golden questions, and what each answer must do.")
        client.create_examples(dataset_name=DATASET, examples=to_examples([item.golden for item in graded]))
    by_question = {item.golden.question + item.golden.locale: item for item in graded}

    def answered(inputs: dict[str, Any]) -> dict[str, Any]:
        """The answer this run already has for the question."""
        item = by_question[inputs["question"] + inputs["locale"]]
        return {"tools": item.answer.tools, "text": item.answer.text, "misses": item.misses}

    def passed(outputs: dict[str, Any]) -> dict[str, Any]:
        """The grade: 1 when the answer did all it must, else 0, with what it missed."""
        return {"key": "passed", "score": int(not outputs["misses"]), "comment": "; ".join(outputs["misses"])}

    evaluate(answered, data=DATASET, evaluators=[passed], experiment_prefix=f"nimbus-{commit}", client=client)


async def run(base: str, settings: Settings, *, langsmith: bool, make_client: Callable[[], httpx2.AsyncClient]) -> int:
    """
    Asks every golden question, prints how each went, and keeps the run in LangSmith if asked: 0 when every answer
    passed, 1 when one didn't, 2 when LangSmith is asked for without its key, before any question is asked.
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
    if langsmith and settings.langsmith_api_key is not None:
        from langsmith import Client

        client = Client(api_key=settings.langsmith_api_key.get_secret_value())
        keep_in_langsmith(client, graded, str(health.get("commit") or "local"))
        print(f"kept in LangSmith: the dataset {DATASET}, and this run as an experiment on it")
    return 0 if all(not item.misses for item in graded) else 1


def main() -> int:
    """The app's address, from the command line; then --langsmith, if given."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    arguments = sys.argv[1:]
    langsmith = arguments[-1:] == ["--langsmith"]
    if langsmith:
        arguments = arguments[:-1]
    if len(arguments) != 1:
        print(USAGE)
        return 2
    client = lambda: httpx2.AsyncClient(timeout=ANSWER_SECONDS)  # noqa: E731 - one line, read once
    return asyncio.run(run(arguments[0].rstrip("/"), Settings(), langsmith=langsmith, make_client=client))


if __name__ == "__main__":
    sys.exit(main())
