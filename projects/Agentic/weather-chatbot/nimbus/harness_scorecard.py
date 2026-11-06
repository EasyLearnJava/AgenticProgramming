"""Public, versioned harness evidence. All displayed statistics are derived from individual attempts."""

import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from nimbus.constants import PROJECT_ROOT

type Mode = Literal["replay", "live"]
type Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,159}$")]
type Commit = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
type Deployment = Annotated[str, Field(pattern=r"^dpl_[a-zA-Z0-9_-]{1,96}$")]
REPORT_DIR = PROJECT_ROOT / "evals" / "harness"
MAX_REPORT_BYTES = 4_000_000


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Build(Evidence):
    commit: Commit | None = None
    deployment: Deployment | None = None
    environment: Literal["local", "development", "preview", "production", "ci", "unknown"] = "unknown"
    dirty: bool | None = None


class ProviderCall(Evidence):
    provider: Literal["kiwi", "trivago"]
    status: Identifier


class Attempt(Evidence):
    suite: Identifier
    case_id: Identifier
    attempt: int = Field(1, ge=1, le=5)
    outcome: Identifier
    duration_ms: float = Field(ge=0, allow_inf_nan=False)
    checks: list[Identifier] = Field(default_factory=list, max_length=32)
    provider_calls: list[ProviderCall] = Field(default_factory=list, max_length=30)


class SuiteStats(Evidence):
    suite: str
    cases: int
    attempts: int
    first_pass: int
    all_three: int | None
    p50_ms: float
    p95_ms: float
    failures: dict[str, int]


class Scorecard(Evidence):
    schema_version: Literal[1] = 1
    mode: Mode
    profile: Literal["full", "smoke"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    source: Build
    target: Build | None = None
    repeats: int = Field(ge=1, le=5)
    attempts: list[Attempt] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def complete_trials(self) -> Self:
        """Missing or duplicate attempts cannot quietly improve the all-three score."""
        if self.finished_at < self.started_at:
            raise ValueError("invalid run interval")
        if self.mode == "replay" and (self.repeats != 1 or self.profile != "full" or self.target is not None):
            raise ValueError("invalid replay metadata")
        if self.mode == "live" and self.target is None:
            raise ValueError("missing target identity")
        observed: dict[tuple[str, str], list[int]] = defaultdict(list)
        for row in self.attempts:
            observed[row.suite, row.case_id].append(row.attempt)
        expected = list(range(1, self.repeats + 1))
        if any(sorted(trials) != expected for trials in observed.values()):
            raise ValueError("missing or duplicate trial")
        return self

    @property
    def passed(self) -> bool:
        return all(row.outcome == "pass" for row in self.attempts)

    def catalog(self) -> dict[str, set[str]]:
        catalog: dict[str, set[str]] = defaultdict(set)
        for row in self.attempts:
            catalog[row.suite].add(row.case_id)
        return dict(catalog)

    def suites(self) -> list[SuiteStats]:
        groups: dict[str, list[Attempt]] = defaultdict(list)
        for row in self.attempts:
            groups[row.suite].append(row)
        stats = []
        for suite, rows in sorted(groups.items()):
            cases = {row.case_id for row in rows}
            failed_three = {row.case_id for row in rows if row.attempt <= 3 and row.outcome != "pass"}
            latencies = sorted(row.duration_ms for row in rows)
            stats.append(
                SuiteStats(
                    suite=suite,
                    cases=len(cases),
                    attempts=len(rows),
                    first_pass=sum(row.attempt == 1 and row.outcome == "pass" for row in rows),
                    all_three=len(cases - failed_three) if self.repeats >= 3 else None,
                    p50_ms=_percentile(latencies, 0.50),
                    p95_ms=_percentile(latencies, 0.95),
                    failures=dict(Counter(row.outcome for row in rows if row.outcome != "pass")),
                )
            )
        return stats

    def providers(self) -> dict[str, dict[str, int]]:
        """Counts are per observed tool result, including empty inventory and partial responses."""
        providers: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self.attempts:
            for call in row.provider_calls:
                providers[call.provider][call.status] += 1
        return {provider: dict(counts) for provider, counts in providers.items()}

    def summary(self) -> dict[str, object]:
        outcomes = self.providers()
        return {
            "passed": self.passed,
            "suites": [suite.model_dump() for suite in self.suites()],
            "provider_outcomes": outcomes,
            "provider_incomplete_fraction": {
                provider: round(1 - (counts.get("found", 0) + counts.get("no_results", 0)) / sum(counts.values()), 4)
                for provider, counts in outcomes.items()
            },
            "tokens": None,  # The public answer stream does not expose usage.
        }

    def weekend_grid(self) -> dict[str, list[str]]:
        """Show the observed first-try checks at each origin and local weekday, including any failures."""
        weekdays = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        groups: dict[str, dict[str, list[bool]]] = {}
        for row in self.attempts:
            if row.suite == "weekend" and row.attempt == 1:
                parts = row.case_id.rsplit("-", 2)
                if len(parts) == 3 and parts[2] in weekdays:
                    groups.setdefault(parts[1], {}).setdefault(parts[2], []).append(row.outcome == "pass")
        return {
            zone: [f"{sum(days[d])}/{len(days[d])}" if d in days else "—" for d in weekdays]
            for zone, days in sorted(groups.items())
        }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    return round(sorted_values[math.ceil(len(sorted_values) * fraction) - 1], 2)


def report_path(mode: Mode) -> Path:
    return REPORT_DIR / f"last-{mode}.json"


def load_report(path: Path) -> Scorecard:
    with path.open("rb") as stream:
        data = stream.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError("scorecard exceeds size limit")
    raw = json.loads(data)
    if not isinstance(raw, dict):
        raise ValueError("invalid scorecard")
    summary = raw.pop("summary", None)
    card = Scorecard.model_validate(raw)
    if summary != card.summary():
        raise ValueError("summary does not match recorded attempts")
    return card


def public_reports() -> list[Scorecard]:
    cards = []
    for mode in ("replay", "live"):
        try:
            card = load_report(REPORT_DIR / f"last-{mode}.json")
        except (OSError, ValidationError, ValueError):
            continue
        if card.mode == mode:
            cards.append(card)
    return cards


def release_errors(
    replay: Scorecard,
    live: Scorecard,
    commit: str,
    deployment: str,
    *,
    replay_catalog: dict[str, set[str]],
    live_catalog: dict[str, set[str]],
    now: AwareDatetime,
) -> list[str]:
    """Require clean matching source, full coverage, three live trials and fresh evidence on the same preview."""
    errors = []
    for mode, card, cases in (("replay", replay, replay_catalog), ("live", live, live_catalog)):
        if card.mode != mode or card.profile != "full" or not card.passed or card.catalog() != cases:
            errors.append(f"{mode} coverage or grade")
        if card.source.commit != commit or card.source.dirty is not False:
            errors.append(f"{mode} source revision")
        if not now - timedelta(hours=24) <= card.started_at <= card.finished_at <= now:
            errors.append(f"{mode} evidence age")
    if live.repeats < 3:
        errors.append("live repetition count")
    if not live.target or (live.target.environment, live.target.commit, live.target.deployment) != (
        "preview",
        commit,
        deployment,
    ):
        errors.append("preview identity")
    return errors
