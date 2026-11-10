"""Publish approved, tokenizer-prepared park chunks to a dedicated Qdrant collection using hosted MiniLM."""

import argparse
import asyncio
import math
import sys
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx2

from nimbus.config import Settings
from nimbus.park_embeddings import MINILM_MODEL, to_embedding_text
from nimbus.park_semantic import (
    PARK_DIMENSIONS,
    PARK_MODEL,
    PARK_PROFILE,
    PARK_SCHEMA,
    QdrantParkAPI,
    chunk_payload,
    manifest_id,
    manifest_payload,
    point_id,
)
from nimbus.parks import ParkKnowledge

SETUP_SECONDS = 120
BATCH_SIZE = 16
OWNER_ID = str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/collection"))
OWNER = {"kind": "ownership", "schema": PARK_SCHEMA, "profile": PARK_PROFILE, "model": PARK_MODEL}
MARKER_VECTOR = [1.0, *([0.0] * (PARK_DIMENSIONS - 1))]


def make_setup_client() -> httpx2.AsyncClient:
    """Allow bounded hosted embedding work during explicit setup, never during application startup."""
    return httpx2.AsyncClient(timeout=30, follow_redirects=False, limits=httpx2.Limits(max_connections=2))


def _completed(document: dict[str, Any] | None) -> None:
    """A wait=true write must report completed, not merely acknowledge an asynchronous operation."""
    result = document.get("result") if document else None
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError("Park publication write was not confirmed")


def _vector_ready(value: object) -> bool:
    """A retrieved hosted vector must have the supported dimensions and a finite, nonzero direction."""
    return (
        isinstance(value, list)
        and len(value) == PARK_DIMENSIONS
        and all(type(number) in {int, float} and -1e6 < number < 1e6 and math.isfinite(number) for number in value)
        and any(number != 0 for number in value)
    )


def read_public_chunks(settings: Settings) -> tuple[str, list[dict[str, Any]]]:
    """Require the existing tokenizer-prepared index, but regenerate every vector with the hosted model."""
    knowledge = ParkKnowledge(settings.parks_index_path)
    catalog = knowledge.inspection()
    if (
        not catalog["available"]
        or not catalog["embedding_model"].startswith(f"{MINILM_MODEL}@")
        or catalog["dimensions"] != PARK_DIMENSIONS
        or not catalog["chunks"]
        or any(not _vector_ready(chunk["embedding"]) for chunk in catalog["chunks"])
    ):
        raise ValueError("Build the tokenizer-prepared MiniLM park index before publishing hosted search")
    return str(catalog["index_version"]), list(catalog["chunks"])


async def _collection(api: QdrantParkAPI, http: httpx2.AsyncClient) -> None:
    """Create or verify our collection; refuse existing unmanaged data and incompatible vector settings."""
    current = await api.request(http, "GET", "", missing_ok=True)
    if current is None:
        created = await api.request(http, "PUT", "", {"vectors": {"size": PARK_DIMENSIONS, "distance": "Cosine"}})
        if not created or created.get("result") is not True:
            raise ValueError("Park collection creation was not confirmed")
        current = await api.request(http, "GET", "")
    if current is None:
        raise ValueError("Park collection is missing")
    result = current.get("result")
    vectors = result.get("config", {}).get("params", {}).get("vectors") if isinstance(result, dict) else None
    if (
        not isinstance(vectors, dict)
        or type(vectors.get("size")) is not int
        or vectors.get("size") != PARK_DIMENSIONS
        or vectors.get("distance") != "Cosine"
    ):
        raise ValueError("Existing park collection has incompatible vector settings")
    owner = await api.request(http, "GET", f"/points/{OWNER_ID}", missing_ok=True)
    owner_result = owner.get("result") if owner else None
    if owner is not None:
        if not isinstance(owner_result, dict) or owner_result.get("payload") != OWNER:
            raise ValueError("Existing collection is not owned by the park index")
    else:
        count = await api.request(http, "POST", "/points/count", {"exact": True})
        counted = count.get("result") if count else None
        if not isinstance(counted, dict) or type(counted.get("count")) is not int or counted["count"] != 0:
            raise ValueError("Refusing to publish into an unmanaged collection")
        _completed(
            await api.request(
                http,
                "PUT",
                "/points?wait=true",
                {"points": [{"id": OWNER_ID, "vector": MARKER_VECTOR, "payload": OWNER}]},
            )
        )
    for key in ("kind", "index_version", "model", "profile", "park_id", "destination_ids", "seasons"):
        _completed(await api.request(http, "PUT", "/index?wait=true", {"field_name": key, "field_schema": "keyword"}))


