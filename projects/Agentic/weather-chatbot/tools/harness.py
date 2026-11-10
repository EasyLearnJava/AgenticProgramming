"""Run the Nimbus replay or live harness, or verify evidence for a human release decision."""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

import httpx2
from pydantic import ValidationError

# Support both the file command from the demo and the project's usual python -m tools.* invocation.
if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nimbus.constants import PROJECT_ROOT
from nimbus.harness_scorecard import Attempt, Build, Scorecard, load_report, release_errors, report_path
from tools.harness_live import live_cases, live_catalog
from tools.harness_replay import replay_cases
from tools.park_replay import replay_park_cases

LIVE_SUITES = ("golden", "travel")


def source_build() -> Build:
    """Git stamps local and CI evidence. Unknown provenance can still run but cannot qualify for release."""
    git = shutil.which("git")
    if not git:
        return Build()
    try:

        def read_git(*args: str) -> str:
            return subprocess.check_output(  # noqa: S603 - resolved git executable, fixed arguments
                [git, *args], cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL, text=True, timeout=10
            ).strip()

        prefix = read_git("rev-parse", "--show-prefix")
        reports = [f":(top,exclude){prefix}evals/harness/last-{mode}.json" for mode in ("replay", "live")]
        return Build(
            commit=read_git("rev-parse", "HEAD"),
            dirty=bool(read_git("status", "--porcelain", "--", ":/", *reports)),
            environment="ci" if os.environ.get("GITHUB_ACTIONS") == "true" else "local",
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return Build()


def origin(value: str) -> str:
    url = urlsplit(value)
    if not url.hostname or url.username is not None or url.password is not None or url.path not in {"", "/"}:
        raise ValueError("use a bare Nimbus origin")
    if (
        url.query
        or url.fragment
        or (url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}))
    ):
        raise ValueError("use HTTPS or a local loopback server")
    return value.rstrip("/")


async def target_build(base: str) -> Build:
    async with (
        asyncio.timeout(10),
        httpx2.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as http,
        http.stream("GET", f"{base}/api/build") as response,
    ):
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=1024):
            body.extend(chunk)
            if len(body) > 2048:
                raise ValueError("oversized build identity")
        return Build.model_validate_json(body)


