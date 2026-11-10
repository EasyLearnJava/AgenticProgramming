"""Publish public BM25 text, reusable MiniLM vectors and ColBERT multivectors to a dedicated Qdrant collection."""

import argparse
import asyncio
import sys
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx2

from nimbus.config import Settings
from nimbus.park_ingest import load_catalog, load_prepared
from nimbus.park_semantic import (
    BM25_FIELD,
    COLBERT_DIMENSIONS,
    COLBERT_MODEL,
    COLBERT_VECTOR,
    DENSE_VECTOR,
    PARK_DIMENSIONS,
    PARK_MODEL,
    PARK_PROFILE,
    PARK_SCHEMA,
    QdrantParkAPI,
    chunk_payload,
    manifest_id,
    manifest_payload,
    multivector_ready,
    point_id,
    vector_ready,
)
from nimbus.park_text import to_embedding_text
from tools.park_search_migration import read_dense_vectors

SETUP_SECONDS = 120
BATCH_SIZE = 1  # A single ColBERT record stays within the bounded JSON readback limit.
OWNER_ID = str(uuid5(NAMESPACE_URL, f"{PARK_PROFILE}/collection"))
OWNER = {"kind": "ownership", "schema": PARK_SCHEMA, "profile": PARK_PROFILE, "model": PARK_MODEL}
MARKER_VECTOR = [1.0, *([0.0] * (PARK_DIMENSIONS - 1))]
VECTOR_CONFIG: dict[str, Any] = {
    DENSE_VECTOR: {"size": PARK_DIMENSIONS, "distance": "Cosine"},
    COLBERT_VECTOR: {
        "size": COLBERT_DIMENSIONS,
        "distance": "Cosine",
        "multivector_config": {"comparator": "max_sim"},
        "hnsw_config": {"m": 0},
    },
}
KEYWORD_FIELDS = ("kind", "index_version", "model", "profile", "park_id", "destination_ids", "seasons")
TEXT_SCHEMA: dict[str, object] = {"type": "text", "tokenizer": "word", "lowercase": True, "scoring": True}


def make_setup_client() -> httpx2.AsyncClient:
    """Allow bounded hosted embedding work only during the explicit publisher, never app startup."""
    return httpx2.AsyncClient(timeout=30, follow_redirects=False, limits=httpx2.Limits(max_connections=2))


def _completed(document: dict[str, Any] | None) -> None:
    """A wait=true write must complete rather than merely acknowledge an asynchronous operation."""
    result = document.get("result") if document else None
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError("Park publication write was not confirmed")


def read_public_chunks(settings: Settings) -> tuple[str, list[dict[str, Any]]]:
    """Read tokenizer-prepared public text; no SQLite, local vectors or model weights are required."""
    prepared = load_prepared(settings.parks_prepared_path)
    catalog = load_catalog(settings.parks_index_path)
    if prepared["index_version"] != catalog["index_version"]:
        raise ValueError("Prepared park text and release catalog versions differ")
    return str(prepared["index_version"]), list(prepared["chunks"])


def _collection_result(document: dict[str, Any] | None) -> dict[str, Any]:
    """Check dense-vector compatibility without accepting malformed collection settings."""
    result = document.get("result") if document else None
    if not isinstance(result, dict):
        raise ValueError("Park collection is missing")
    config = result.get("config")
    params = config.get("params") if isinstance(config, dict) else None
    vectors = params.get("vectors") if isinstance(params, dict) else None
    if not isinstance(vectors, dict) or set(vectors) != {DENSE_VECTOR, COLBERT_VECTOR}:
        raise ValueError("Existing park collection has incompatible vector settings")
    for name, expected in VECTOR_CONFIG.items():
        actual = vectors[name]
        if not isinstance(actual, dict) or type(actual.get("size")) is not int:
            raise ValueError("Existing park collection has incompatible vector settings")
        for key, value in expected.items():
            observed = actual.get(key)
            matches = (
                isinstance(observed, dict) and all(observed.get(k) == v for k, v in value.items())
                if isinstance(value, dict)
                else observed == value
            )
            if not matches:
                raise ValueError("Existing park collection has incompatible vector settings")
    return result


