"""
IT Knowledge Base: Utilities
============================

Helpers the pipeline uses that aren't a step of their own. It handles:
  1. Printing a search: the question, the chunks the retriever found, closest first, and a sample of what a prompt
     gets

Usage (pipeline.py calls it; this file only defines it):
    print_retrieval(question, chunks, format_docs(chunks[:2]))
        ->  the question and the chunks found, then the prompt's text: the first 2 chunks, as format_docs() joins them
"""
from langchain_core.documents import Document


def print_retrieval(question: str, chunks: list[Document], sample: str) -> None:
    """Print the question, the chunks the retriever found, closest first, and a sample of the prompt: `sample`, the
    first 2 chunks as format_docs() joins them."""
    print(f"Question: {question}")
    print(f"\nThe {len(chunks)} closest chunks the retriever found, closest first:")
    for chunk in chunks:
        print(f"  {chunk.metadata['title']}, from character {chunk.metadata['start_index']}")
    print(f"\nA sample of what a prompt gets: the first 2 of the {len(chunks)} chunks, as one text (format_docs):")
    print(sample)
