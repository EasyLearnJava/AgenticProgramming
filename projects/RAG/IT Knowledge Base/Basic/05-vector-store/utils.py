"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing the collection, then every point stored in it

Usage (pipeline.py calls it; this file only defines it):
    print_points(store)   ->  the collection, then every point stored in it
"""
from langchain_qdrant import QdrantVectorStore


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
