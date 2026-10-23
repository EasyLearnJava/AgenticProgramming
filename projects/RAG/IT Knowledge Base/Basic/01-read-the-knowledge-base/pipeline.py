"""
IT Knowledge Base: The Pipeline
===============================

The one file to run: it calls this project's steps in order, and the other files only define them. It handles:
  1. Step 1: reading the knowledge base CSV file into Documents, then printing them

Usage:
    python pipeline.py
"""
from knowledge_base import load_documents
from utils import print_documents


def main() -> None:
    """Run every step in order, each one after its name."""
    print("Step 1: Read the knowledge base")
    docs = load_documents()
    print_documents(docs)


if __name__ == "__main__":
    main()
