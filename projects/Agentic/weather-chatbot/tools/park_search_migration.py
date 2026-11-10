"""Read-only reuse of verified v2 MiniLM vectors when explicitly publishing a separate v3 collection."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx2

from nimbus.config import Settings
from nimbus.park_semantic import BM25_FIELD, PARK_DIMENSIONS, PARK_MODEL, QdrantParkAPI, chunk_payload, vector_ready

LEGACY_PROFILE = "nimbus-park-hybrid-text-v2"


def legacy_id(version: str, kind: str, identity: str = "") -> str:
    """Use the immutable v2 identifiers without changing the new runtime's publication profile."""
    suffix = f"/{identity}" if identity else ""
    return str(uuid5(NAMESPACE_URL, f"{LEGACY_PROFILE}/{version}/{kind}{suffix}"))


async def read_dense_vectors(
    settings: Settings,
    http: httpx2.AsyncClient,
    collection: str,
    version: str,
    chunks: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Copy approved public vectors only; never infer, write, delete or repair the source collection."""
    source = settings.model_copy(update={"parks_qdrant_collection": collection})
    api = QdrantParkAPI(source)
    if not api.configured or collection == settings.parks_qdrant_collection:
        raise ValueError("Reuse requires a separate, valid public park collection")
    document = await api.request(http, "GET", "")
    result = document.get("result") if document else None
    config = result.get("config") if isinstance(result, dict) else None
    params = config.get("params") if isinstance(config, dict) else None
    vectors = params.get("vectors") if isinstance(params, dict) else None
    if (
        not isinstance(vectors, dict)
        or type(vectors.get("size")) is not int
        or vectors.get("size") != PARK_DIMENSIONS
        or vectors.get("distance") != "Cosine"
    ):
        raise ValueError("Reuse collection has incompatible dense vectors")
    owner_id = str(uuid5(NAMESPACE_URL, f"{LEGACY_PROFILE}/collection"))
    manifest = {
        "kind": "manifest",
        "schema": 2,
        "index_version": version,
        "model": PARK_MODEL,
        "profile": LEGACY_PROFILE,
        "chunk_count": len(chunks),
        "bm25_field": BM25_FIELD,
    }
    owner = {"kind": "ownership", "schema": 2, "profile": LEGACY_PROFILE, "model": PARK_MODEL}
    for identity, expected in ((owner_id, owner), (legacy_id(version, "manifest"), manifest)):
        document = await api.request(http, "GET", f"/points/{identity}")
        result = document.get("result") if document else None
        if not isinstance(result, dict) or result.get("id") != identity or result.get("payload") != expected:
            raise ValueError("Reuse collection ownership or publication does not match")
    copied: dict[str, list[float]] = {}
    for offset in range(0, len(chunks), 16):
        batch = chunks[offset : offset + 16]
        expected_chunks = {legacy_id(version, "chunk", chunk["id"]): chunk for chunk in batch}
        document = await api.request(
            http, "POST", "/points", {"ids": list(expected_chunks), "with_payload": True, "with_vector": True}
        )
        points = document.get("result") if document else None
        if not isinstance(points, list) or len(points) != len(batch):
            raise ValueError("Reuse collection is incomplete")
        seen: set[str] = set()
        for point in points:
            if not isinstance(point, dict) or not isinstance(point.get("id"), str):
                raise ValueError("Invalid reuse record")
            chunk = expected_chunks.get(point["id"])
            if chunk is None or point["id"] in seen:
                raise ValueError("Unapproved reuse record")
            payload = {**chunk_payload(chunk, version), "schema": 2, "profile": LEGACY_PROFILE}
            if point.get("payload") != payload or not vector_ready(point.get("vector")):
                raise ValueError("Reuse record text, metadata or dense vector differs")
            copied[chunk["id"]] = point["vector"]
            seen.add(point["id"])
    return copied
