"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing which columns went where, and every Document

Usage (pipeline.py calls it; this file only defines it):
    print_documents(docs)   ->  which columns went where, then every Document in full
"""
from langchain_core.documents import Document

from knowledge_base import METADATA_COLUMNS, TEXT_COLUMNS


def print_documents(docs: list[Document]) -> None:
    """Print which columns went where, then every Document in full: its text, then its labels."""
    print(f"{len(docs)} documents")
    print("text:     " + ", ".join(TEXT_COLUMNS))
    print("metadata: " + ", ".join(["doc_id", *METADATA_COLUMNS]))
    print()
    for number, doc in enumerate(docs):
        if number > 0:
            print()
        print(f"Document {number + 1} of {len(docs)}")
        print("Text (page_content):")
        print(doc.page_content)
        print()
        print("Labels (metadata):")
        print(doc.metadata)
