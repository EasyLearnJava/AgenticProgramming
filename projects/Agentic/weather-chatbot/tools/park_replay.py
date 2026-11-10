"""Record public Qdrant search scores explicitly, then replay the real ranker offline without pretending it is live."""

import argparse
import asyncio
import copy
import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from nimbus.config import Settings
from nimbus.park_ingest import compact_chunk, load_catalog, load_prepared
from nimbus.park_models import ParkChunk
from nimbus.park_semantic import PARK_MODEL, PARK_PROFILE, CatalogResult, SearchMethod, SemanticResult
from nimbus.parks import ParkKnowledge, ParkStore, make_park_knowledge
from tools.eval_parks import CASES_PATH, PROJECT_ROOT, read_cases, run_cases, to_report

RECORDING = PROJECT_ROOT / "evals" / "park-retrieval-recording.json"
MAX_RECORDING_BYTES = 2_000_000


def request_key(query: str, scope: Mapping[str, Any]) -> str:
    """Hash the complete question/method/scope contract; no question or search terms are written to recordings."""
    raw = json.dumps({"query": query, **scope}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class RecordedParkStore:
    """Replay real provider scores with reviewed public text; unknown inputs fail instead of manufacturing matches."""

    configured = True

    def __init__(
        self,
        recording: Path = RECORDING,
        *,
        prepared_path: Path = PROJECT_ROOT / "data/parks/prepared.json",
        cases_path: Path = CASES_PATH,
    ) -> None:
        """Bind bounded recordings to the exact approved corpus, provider profile and public evaluation cases."""
        self.prepared = load_prepared(prepared_path)
        if not recording.is_file() or recording.stat().st_size > MAX_RECORDING_BYTES:
            raise ValueError("Missing or oversized park recording")
        document = json.loads(recording.read_text(encoding="utf-8"))
        fields = {"schema_version", "index_version", "model", "profile", "cases_sha256", "recorded_at", "records"}
        if (
            not isinstance(document, dict)
            or set(document) != fields
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or document["index_version"] != self.prepared["index_version"]
            or document["model"] != PARK_MODEL
            or document["profile"] != PARK_PROFILE
            or document["cases_sha256"] != hashlib.sha256(cases_path.read_bytes()).hexdigest()
            or datetime.fromisoformat(document["recorded_at"]).tzinfo is None
            or not isinstance(document["records"], dict)
            or not 1 <= len(document["records"]) <= 1000
        ):
            raise ValueError("Park recording does not match the approved retrieval contract")
        self.expected = {item["id"]: compact_chunk(ParkChunk.model_validate(item)) for item in self.prepared["chunks"]}
        self.records: dict[str, dict[str, Any]] = document["records"]
        for key, row in self.records.items():
            if (
                not isinstance(key, str)
                or len(key) != 64
                or any(char not in "0123456789abcdef" for char in key)
                or not isinstance(row, dict)
                or set(row) != {"method", "scores"}
                or row["method"] not in {"semantic", "bm25"}
                or not isinstance(row["scores"], dict)
                or any(
                    identity not in self.expected
                    or type(score) not in {int, float}
                    or not math.isfinite(score)
                    or (not -1 <= score <= 1 if row["method"] == "semantic" else score < 0)
                    for identity, score in row["scores"].items()
                )
            ):
                raise ValueError("Invalid recorded park scores")

    async def catalog(
        self, index_version: str, expected: Mapping[str, Mapping[str, Any]], *, with_vectors: bool = False
    ) -> CatalogResult:
        """Expose reviewed public text for replay only; vector visualization is not a replay operation."""
        if index_version != self.prepared["index_version"] or dict(expected) != self.expected or with_vectors:
            return CatalogResult("index_mismatch")
        return CatalogResult("ready", [{**copy.deepcopy(item), "embedding": []} for item in self.prepared["chunks"]])

    async def search(
        self,
        query: str,
        *,
        index_version: str,
        park_id: str,
        destination_id: str,
        season: str | None,
        eligible: Mapping[str, str],
        method: SearchMethod = "semantic",
    ) -> SemanticResult:
        """Return a detached score recording only for the identical query and scope."""
        key = request_key(
            query,
            {
                "index_version": index_version,
                "park_id": park_id,
                "destination_id": destination_id,
                "season": season,
                "eligible": dict(eligible),
                "method": method,
            },
        )
        row = self.records.get(key)
        if row is None or row["method"] != method:
            return SemanticResult("index_mismatch")
        return SemanticResult("ready", dict(row["scores"]))

    async def health(self, index_version: str) -> str:
        """Check only recording identity, never report replay as live Qdrant health."""
        return "ready" if index_version == self.prepared["index_version"] else "index_mismatch"


class RecordingParkStore:
    """Forward real public evaluation requests and retain only hashes, method names and numeric result scores."""

    def __init__(self, source: ParkStore) -> None:
        """Wrap the configured real provider without changing its requests or validation."""
        self.source = source
        self.records: dict[str, dict[str, Any]] = {}

    @property
    def configured(self) -> bool:
        """Reflect actual provider configuration."""
        return self.source.configured

    async def catalog(
        self, index_version: str, expected: Mapping[str, Mapping[str, Any]], *, with_vectors: bool = False
    ) -> CatalogResult:
        """Preserve the provider's full publication and provenance checks."""
        return await self.source.catalog(index_version, expected, with_vectors=with_vectors)

    async def search(
        self,
        query: str,
        *,
        index_version: str,
        park_id: str,
        destination_id: str,
        season: str | None,
        eligible: Mapping[str, str],
        method: SearchMethod = "semantic",
    ) -> SemanticResult:
        """Record successful provider scores only; outages cannot become a replay baseline."""
        result = await self.source.search(
            query,
            index_version=index_version,
            park_id=park_id,
            destination_id=destination_id,
            season=season,
            eligible=eligible,
            method=method,
        )
        if result.status == "ready":
            key = request_key(
                query,
                {
                    "index_version": index_version,
                    "park_id": park_id,
                    "destination_id": destination_id,
                    "season": season,
                    "eligible": dict(eligible),
                    "method": method,
                },
            )
            row = {"method": method, "scores": dict(result.scores)}
            if key in self.records and self.records[key] != row:
                raise ValueError("Provider results changed during recording")
            self.records[key] = row
        return result

    async def health(self, index_version: str) -> str:
        """Delegate publication readiness without recording health as retrieval evidence."""
        return await self.source.health(index_version)


async def replay_park_cases() -> list[dict[str, Any]]:
    """Run the public cases through real routing, rank fusion and context bounds using recorded Qdrant scores."""
    knowledge = ParkKnowledge(PROJECT_ROOT / "data/parks/catalog.json", store=RecordedParkStore())
    rows = []
    for case in read_cases():
        start = perf_counter()
        (result,) = await run_cases(knowledge, [case])
        rows.append(
            {
                "suite": "parks",
                "case_id": case.id,
                "attempt": 1,
                "outcome": "pass" if result.passed else "retrieval_mismatch",
                "duration_ms": round((perf_counter() - start) * 1000),
                "checks": ["recorded_qdrant_retrieval"],
            }
        )
    return rows


async def record_public_cases(settings: Settings, output: Path) -> int:
    """Explicitly call Qdrant for the reviewed public suite and atomically save successful provider recordings."""
    knowledge = make_park_knowledge(
        settings.model_copy(update={"parks_enabled": True, "parks_retrieval_mode": "hybrid"})
    )
    if knowledge is None or knowledge.store is None:
        raise ValueError("Configure hosted park retrieval before recording")
    corpus = load_catalog(settings.parks_index_path)
    source = RecordingParkStore(knowledge.store)
    knowledge.store = source
    cases = read_cases()
    results = await run_cases(knowledge, cases)
    if not results or any(result.provider_failure for result in results):
        raise ValueError("Failed provider work cannot publish a replay baseline")
    document = {
        "schema_version": 1,
        "index_version": corpus["index_version"],
        "model": PARK_MODEL,
        "profile": PARK_PROFILE,
        "cases_sha256": hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        "recorded_at": datetime.now(UTC).isoformat(),
        "records": source.records,
    }
    temporary = output.with_suffix(".pending.json")
    try:
        temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        RecordedParkStore(temporary, prepared_path=settings.parks_prepared_path)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print("\n".join(to_report(results)))
    return int(any(not result.passed for result in results))


def main() -> int:
    """Record the reviewed public cases only when an operator explicitly runs this provider command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=RECORDING)
    args = parser.parse_args()
    try:
        return asyncio.run(record_public_cases(Settings(), args.output))
    except Exception as error:
        print(f"Park recording failed ({type(error).__name__}); existing evidence was not replaced.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