def _index_ready(name: str, value: object) -> bool:
    """Require native scored text, not a filtering-only index mislabeled as BM25."""
    if not isinstance(value, dict):
        return False
    if name != BM25_FIELD:
        return value.get("data_type") == "keyword"
    params = value.get("params")
    scoring = params.get("scoring") if isinstance(params, dict) else None
    return (
        value.get("data_type") == "text"
        and isinstance(params, dict)
        and params.get("type") == "text"
        and params.get("tokenizer") == "word"
        and params.get("lowercase") is True
        and (scoring is True or scoring == {"type": "bm25"})
    )


async def _collection(api: QdrantParkAPI, http: httpx2.AsyncClient) -> None:
    """Create a dedicated owned collection; never repurpose incompatible data or the weather cache."""
    current = await api.request(http, "GET", "", missing_ok=True)
    if current is None:
        created = await api.request(http, "PUT", "", {"vectors": VECTOR_CONFIG})
        if not created or created.get("result") is not True:
            raise ValueError("Park collection creation was not confirmed")
        current = await api.request(http, "GET", "")
    result = _collection_result(current)
    owner = await api.request(http, "GET", f"/points/{OWNER_ID}", missing_ok=True)
    owner_result = owner.get("result") if owner else None
    if owner is not None:
        if (
            not isinstance(owner_result, dict)
            or owner_result.get("id") != OWNER_ID
            or owner_result.get("payload") != OWNER
        ):
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
                {"points": [{"id": OWNER_ID, "vector": {DENSE_VECTOR: MARKER_VECTOR}, "payload": OWNER}]},
            )
        )
    # ① Text is indexed by native BM25; this branch needs no second embedding model.
    indexes = result.get("payload_schema", {})
    if not isinstance(indexes, dict):
        raise ValueError("Invalid collection index settings")
    for name in (*KEYWORD_FIELDS, BM25_FIELD):
        if name in indexes:
            if not _index_ready(name, indexes[name]):
                raise ValueError("Existing collection has incompatible text or scope indexes")
            continue
        _completed(
            await api.request(
                http,
                "PUT",
                "/index?wait=true",
                {"field_name": name, "field_schema": TEXT_SCHEMA if name == BM25_FIELD else "keyword"},
            )
        )
    checked = _collection_result(await api.request(http, "GET", ""))
    indexes = checked.get("payload_schema", {})
    if not isinstance(indexes, dict) or any(
        not _index_ready(name, indexes.get(name)) for name in (*KEYWORD_FIELDS, BM25_FIELD)
    ):
        raise ValueError("Park keyword indexes were not verified")


async def _existing_batch(
    api: QdrantParkAPI, http: httpx2.AsyncClient, batch: list[dict[str, Any]], version: str
) -> set[str]:
    """Verify existing immutable records before reusing them; never silently overwrite corrupt records."""
    expected = {point_id(version, chunk["id"]): chunk_payload(chunk, version) for chunk in batch}
    document = await api.request(
        http, "POST", "/points", {"ids": list(expected), "with_payload": True, "with_vector": True}
    )
    points = document.get("result") if document else None
    if not isinstance(points, list) or len(points) > len(expected):
        raise ValueError("Invalid park publication verification")
    seen: set[str] = set()
    for item in points:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or item["id"] not in expected
            or item["id"] in seen
            or item.get("payload") != expected[item["id"]]
            or not isinstance(item.get("vector"), dict)
            or set(item["vector"]) != {DENSE_VECTOR, COLBERT_VECTOR}
            or not vector_ready(item["vector"].get(DENSE_VECTOR))
            or not multivector_ready(item["vector"].get(COLBERT_VECTOR))
        ):
            raise ValueError("Park publication did not match the prepared corpus")
        seen.add(item["id"])
    return seen


async def _verify_batch(
    api: QdrantParkAPI, http: httpx2.AsyncClient, batch: list[dict[str, Any]], version: str
) -> None:
    """Require all source records and hosted vectors before publishing the generation marker."""
    present = await _existing_batch(api, http, batch, version)
    if present != {point_id(version, chunk["id"]) for chunk in batch}:
        raise ValueError("Park publication is incomplete")


