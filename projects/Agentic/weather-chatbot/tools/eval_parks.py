"""
tools/eval_parks.py: reviewed park questions, graded against Qdrant without asking a generative language model.
Each expected source must contain the labeled evidence, every passage must apply to the requested destination,
and unsupported places and questions must abstain. Reports contain case IDs and grades, never question text.
Run from the project directory: uv run python -m tools.eval_parks.
"""

import argparse
import asyncio
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "evals" / "parks.json"
INDEX_PATH = PROJECT_ROOT / "data" / "parks" / "catalog.json"


class ParkCase(BaseModel):
    """One human-labeled question and the destination and source evidence retrieval must find."""

    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    destination_id: str | None = None
    resolution: Literal["resolved", "ambiguous", "unsupported"] = "resolved"
    query: str = Field(min_length=1)
    visit_date: date | None = None
    expected_status: Literal["found", "not_found"] = "found"
    document_ids: list[str] = Field(default_factory=list)
    evidence_terms: list[str] = Field(default_factory=list)
    max_evidence_rank: int = Field(default=4, ge=1, le=4)
    forbidden_sections: list[str] = Field(default_factory=list)


class ParkResult(BaseModel):
    """A question's grade, containing identifiers and counts but no question or source text."""

    id: str
    passed: bool
    misses: list[str]
    passage_count: int = 0
    retrieval_mode: str = "none"
    evidence_rank: int | None = None
    grades_evidence: bool = False
    provider_failure: str | None = None


class KnowledgeSearch(Protocol):
    """The destination and retrieval operations exercised by provider evaluations and offline grading tests."""

    def resolve(self, query: str) -> dict[str, Any]:
        """Resolve a name to candidates and an explicit status."""
        ...

    async def search(self, destination_id: str, query: str, visit_date: date | None = None) -> dict[str, Any]:
        """Return passages for the named destination and question."""
        ...


def read_cases(path: Path = CASES_PATH) -> list[ParkCase]:
    """Read the labeled questions, refusing duplicate case IDs."""
    cases = TypeAdapter(list[ParkCase]).validate_json(path.read_bytes())
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("park evaluation case IDs must be unique")
    return cases


def evidence_rank(case: ParkCase, result: dict[str, Any]) -> int | None:
    """The first returned rank with labeled evidence in the required source, or None when evidence is missing."""
    return next(
        (
            rank
            for rank, passage in enumerate(result.get("passages", []), start=1)
            if (not case.document_ids or passage.get("document_id") in case.document_ids)
            and all(re.search(term, str(passage.get("text", "")), re.I) for term in case.evidence_terms)
        ),
        None,
    )


def grade_retrieval(case: ParkCase, result: dict[str, Any]) -> list[str]:
    """Check retrieval status, destination isolation, and labeled evidence in the same source passage."""
    # ① Every result must have the expected status and an honest empty result for an unsupported question.
    misses = []
    if result.get("status") != case.expected_status:
        misses.append(f"expected {case.expected_status}, got {result.get('status')}")
    passages = result.get("passages", [])
    if case.expected_status == "not_found":
        if passages:
            misses.append("unexpected passages")
        return misses
    # ② A relevant-sounding paragraph from another trail is still wrong.
    if any(case.destination_id not in passage.get("destination_ids", []) for passage in passages):
        misses.append("passage belongs to another destination")
    if any(passage.get("section") in case.forbidden_sections for passage in passages):
        misses.append("passage belongs to an excluded season or section")
    # ③ Source and evidence must occur together; finding each in unrelated passages does not pass.
    rank = evidence_rank(case, result)
    if rank is None:
        misses.append("supporting passage missing")
    elif rank > case.max_evidence_rank:
        misses.append(f"supporting passage below rank {case.max_evidence_rank}")
    return misses


