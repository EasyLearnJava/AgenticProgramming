"""Compare lexical, semantic-only and fused park evidence using public labeled questions and hosted scores."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nimbus.config import Settings
from nimbus.park_ranking import RRF_K, SEMANTIC_WEIGHT
from nimbus.park_semantic import PARK_MODEL, PARK_PROFILE
from nimbus.parks import (
    HOSTED_MIN_SEMANTIC_SCORE,
    HOSTED_STANDALONE_SEMANTIC_SCORE,
    MAX_CONTEXT_CHARS,
    MAX_PASSAGES,
    ParkKnowledge,
    make_park_knowledge,
)
from tools.eval_parks import ParkCase, evidence_rank, grade_retrieval, read_cases


def semantic_only(result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate dense ranks at the candidate cutoff, independently of the hybrid's keyword/admission gate."""
    candidates = [
        item for item in result.get("diagnostics", {}).get("candidates", []) if item["semantic_rank"] is not None
    ]
    passages: list[dict[str, Any]] = []
    used = 0
    for item in sorted(candidates, key=lambda row: row["semantic_rank"]):
        passage = item["chunk"]
        if len(passages) >= MAX_PASSAGES:
            break
        if used + len(passage["text"]) <= MAX_CONTEXT_CHARS:
            passages.append(passage)
            used += len(passage["text"])
    return {**result, "passages": passages, "status": "found" if passages else "not_found"}


async def compare(settings: Settings, cases: list[ParkCase]) -> dict[str, Any]:
    """Record grades and ranks only; a provider failure is separate from a legitimate retrieval miss."""
    hosted = make_park_knowledge(settings)
    if hosted is None or hosted.semantic_provider != "qdrant":
        raise ValueError("Select hosted Qdrant retrieval for this comparison")
    lexical = ParkKnowledge(settings.parks_index_path)
    rows = []
    for case in cases:
        if case.resolution != "resolved":
            continue
        destination = case.destination_id or ""
        baseline = await lexical.search(destination, case.query, case.visit_date)
        hybrid = await hosted.search(destination, case.query, case.visit_date, explain=True)
        profiles = {"lexical": baseline, "semantic": semantic_only(hybrid), "hybrid": hybrid}
        rows.append(
            {
                "id": case.id,
                "semantic_status": hybrid["semantic_status"],
                "grades_evidence": case.expected_status == "found",
                "profiles": {
                    name: {
                        "passed": not grade_retrieval(case, result),
                        "misses": grade_retrieval(case, result),
                        "evidence_rank": evidence_rank(case, result),
                    }
                    for name, result in profiles.items()
                },
            }
        )
    totals = {}
    for name in ("lexical", "semantic", "hybrid"):
        evidence = [row["profiles"][name]["evidence_rank"] for row in rows if row["grades_evidence"]]
        totals[name] = {
            "passed": sum(row["profiles"][name]["passed"] for row in rows),
            "cases": len(rows),
            "recall_at_4": sum(rank is not None for rank in evidence) / max(1, len(evidence)),
            "top_1": sum(rank == 1 for rank in evidence) / max(1, len(evidence)),
            "mrr_at_4": sum(1 / rank for rank in evidence if rank) / max(1, len(evidence)),
        }
    return {
        "at": datetime.now(UTC).isoformat(),
        "index_version": hosted.index_version,
        "policy": {
            "model": PARK_MODEL,
            "embedding_profile": PARK_PROFILE,
            "dense_baseline": "candidate_cutoff_without_keyword_gate",
            "semantic_candidate_cutoff": HOSTED_MIN_SEMANTIC_SCORE,
            "semantic_only_admission_cutoff": HOSTED_STANDALONE_SEMANTIC_SCORE,
            "rrf_k": RRF_K,
            "keyword_weight": 1.0,
            "semantic_weight": SEMANTIC_WEIGHT,
        },
        "provider_failures": sum(row["semantic_status"] != "ready" for row in rows),
        "quality_regressions": [
            metric
            for metric in ("passed", "recall_at_4", "top_1", "mrr_at_4")
            if totals["hybrid"][metric] < totals["lexical"][metric]
        ],
        "summary": totals,
        "cases": rows,
    }


def main() -> int:
    """Run an explicitly requested provider comparison and write a sanitized reproducible artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evals/parks.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/park-hybrid-last-run.json"))
    args = parser.parse_args()
    settings = Settings(parks_semantic_provider="qdrant", parks_retrieval_mode="hybrid")
    try:
        report = asyncio.run(compare(settings, read_cases(args.cases)))
    except Exception as error:
        print(f"Park comparison unavailable ({type(error).__name__}); no success report was produced.")
        return 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": report["summary"], "provider_failures": report["provider_failures"]}, indent=2))
    return int(
        report["provider_failures"] > 0
        or bool(report["quality_regressions"])
        or not report["cases"]
        or report["summary"]["hybrid"]["passed"] < len(report["cases"])
    )


if __name__ == "__main__":
    raise SystemExit(main())