async def _verify_batch(
    api: QdrantParkAPI, http: httpx2.AsyncClient, batch: list[dict[str, Any]], version: str
) -> None:
    """Re-read hosted vectors and exact public metadata before making this version available to chat."""
    expected = {point_id(version, chunk["id"]): chunk_payload(chunk, version) for chunk in batch}
    document = await api.request(
        http, "POST", "/points", {"ids": list(expected), "with_payload": True, "with_vector": True}
    )
    points = document.get("result") if document else None
    if not isinstance(points, list) or len(points) != len(expected):
        raise ValueError("Park publication is incomplete")
    seen = set()
    for item in points:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or item["id"] not in expected
            or item["id"] in seen
            or item.get("payload") != expected[item["id"]]
            or not _vector_ready(item.get("vector"))
        ):
            raise ValueError("Park publication did not match its local index")
        seen.add(item["id"])


async def setup(
    settings: Settings,
    factory: Callable[[], httpx2.AsyncClient] = make_setup_client,
) -> tuple[str, int]:
    """Upload only public source chunks and publish a verified readiness marker; never expire or delete records."""
    api = QdrantParkAPI(settings)
    if not api.configured:
        raise ValueError("Configure a dedicated park collection and an authorized Qdrant credential")
    version, chunks = read_public_chunks(settings)
    async with asyncio.timeout(SETUP_SECONDS), factory() as http:
        # ① Scope collection ownership before making any payload or index changes.
        await _collection(api, http)
        # ② Hosted inference uses exactly the same model as runtime queries, not the local vectors in SQLite.
        for offset in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[offset : offset + BATCH_SIZE]
            points = [
                {
                    "id": point_id(version, chunk["id"]),
                    "vector": {
                        "text": to_embedding_text(chunk["title"], chunk["section"], chunk["text"]),
                        "model": PARK_MODEL,
                    },
                    "payload": chunk_payload(chunk, version),
                }
                for chunk in batch
            ]
            _completed(await api.request(http, "PUT", "/points?wait=true", {"points": points}))
            await _verify_batch(api, http, batch, version)
        # ③ A count guards against duplicate/unrecognized records; readers require the marker written last.
        count = await api.request(
            http,
            "POST",
            "/points/count",
            {
                "exact": True,
                "filter": {
                    "must": [
                        {"key": "kind", "match": {"value": "chunk"}},
                        {"key": "index_version", "match": {"value": version}},
                        {"key": "profile", "match": {"value": PARK_PROFILE}},
                    ]
                },
            },
        )
        counted = count.get("result") if count else None
        if not isinstance(counted, dict) or type(counted.get("count")) is not int or counted["count"] != len(chunks):
            raise ValueError("Park publication count did not match")
        marker = manifest_payload(version, len(chunks))
        _completed(
            await api.request(
                http,
                "PUT",
                "/points?wait=true",
                {"points": [{"id": manifest_id(version), "vector": MARKER_VECTOR, "payload": marker}]},
            )
        )
        verified = await api.request(http, "GET", f"/points/{manifest_id(version)}")
        result = verified.get("result") if verified else None
        if not isinstance(result, dict) or result.get("payload") != marker:
            raise ValueError("Park readiness marker was not verified")
    return version, len(chunks)


def main() -> int:
    """Publish an explicitly selected collection, reporting only public version/count and safe failure classes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", help="Dedicated park collection; must differ from the weather cache")
    args = parser.parse_args()
    try:
        settings = Settings(**({"parks_qdrant_collection": args.collection} if args.collection else {}))
        version, count = asyncio.run(setup(settings))
    except Exception as error:
        print(f"Park search setup failed ({type(error).__name__}); check the index, credentials and collection.")
        return 1
    print(f"Verified hosted park index {version}: {count} public chunks, {PARK_DIMENSIONS} dimensions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
