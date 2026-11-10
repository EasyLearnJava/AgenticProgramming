"""Compare BM25, dense, scoped RRF and ColBERT evidence from one provider search per public question."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nimbus.config import Settings
from nimbus.park_ranking import RRF_K, SEMANTIC_WEIGHT
from nimbus.park_semantic import COLBERT_MODEL, PARK_MODEL, PARK_PROFILE
from nimbus.parks import (
    HOSTED_MIN_SEMANTIC_SCORE,
    HOSTED_STANDALONE_SEMANTIC_SCORE,
    MAX_CONTEXT_CHARS,
    MAX_PASSAGES,
    RERANK_CANDIDATES,
    make_park_knowledge,
)
from tools.eval_parks import ParkCase, evidence_rank, grade_retrieval, provider_failure, read_cases
from tools.park_replay import RecordingParkStore, save_recording


def ranked_profile(result: dict[str, Any], rank_key: str) -> dict[str, Any]:
    """Apply the production context limits to one ranking already measured on the identical eligible corpus."""
    candidates = [
        item for item in result.get("diagnostics", {}).get("candidates", []) if item.get(rank_key) is not None
    ]
    passages: list[dict[str, Any]] = []
    used = 0
    for item in sorted(candidates, key=lambda row: row[rank_key]):
        passage = item["chunk"]
        if len(passages) >= MAX_PASSAGES:
            break
        if used + len(passage["text"]) <= MAX_CONTEXT_CHARS:
            passages.append(passage)
            used += len(passage["text"])
    return {**result, "passages": passages, "status": "found" if passages else "not_found"}


def semantic_only(result: dict[str, Any]) -> dict[str, Any]:
    """Evaluate dense ranks at the candidate cutoff, independently of the hybrid's keyword/admission gate."""
    if result.get("semantic_status") != "ready":
        return {**result, "passages": [], "status": "unavailable"}
    return ranked_profile(result, "semantic_rank")


def retrieval_profiles(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compare stages without repeating provider calls or conflating a provider outage with abstention."""
    unavailable = {**result, "passages": [], "status": "unavailable"}
    return {
        "lexical": ranked_profile(result, "keyword_rank") if result.get("keyword_status") == "ready" else unavailable,
        "semantic": semantic_only(result),
        "rrf": ranked_profile(result, "rrf_rank") if result.get("keyword_status") == "ready" else unavailable,
        "hybrid": result,
    }


async def compare(settings: Settings, cases: list[ParkCase], *, recording: Path | None = None) -> dict[str, Any]:
    """Record grades and ranks only; a provider failure is separate from a legitimate retrieval miss."""
    hosted = make_park_knowledge(
        settings.model_copy(update={"parks_retrieval_mode": "hybrid", "parks_rerank_enabled": True})
    )
    if hosted is None or hosted.semantic_provider != "qdrant":
        raise ValueError("Select hosted Qdrant retrieval for this comparison")
    recorder = None
    if recording is not None:
        if cases != read_cases() or hosted.store is None:
            raise ValueError("Only the complete approved public suite may refresh replay evidence")
        recorder = RecordingParkStore(hosted.store)
        hosted.store = recorder
    rows = []
    for case in cases:
        if case.resolution != "resolved":
            continue
        destination = case.destination_id or ""
        hybrid = await hosted.search(destination, case.query, case.visit_date, explain=True)
        profiles = retrieval_profiles(hybrid)
        rows.append(
            {
                "id": case.id,
                "semantic_status": hybrid["semantic_status"],
                "rerank_status": hybrid.get("rerank_status", "disabled"),
                "provider_failure": provider_failure(hybrid)
                or ("unavailable" if hybrid.get("rerank_status", "disabled") == "disabled" else None),
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
    for name in ("lexical", "semantic", "rrf", "hybrid"):
        evidence = [row["profiles"][name]["evidence_rank"] for row in rows if row["grades_evidence"]]
        totals[name] = {
            "passed": sum(row["profiles"][name]["passed"] for row in rows),
            "cases": len(rows),
            "recall_at_4": sum(rank is not None for rank in evidence) / max(1, len(evidence)),
            "top_1": sum(rank == 1 for rank in evidence) / max(1, len(evidence)),
            "mrr_at_4": sum(1 / rank for rank in evidence if rank) / max(1, len(evidence)),
        }
    report = {
        "at": datetime.now(UTC).isoformat(),
        "index_version": hosted.index_version,
        "policy": {
            "model": PARK_MODEL,
            "embedding_profile": PARK_PROFILE,
            "bm25_statistics_scope": "eligible-corpus",
            "rerank_model": COLBERT_MODEL,
            "rerank_limit": RERANK_CANDIDATES,
            "comparison": "same_request_same_eligible_candidates",
            "hybrid_profile": "colbert_reranked_rrf",
            "dense_baseline": "candidate_cutoff_without_keyword_gate",
            "semantic_candidate_cutoff": HOSTED_MIN_SEMANTIC_SCORE,
            "semantic_only_admission_cutoff": HOSTED_STANDALONE_SEMANTIC_SCORE,
            "rrf_k": RRF_K,
            "keyword_weight": 1.0,
            "semantic_weight": SEMANTIC_WEIGHT,
        },
        "provider_failures": sum(row["provider_failure"] is not None for row in rows),
        "quality_regressions": [
            metric
            for metric in ("passed", "recall_at_4", "top_1", "mrr_at_4")
            if totals["hybrid"][metric] < totals["rrf"][metric]
        ],
        "summary": totals,
        "cases": rows,
    }
    if (
        recorder is not None
        and recording is not None
        and rows
        and not report["provider_failures"]
        and not report["quality_regressions"]
        and all(row["profiles"]["hybrid"]["passed"] for row in rows)
    ):
        save_recording(recorder, hosted.index_version, recording, prepared_path=settings.parks_prepared_path)
    return report


def main() -> int:
    """Run an explicitly requested provider comparison and write a sanitized reproducible artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evals/parks.json"))
    parser.add_argument("--output", type=Path, default=Path("evals/park-colbert-last-run.json"))
    parser.add_argument("--recording", type=Path, help="Refresh the public-suite offline score recording from this run")
    args = parser.parse_args()
    settings = Settings(parks_retrieval_mode="hybrid")
    try:
        report = asyncio.run(compare(settings, read_cases(args.cases), recording=args.recording))
        report["cases_sha256"] = hashlib.sha256(args.cases.read_bytes()).hexdigest()
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