async def setup(
    settings: Settings,
    factory: Callable[[], httpx2.AsyncClient] = make_setup_client,
    *,
    reuse_collection: str | None = None,
) -> tuple[str, int]:
    """Publish approved records once; repeat runs verify and reuse embeddings instead of generating them again."""
    api = QdrantParkAPI(settings)
    if not api.configured:
        raise ValueError("Configure a dedicated park collection and an authorized Qdrant credential")
    version, chunks = read_public_chunks(settings)
    async with asyncio.timeout(SETUP_SECONDS), factory() as http:
        reused = await read_dense_vectors(settings, http, reuse_collection, version, chunks) if reuse_collection else {}
        await _collection(api, http)
        document = await api.request(http, "GET", f"/points/{manifest_id(version)}", missing_ok=True)
        marker = manifest_payload(version, len(chunks))
        if document is not None:
            existing = document.get("result")
            if (
                not isinstance(existing, dict)
                or existing.get("id") != manifest_id(version)
                or existing.get("payload") != marker
            ):
                raise ValueError("Existing park readiness marker does not match")
        # Reuse verified dense vectors when migrating; generate only missing representations.
        for offset in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[offset : offset + BATCH_SIZE]
            present = await _existing_batch(api, http, batch, version)
            missing = [chunk for chunk in batch if point_id(version, chunk["id"]) not in present]
            if document is not None and missing:
                raise ValueError("A published park generation is incomplete")
            if missing:
                points = [
                    {
                        "id": point_id(version, chunk["id"]),
                        "vector": {
                            DENSE_VECTOR: reused.get(
                                chunk["id"],
                                {
                                    "text": to_embedding_text(chunk["title"], chunk["section"], chunk["text"]),
                                    "model": PARK_MODEL,
                                },
                            ),
                            COLBERT_VECTOR: {
                                "text": to_embedding_text(chunk["title"], chunk["section"], chunk["text"]),
                                "model": COLBERT_MODEL,
                            },
                        },
                        "payload": chunk_payload(chunk, version),
                    }
                    for chunk in missing
                ]
                _completed(await api.request(http, "PUT", "/points?wait=true", {"points": points}))
            await _verify_batch(api, http, batch, version)
        # ③ Counts and native BM25 queryability are verified before readiness is written, without dense re-embedding.
        conditions = [
            {"key": "kind", "match": {"value": "chunk"}},
            {"key": "index_version", "match": {"value": version}},
            {"key": "profile", "match": {"value": PARK_PROFILE}},
        ]
        count = await api.request(http, "POST", "/points/count", {"exact": True, "filter": {"must": conditions}})
        counted = count.get("result") if count else None
        if not isinstance(counted, dict) or type(counted.get("count")) is not int or counted["count"] != len(chunks):
            raise ValueError("Park publication count did not match")
        query = await api.request(
            http,
            "POST",
            "/points/query",
            {
                "query": {"text": chunk_payload(chunks[0], version)[BM25_FIELD][:1000]},
                "using": BM25_FIELD,
                "filter": {"must": conditions},
                "params": {"idf": {"corpus": {"must": conditions}}},
                "limit": 1,
                "with_payload": False,
                "with_vector": False,
            },
        )
        queried = query.get("result") if query else None
        if not isinstance(queried, dict) or not isinstance(queried.get("points"), list) or not queried["points"]:
            raise ValueError("Park BM25 index was not queryable")
        if document is None:
            _completed(
                await api.request(
                    http,
                    "PUT",
                    "/points?wait=true",
                    {
                        "points": [
                            {"id": manifest_id(version), "vector": {DENSE_VECTOR: MARKER_VECTOR}, "payload": marker}
                        ]
                    },
                )
            )
        verified = await api.request(http, "GET", f"/points/{manifest_id(version)}")
        result = verified.get("result") if verified else None
        if not isinstance(result, dict) or result.get("id") != manifest_id(version) or result.get("payload") != marker:
            raise ValueError("Park readiness marker was not verified")
    return version, len(chunks)


def main() -> int:
    """Publish an explicitly selected collection, reporting only version/count and sanitized failure classes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", help="Dedicated park collection; must differ from the weather cache")
    parser.add_argument("--reuse-collection", help="Read-only v2 source for reusing verified MiniLM vectors")
    args = parser.parse_args()
    try:
        settings = Settings(**({"parks_qdrant_collection": args.collection} if args.collection else {}))
        version, count = asyncio.run(setup(settings, reuse_collection=args.reuse_collection))
    except Exception as error:
        print(f"Park search setup failed ({type(error).__name__}); check the corpus, credentials and collection.")
        return 1
    print(f"Verified hosted park index {version}: {count} public chunks, native BM25, MiniLM and ColBERT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
