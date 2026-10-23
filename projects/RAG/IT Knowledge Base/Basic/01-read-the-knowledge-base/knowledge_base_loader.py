"""
IT Knowledge Base: Read the Knowledge Base
==========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article. It handles:
  1. Reading the CSV file, one row at a time
  2. Turning each row into a Document (page_content + metadata)

Usage (pipeline.py runs this; this file only defines it):
    docs = KBLoader(KB_FILE).load()   ->  10 Documents, one per article
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# Found next to this script, whichever folder it's run from
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores which file to read, and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, data_path: str | Path):
        self.data_path = Path(data_path)

    def lazy_load(self) -> Iterator[Document]:
        """Yield one Document per row: one "column: value" line per column, and the file and row as metadata."""
        with open(self.data_path, encoding="utf-8", newline="") as file:
            for number, row in enumerate(csv.DictReader(file)):
                text = "\n".join(f"{column}: {value}" for column, value in row.items())
                yield Document(page_content=text, metadata={"source": self.data_path.name, "row": number})
