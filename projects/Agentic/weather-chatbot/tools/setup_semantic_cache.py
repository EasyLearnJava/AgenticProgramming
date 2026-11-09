"""Create/verify the dedicated cache collection and filter indexes; never replace an existing collection."""

import argparse
import asyncio
import sys
from typing import Any

import httpx2

from nimbus.config import Settings


async def setup(settings: Settings) -> None:
    """Require an operator credential; serving chat never needs collection-management permission."""
    if not settings.qdrant_url or settings.qdrant_api_key is None:
        raise ValueError("Set QDRANT_URL and QDRANT_API_KEY in .env.local")
    headers = {"api-key": settings.qdrant_api_key.get_secret_value()}
    url = f"{settings.qdrant_url}/collections/{settings.qdrant_collection}"
    async with asyncio.timeout(45), httpx2.AsyncClient(timeout=15, follow_redirects=False, headers=headers) as client:
        response = await client.get(url)
        if response.status_code == 404:
            response = await client.put(url, json={"vectors": {"size": 384, "distance": "Cosine"}})
            response.raise_for_status()
            response = await client.get(url)
        response.raise_for_status()
        document: dict[str, Any] = response.json()
        vectors = document["result"]["config"]["params"]["vectors"]
        if vectors.get("size") != 384 or vectors.get("distance") != "Cosine":
            raise ValueError("Existing collection is incompatible; use a new dedicated cache collection")
        response = await client.patch(
            url,
            json={
                "strict_mode_config": {
                    "enabled": True,
                    "max_points_count": 2000,
                    "max_collection_payload_size_bytes": 120_000_000,
                }
            },
        )
        response.raise_for_status()
        for field in ("scope", "context", "guard", "version", "exact", "expires_at"):
            response = await client.put(
                url + "/index?wait=true",
                json={
                    "field_name": field,
                    "field_schema": "float" if field == "expires_at" else "keyword",
                },
            )
            response.raise_for_status()


def main() -> int:
    """Print only safe setup outcomes; HTTP exceptions may contain sensitive provider response text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", help="An explicit dedicated collection (for isolated live evaluations)")
    args = parser.parse_args()
    settings = Settings(**({"qdrant_collection": args.collection} if args.collection else {}))
    try:
        asyncio.run(setup(settings))
    except Exception as error:
        print(f"Cache setup failed ({type(error).__name__}); check endpoint, permissions and availability.")
        return 1
    print(f"Verified {settings.qdrant_collection}: 384 dimensions, Cosine distance, six payload indexes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
