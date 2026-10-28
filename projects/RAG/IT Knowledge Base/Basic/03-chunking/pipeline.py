"""
IT Knowledge Base: Chunking
===========================

The project's code in one file: it reads the IT knowledge base CSV file into LangChain Documents, one per article,
then cuts them into smaller pieces, chunks, so a search can find the part of an article that matches. It handles:
  1. Reading each article into a Document: its text in page_content, its labels in metadata
  2. Splitting each Document into chunks of at most CHUNK_SIZE characters, with CHUNK_OVERLAP between neighbours
  3. Keeping each chunk's article labels, plus start_index: where in the article's text it starts
  4. Running the steps: main() names them, runs them, then prints the chunks with utils.py's print_chunks()

Usage:
    python pipeline.py        # chunks of at most 512 characters
    python pipeline.py 200    # chunks of at most 200 characters
"""
import csv
import sys
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from utils import print_chunks

# Found next to this script, whichever folder it's run from
# Path comes from Python's pathlib: resolve() gives this file's full path, and .parent its folder
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# The text is what gets searched and read; the labels are shown with an answer. The title is in both.
TEXT_COLUMNS = ["title", "problem", "resolution", "notes"]
METADATA_COLUMNS = ["title", "system", "category", "priority", "tags"]

# In characters: the articles are 569 to 716 characters long, so 512 makes 2 or 3 chunks each (28 in all)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


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


def make_splitter(chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> RecursiveCharacterTextSplitter:
    """A splitter that breaks at empty lines first, then line breaks, then spaces; it records start_index."""
    # RecursiveCharacterTextSplitter comes from langchain_text_splitters: LangChain's splitter by size
    return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, add_start_index=True)


def split_documents(docs: list[Document], chunk_size: int = CHUNK_SIZE,
                    chunk_overlap: int = CHUNK_OVERLAP) -> list[Document]:
    """Every Document cut into chunks, each a new Document with a copy of its article's metadata."""
    return make_splitter(chunk_size, chunk_overlap).split_documents(docs)


def main(chunk_size: int = CHUNK_SIZE) -> None:
    """Run every step in order: the earlier ones in one line each, this project's step in full."""
    docs = load_documents()
    print(f"Step 1: Read the knowledge base: {len(docs)} documents")
    print("Step 2: Chunk")
    chunks = split_documents(docs, chunk_size=chunk_size)
    print_chunks(docs, chunks, chunk_size)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else CHUNK_SIZE)
