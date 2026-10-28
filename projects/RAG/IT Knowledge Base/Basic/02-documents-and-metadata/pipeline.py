"""
IT Knowledge Base: Documents and Metadata
=========================================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, one per article,
with the text kept apart from the labels, and runs the step. It handles:
  1. Putting the title, problem, resolution and notes into the Document's text (page_content)
  2. Putting the article's number, title, system, category, priority and tags into its labels (metadata)
  3. Running the step: main() names it, runs it, then prints the Documents with utils.py's print_documents()

Usage:
    python pipeline.py
"""
import csv
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from utils import print_documents

# Found next to this script, whichever folder it's run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
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
            # DictReader comes from Python's csv module: each row as {column: value}, named by the header row
            for number, row in enumerate(csv.DictReader(file)):
                # Each part keeps its label, so the model can tell the symptom from the fix
                text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in TEXT_COLUMNS)
                metadata = {"doc_id": str(number), **{column: row[column] for column in METADATA_COLUMNS}}
                # Document comes from langchain_core: LangChain's text (page_content) with its labels (metadata)
                yield Document(page_content=text, metadata=metadata)


def load_documents(path: Path = KB_FILE) -> list[Document]:
    """Every article, as a list of Documents."""
    # load() comes from LangChain's BaseLoader, which KBLoader extends: lazy_load()'s Documents, in a list
    return KBLoader(path).load()


def main() -> None:
    """Run every step in order, each one after its name."""
    print("Step 1: Read the knowledge base")
    docs = load_documents()
    print_documents(docs, TEXT_COLUMNS, METADATA_COLUMNS)


if __name__ == "__main__":
    main()
