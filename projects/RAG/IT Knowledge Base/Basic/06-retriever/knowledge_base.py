"""
IT Knowledge Base: Documents and Metadata
=========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article, with the text kept apart from the
labels. It handles:
  1. Putting the title, problem, resolution and notes into the Document's text (page_content)
  2. Putting the article's number, title, system, category, priority and tags into its labels (metadata)
  3. Printing which columns went where, and every Document

Usage (this file only defines these; pipeline.py runs the steps):
    docs = load_documents()   ->  10 Documents: the text in page_content, the labels in metadata
    print_documents(docs)     ->  which columns went where, then every Document in full
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# Found next to this script, whichever folder it's run from
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# The text is what gets searched and read; the labels are shown with an answer. The title is in both.
TEXT_COLUMNS = ["title", "problem", "resolution", "notes"]
METADATA_COLUMNS = ["title", "system", "category", "priority", "tags"]


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores which file to read, and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, path: Path = KB_FILE):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        """Yield one Document per row: "Title: ..." blocks as the text, and the labels as metadata."""
        with open(self.path, encoding="utf-8", newline="") as file:
            for number, row in enumerate(csv.DictReader(file)):
                # Each part keeps its label, so the model can tell the symptom from the fix
                text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
                metadata = {"doc_id": str(number), **{column: row[column] for column in METADATA_COLUMNS}}
                yield Document(page_content=text, metadata=metadata)


def load_documents(path: Path = KB_FILE) -> list[Document]:
    """Every article, as a list of Documents."""
    return KBLoader(path).load()


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