async def run_cases(knowledge: KnowledgeSearch, cases: Sequence[ParkCase]) -> list[ParkResult]:
    """Resolve and retrieve each case, without searching ambiguous or unsupported destinations."""
    results = []
    for case in cases:
        # ① Resolve first; expected ambiguity and unsupported names end without retrieval.
        resolved = knowledge.resolve(case.destination)
        misses = []
        if resolved.get("status") != case.resolution:
            misses.append(f"expected resolution {case.resolution}, got {resolved.get('status')}")
        candidates = resolved.get("candidates", [])
        destination = resolved.get("destination") or (candidates[0] if len(candidates) == 1 else {})
        if case.resolution != "resolved":
            results.append(ParkResult(id=case.id, passed=not misses, misses=misses))
            continue
        if destination.get("id") != case.destination_id:
            misses.append("wrong destination")
        if misses:
            results.append(ParkResult(id=case.id, passed=False, misses=misses))
            continue
        # ② Query only the resolved ID, then grade returned evidence rather than model wording.
        result = await knowledge.search(str(destination["id"]), case.query, case.visit_date)
        failure = provider_failure(result)
        if failure:
            misses.append(f"provider {failure}")
        misses.extend(grade_retrieval(case, result))
        results.append(
            ParkResult(
                id=case.id,
                passed=not misses,
                misses=misses,
                passage_count=len(result.get("passages", [])),
                retrieval_mode=str(result.get("retrieval_mode", "none")),
                evidence_rank=evidence_rank(case, result) if case.expected_status == "found" else None,
                grades_evidence=case.expected_status == "found",
                provider_failure=failure,
            )
        )
    return results


def to_report(results: Sequence[ParkResult]) -> list[str]:
    """Summarize case IDs, evidence counts and failures, never the questions' text."""
    lines = []
    for result in results:
        lines.append(
            f"{'pass' if result.passed else 'FAIL'}  {result.id}: "
            f"{result.passage_count} passages, {result.retrieval_mode}"
        )
        lines.extend(f"      {miss}" for miss in result.misses)
    evidence = [result for result in results if result.grades_evidence]
    if evidence:
        recall = sum(result.evidence_rank is not None for result in evidence) / len(evidence)
        reciprocal = sum(1 / result.evidence_rank for result in evidence if result.evidence_rank) / len(evidence)
        top_one = sum(result.evidence_rank == 1 for result in evidence) / len(evidence)
        lines.append(f"Evidence recall@4 {recall:.1%}; top-1 {top_one:.1%}; MRR@4 {reciprocal:.3f}")
    lines.append(f"{sum(result.passed for result in results)} of {len(results)} passed")
    return lines


def provider_failure(result: dict[str, Any]) -> str | None:
    """Keep unavailable provider work separate from empty evidence, using only fixed public reason codes."""
    failures = {"unconfigured", "index_mismatch", "unavailable", "invalid_response", "timeout"}
    for value in (result.get("keyword_status", "ready"), result.get("semantic_status", "disabled")):
        if not isinstance(value, str) or value not in {"ready", "disabled", "not_needed"}:
            return value if isinstance(value, str) and value in failures else "invalid_response"
    return "unavailable" if result.get("status") == "unavailable" else None


def main() -> int:
    """Grade explicitly configured hosted retrieval; any provider failure or missed case exits unsuccessfully."""
    from nimbus.config import Settings
    from nimbus.parks import make_park_knowledge

    parser = argparse.ArgumentParser(description="Evaluate Qdrant park retrieval without Gemini calls.")
    parser.add_argument("--index", type=Path, default=INDEX_PATH, help="Compact runtime identity catalog")
    parser.add_argument("--cases", type=Path, default=CASES_PATH)
    parser.add_argument("--lexical-only", action="store_true", help="Evaluate Qdrant BM25 without dense inference")
    args = parser.parse_args()
    settings = Settings(
        parks_enabled=True,
        parks_index_path=args.index,
        parks_retrieval_mode="lexical" if args.lexical_only else "hybrid",
    )
    knowledge = make_park_knowledge(settings)
    if knowledge is None:
        raise ValueError("Park knowledge is disabled")
    print("Evaluating Qdrant BM25." if args.lexical_only else "Evaluating Qdrant BM25 + hosted semantic retrieval.")
    results = asyncio.run(run_cases(knowledge, read_cases(args.cases)))
    print("\n".join(to_report(results)))
    return int(not results or any(not result.passed for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
