"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing Documents: the count and each title, then every Document in full

Usage (pipeline.py calls it; this file only defines it):
    print_documents(docs)   ->  the count and each title, then every Document in full
"""
from langchain_core.documents import Document


def print_documents(docs: list[Document]) -> None:
    """Print the count and each title, then every Document in full."""
    print(f"{len(docs)} documents")
    for doc in docs:
        print(f"row {doc.metadata['row']}  {doc.page_content.splitlines()[0]}")

    for number, doc in enumerate(docs, 1):
        print()
        print(f"Document {number} of {len(docs)}")
        print("Text (page_content):")
        print(doc.page_content)
        print()
        print("Where it came from (metadata):")
        print(doc.metadata)
