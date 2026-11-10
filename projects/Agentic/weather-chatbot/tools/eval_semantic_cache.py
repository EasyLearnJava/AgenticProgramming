"""Live free MiniLM/cache eval in an isolated collection; fixtures never enter visitors' answer cache."""

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2

from nimbus.config import Settings
from nimbus.constants import PROJECT_ROOT
from nimbus.semantic_cache.models import CacheEntry, WeatherEvidence
from nimbus.semantic_cache.policy import cache_policy, digest, normalized
from nimbus.semantic_cache.service import SemanticCacheService
from nimbus.tools import CurrentWeatherOutput, GeocodeOutput
from tools.setup_semantic_cache import setup


def score_outcomes(outcomes: list[dict[str, Any]], exact: str, isolated: str) -> dict[str, Any]:
    """Separate provider failures and false hits from tolerated paraphrase misses."""
    training = [case for case in outcomes if case["split"] == "training"]
    positives = [case for case in outcomes if case["split"] == "validation" and case["expected"] == "hit"]
    negatives = [case for case in outcomes if case["expected"] != "hit"]
    provider_errors = sum(case["result"] == "error" for case in outcomes) + (exact == "error") + (isolated == "error")
    false_hits = sum(case["result"] in {"exact_hit", "semantic_hit"} for case in negatives)
    recall = sum(bool(case["passed"]) for case in positives) / len(positives) if positives else 0.0
    return {
        "passed": not provider_errors
        and not false_hits
        and all(case["passed"] for case in training + negatives)
        and recall >= 0.8
        and exact == "exact_hit"
        and isolated == "miss",
        "provider_errors": provider_errors,
        "false_hits": false_hits,
        "positive_recall": recall,
    }


async def evaluate(settings: Settings, cases_path: Path) -> dict[str, Any]:
    """Exercise real hosted embeddings and the application adapter, reporting false hits independently of outages."""
    cases = json.loads(await asyncio.to_thread(cases_path.read_text, encoding="utf-8"))
    # ① An explicit evaluation-only collection and random partition protect real cache records.
    eval_settings = Settings(
        **{
            **settings.model_dump(),
            "qdrant_collection": settings.qdrant_collection + "_eval",
            "semantic_cache_mode": "on",
        }
    )
    await setup(eval_settings)
    now = time.time()
    moment = datetime.fromtimestamp(now, UTC)
    policy = cache_policy(cases["seed"], moment, "en-US", "America/Chicago")
    assert policy is not None  # noqa: S101 - committed fixture is an explicit weather overview
    scope, context = digest(uuid4().hex), digest("semantic-evaluation-v1")
    current = CurrentWeatherOutput(
        latitude=32.78,
        longitude=-96.81,
        time_zone="America/Chicago",
        observed_at=moment.isoformat(),
        condition="Clear sky",
        is_day=True,
        temperature=70,
        feels_like=70,
        temperature_unit="°F",
        wind_speed=1,
        wind_speed_unit="mph",
    )
    places = GeocodeOutput(
        candidates=[
            {
                "name": "Dallas",
                "region": "Texas",
                "country_code": "US",
                "latitude": 32.78,
                "longitude": -96.81,
                "time_zone": "America/Chicago",
            }
        ],
        is_ambiguous=False,
    )
    entry = CacheEntry(
        scope=scope,
        context=context,
        exact=digest(normalized(cases["seed"])),
        policy=policy,
        label="Evaluation fixture",
        answer="Evaluation fixture only; not live weather.",
        evidence=WeatherEvidence(places=places, current=current),
        created_at=now,
        expires_at=now + 120,
        evidence_fetched_at=now,
    )
    service = SemanticCacheService(eval_settings)
    outcomes: list[dict[str, Any]] = []
    try:
        if (await service.store(cases["seed"], entry)).status != "saved":
            raise RuntimeError("seed_unavailable")
        # ② No model is called; hits therefore prove reuse, not Gemini answering the question again.
        for index, case in enumerate(cases["cases"]):
            candidate_policy = cache_policy(case["question"], moment, "en-US", "America/Chicago")
            result = "bypass"
            if candidate_policy:
                # Independent clients avoid the intentionally strict per-instance UI gate during a bounded eval.
                result = (
                    await SemanticCacheService(eval_settings).lookup(case["question"], scope, context, candidate_policy)
                ).status
            hit = result in {"semantic_hit", "exact_hit"}
            passed = hit if case["expected"] == "hit" else result == case["expected"]
            outcomes.append(
                {
                    "id": case["id"],
                    "split": case["split"],
                    "expected": case["expected"],
                    "result": result,
                    "passed": passed,
                    "case": index + 1,
                }
            )
        exact = await SemanticCacheService(eval_settings).lookup(cases["seed"], scope, context, policy)
        isolated = await SemanticCacheService(eval_settings).lookup(cases["seed"], digest(uuid4().hex), context, policy)
        return {
            **score_outcomes(outcomes, exact.status, isolated.status),
            "threshold": settings.semantic_cache_threshold,
            "cases": outcomes,
            "exact": exact.status,
            "cross_browser": isolated.status,
            "checked_at": moment.isoformat(),
        }
    finally:
        # ③ Remove only this run's disposable fixtures. No main-cache records or other evaluation runs are touched.
        assert eval_settings.qdrant_api_key is not None  # noqa: S101 - setup required the credential
        async with httpx2.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                f"{eval_settings.qdrant_url}/collections/{eval_settings.qdrant_collection}/points/delete?wait=true",
                headers={"api-key": eval_settings.qdrant_api_key.get_secret_value()},
                json={"filter": {"must": [{"key": "scope", "match": {"value": scope}}]}},
            )
            response.raise_for_status()


def main() -> int:
    """Write a sanitized result artifact; never print provider error bodies, keys or private questions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "evals/semantic-cache-last-run.json")
    parser.add_argument("--cases", type=Path, default=PROJECT_ROOT / "evals/semantic_cache.json")
    args = parser.parse_args()
    try:
        report = asyncio.run(evaluate(Settings(), args.cases))
    except Exception as error:
        print(f"Live cache evaluation unavailable ({type(error).__name__}); not counted as a pass.")
        return 1
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