def save(card: Scorecard, path: Path) -> None:
    """Atomic replacement keeps the public page usable during interrupted or concurrent runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    evidence = card.model_dump(mode="json")
    evidence["summary"] = card.summary()
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(json.dumps(evidence, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def report(card: Scorecard) -> str:
    state = "PASS" if card.passed else "FAIL"
    lines = [
        f"## Nimbus {card.mode} · {state}",
        "",
        "| Suite | First try | All three | p50 (ms) | p95 (ms) |",
        "|---|---:|---:|---:|---:|",
    ]
    for suite in card.suites():
        three = "—" if suite.all_three is None else f"{suite.all_three}/{suite.cases}"
        lines.append(
            f"| {suite.suite} | {suite.first_pass}/{suite.cases} | {three} | {suite.p50_ms} | {suite.p95_ms} |"
        )
    lines.extend(f"- {r.suite}/{r.case_id}, try {r.attempt}: {r.outcome}" for r in card.attempts if r.outcome != "pass")
    return "\n".join(lines)


async def replay_attempts() -> list[Attempt]:
    # Replay uses synchronous test doubles and may run their own event loops.
    rows = await asyncio.to_thread(replay_cases)
    return [Attempt.model_validate(row) for row in [*rows, *await replay_park_cases()]]


async def run(args: argparse.Namespace) -> int:
    # ① Stamp the source and, for a live run, the deployment receiving the questions.
    start = datetime.now(UTC)
    source = source_build()
    target = None
    if args.mode == "replay":
        if args.base_url or args.smoke or args.suite or args.repeats is not None or args.pause is not None:
            raise ValueError("live options on replay")
        trials = 1
        attempts = await replay_attempts()
    else:
        if not args.base_url:
            raise ValueError("live mode requires --base-url")
        base = origin(args.base_url)
        target = await target_build(base)
        if args.require_preview and (target.environment != "preview" or not target.commit or not target.deployment):
            raise ValueError("expected an identifiable preview")
        trials = args.repeats if args.repeats is not None else 3
        pause = args.pause if args.pause is not None else 40
        if not 1 <= trials <= 5 or not 0 <= pause <= 600:
            raise ValueError("invalid repeats or pause")
        selected = tuple(dict.fromkeys(args.suite or LIVE_SUITES))
        rows = await live_cases(
            base, suites=selected, repeats=trials, pause=pause, smoke=args.smoke, expected_deployment=target.deployment
        )
        attempts = [Attempt.model_validate(row) for row in rows]
        if await target_build(base) != target:
            raise ValueError("target changed during evaluation")
    if source_build() != source:
        raise ValueError("source revision changed during evaluation")
    # ② Validate trial coverage before atomically publishing the public evidence.
    card = Scorecard(
        mode=args.mode,
        profile="smoke" if args.smoke else "full",
        started_at=start,
        finished_at=datetime.now(UTC),
        source=source,
        target=target,
        repeats=trials,
        attempts=attempts,
    )
    if card.mode == "live" and card.catalog() != live_catalog(selected, smoke=args.smoke):
        raise ValueError("incomplete live coverage")
    path = args.output or report_path(card.mode)
    save(card, path)
    summary = report(card)
    print(summary)
    print(f"Scorecard: {path}")
    if args.summary_file:
        with args.summary_file.open("a", encoding="utf-8") as stream:
            print(summary, file=stream)
    return int(not card.passed)


async def gate(args: argparse.Namespace) -> int:
    # ③ Reconstruct coverage from this checkout before a releaser reviews the exact preview.
    if not re.fullmatch(r"[a-f0-9]{40}", args.commit) or not re.fullmatch(r"dpl_[a-zA-Z0-9_-]{1,96}", args.deployment):
        raise ValueError("invalid release identifiers")
    current = source_build()
    if current.commit != args.commit or current.dirty is not False:
        print("Gate closed: check out the clean revision being evaluated.")
        return 1
    rows = await replay_attempts()
    catalog: dict[str, set[str]] = {}
    for row in rows:
        catalog.setdefault(row.suite, set()).add(row.case_id)
    errors = release_errors(
        load_report(args.replay),
        load_report(args.live),
        args.commit,
        args.deployment,
        replay_catalog=catalog,
        live_catalog=live_catalog(LIVE_SUITES),
        now=datetime.now(UTC),
    )
    if any(row.outcome != "pass" for row in rows):
        errors.append("current replay failed")
    print("Gate closed: " + ", ".join(errors) if errors else "Evidence passed. Ready for human release review.")
    return int(bool(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="command", required=True)
    runner = actions.add_parser("run", help="Run synthetic scenarios and save evidence.")
    runner.add_argument("--mode", choices=("replay", "live"), default="replay")
    runner.add_argument("--base-url", help="An explicit Nimbus origin for live evaluation.")
    runner.add_argument(
        "--require-preview", action="store_true", help="Refuse to send traffic to a non-preview target."
    )
    runner.add_argument("--suite", choices=LIVE_SUITES, action="append")
    runner.add_argument("--smoke", action="store_true")
    runner.add_argument("--repeats", type=int)
    runner.add_argument("--pause", type=float)
    runner.add_argument("--output", type=Path)
    runner.add_argument("--summary-file", type=Path)
    release = actions.add_parser("gate", help="Check the evidence for one exact preview.")
    release.add_argument("--replay", type=Path, required=True)
    release.add_argument("--live", type=Path, required=True)
    release.add_argument("--commit", required=True)
    release.add_argument("--deployment", required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return asyncio.run(run(args) if args.command == "run" else gate(args))
    except (OSError, ValueError, httpx2.HTTPError, ValidationError) as exc:
        # Upstream error messages and validation inputs may contain request bodies or private preview URLs.
        print(
            f"Harness could not complete ({type(exc).__name__}). Check the command, fixtures and target identity.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
