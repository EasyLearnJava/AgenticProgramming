"""
IT Knowledge Base: Read the Knowledge Base
==========================================

The whole project in one file: it reads the IT knowledge base CSV file into LangChain Documents, one per article,
and prints them. It handles:
  1. Reading the CSV file, one row at a time
  2. Turning each row into a Document (page_content + metadata)
  3. Printing the count and each title, then every Document in full
  4. Running the step: main() names it, then runs it

Usage:
    python pipeline.py
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# Found next to this script, whichever folder it's run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores which file to read, and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, path: Path = KB_FILE):
        self.path = path

    def lazy_load(self) -> Iterator[Document]:
        """Yield one Document per row: one "column: value" line per column, and the file and row as metadata."""
        with open(self.path, encoding="utf-8", newline="") as file:
            # DictReader comes from Python's csv module: each row as {column: value}, named by the header row
            for number, row in enumerate(csv.DictReader(file)):
                text = "\n".join(f"{column}: {value}" for column, value in row.items())
                # Document comes from langchain_core: LangChain's text (page_content) with its labels (metadata)
                yield Document(page_content=text, metadata={"source": self.path.name, "row": number})


def load_documents(path: Path = KB_FILE) -> list[Document]:
    """Every article, as a list of Documents."""
    # load() comes from LangChain's BaseLoader, which KBLoader extends: lazy_load()'s Documents, in a list
    return KBLoader(path).load()


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


def main() -> None:
    """Run every step in order, each one after its name."""
    print("Step 1: Read the knowledge base")
    docs = load_documents()
    print_documents(docs)


if __name__ == "__main__":
    main()
