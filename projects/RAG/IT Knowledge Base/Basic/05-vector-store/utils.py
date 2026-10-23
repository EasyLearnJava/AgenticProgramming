"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Connecting: the Qdrant server at an address, checked to be there, or Qdrant in memory
  2. Printing the collection, then every point stored in it

Usage (pipeline.py calls them; this file only defines them):
    client = connect(QDRANT_URL)   ->  the server, checked to be there; Qdrant in memory with no address
    print_points(store)            ->  the collection, then every point stored in it
"""
import sys

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException


def connect(qdrant_url: str) -> QdrantClient:
    """The Qdrant server at qdrant_url, checked to be there; or Qdrant in memory when there's no address."""
    if not qdrant_url:
        print("Qdrant: in memory, inside this script")
        return QdrantClient(":memory:")
    # check_compatibility=False skips qdrant-client's background version check, which only warns.
    client = QdrantClient(url=qdrant_url, check_compatibility=False)
    try:
        client.get_collections()                   # a first request, before any call to Gemini: is it there?
    except ResponseHandlingException:
        sys.exit(f"Can't reach Qdrant at {qdrant_url}. Start it first, in this folder: docker compose up -d "
                 "(or remove QDRANT_URL from .env to run Qdrant in memory).")
    print(f"Qdrant: the server at {qdrant_url}")
    return client


def print_points(store: QdrantVectorStore) -> None:
    """Print the collection's settings, then every point stored in it, in article and place order."""
    collection = store.collection_name
    params = store.client.get_collection(collection).config.params.vectors
    # scroll() returns points in id order, so they're sorted back into article and place order
    points, _ = store.client.scroll(collection, limit=100, with_vectors=True)
    points.sort(key=lambda point: (int(point.payload["metadata"]["doc_id"]), point.payload["metadata"]["start_index"]))
    print(f"Collection {collection!r}: {len(points)} points, vectors of {params.size} numbers, "
          f"compared by {params.distance.value}")
    print(f"Each point holds an id, a vector and a payload with {', '.join(sorted(points[0].payload))}")
    print()
    for number, point in enumerate(points, 1):
        metadata = point.payload["metadata"]
        print(f"Point {number} of {len(points)}: {metadata['title']}, from character {metadata['start_index']}: "
              f"{len(point.vector)} numbers, {len(point.payload['page_content'])} characters of text, "
              f"{len(metadata)} labels")
