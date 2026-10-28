"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing how many chunks each article makes, then every chunk

Usage (pipeline.py calls it; this file only defines it):
    print_chunks(docs, chunks, chunk_size)   ->  how many chunks each article makes, then every article's chunks
"""
from langchain_core.documents import Document


def print_chunks(docs: list[Document], chunks: list[Document], chunk_size: int) -> None:
    """Print how many chunks each article makes, then every article's chunks: where each starts, and its text."""
    print(f"{len(docs)} articles -> {len(chunks)} chunks of at most {chunk_size} characters")
    for doc in docs:
        count = sum(chunk.metadata["doc_id"] == doc.metadata["doc_id"] for chunk in chunks)
        print(f"  {count} from {doc.metadata['title']} ({len(doc.page_content)} characters)")
    for number, doc in enumerate(docs):
        mine = [chunk for chunk in chunks if chunk.metadata["doc_id"] == doc.metadata["doc_id"]]
        print()
        print(f"Article {number + 1} of {len(docs)}: {doc.metadata['title']}, "
              f"cut into {len(mine)} chunk{'s' if len(mine) > 1 else ''}")
        for place, chunk in enumerate(mine, 1):
            print()
            print(f"Chunk {place} of {len(mine)}, from character {chunk.metadata['start_index']} "
                  f"({len(chunk.page_content)} characters):")
            print(chunk.page_content)
