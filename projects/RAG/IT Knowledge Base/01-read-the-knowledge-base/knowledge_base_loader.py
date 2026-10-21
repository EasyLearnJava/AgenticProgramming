"""
IT Knowledge Base, Step 1: Read the Knowledge Base
==================================================

This module reads the IT knowledge base, a CSV file of 10 IT support articles, into LangChain Documents: one
Document per article. It handles:
  1. Checking that the CSV file exists and has a header row
  2. Turning each row into a Document: its text (page_content) and where it came from (metadata)
  3. Logging what it read, and printing every Document

Architecture:
    data/sample_it_kb.csv  ->  KBLoader(data_path)  ->  load()  ->  10 Documents

No model, no API key: it only reads a file.

Usage:
    python knowledge_base_loader.py                            # reads data/sample_it_kb.csv
    python knowledge_base_loader.py --data-path other.csv      # reads another CSV file with a header row
    python knowledge_base_loader.py --log-level DEBUG          # also logs each row as it's read
"""
import argparse
import csv
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

# One logger per module, named after it. Where its messages go and which levels show is set once, in main(): a module
# that is imported (as the tests import this one) leaves that choice to whoever imports it.
logger = logging.getLogger(__name__)


# -------------------------------------------------
# Configuration
# -------------------------------------------------

# The knowledge base file. Path(__file__).resolve().parent is the folder this script is in, and `/` on a Path adds a
# name to it. A bare "data/sample_it_kb.csv" would be looked for in whatever folder you run the script from.
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"

# Each log line: when, how serious, what happened. For example:
#     2026-10-20 14:03:12,345 INFO Read 10 documents from sample_it_kb.csv
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


# -------------------------------------------------
# KBLoader Class - Reads the Knowledge Base
# -------------------------------------------------

class KBLoader(BaseLoader):
    """
    A LangChain document loader for the IT knowledge base CSV file.

    Step 1: Configure: the constructor only stores which file to read and how; it reads nothing
    Step 2: Load: lazy_load() opens the file and turns each row into a Document

    BaseLoader gives every LangChain loader the same methods: we write lazy_load(), which hands out the Documents one
    at a time, and BaseLoader's load() collects them into a list.
    """

    def __init__(self, data_path: str | Path, encoding: str = "utf-8"):
        """
        Store the loader's configuration. Nothing is opened or read here: load() and lazy_load() do that.

        Args:
            data_path: the CSV file to read; its first line must name the columns
            encoding: the file's text encoding
        """
        self.data_path = Path(data_path)
        self.encoding = encoding

    def lazy_load(self) -> Iterator[Document]:
        """
        Read the CSV file and hand out one Document per row, in the file's order.

        Yields:
            a Document per row: page_content has one "column: value" line per column; metadata has the file's name
            and the row number, counted from 0

        Raises:
            FileNotFoundError: there's no file at data_path
            ValueError: the file is empty, so it has no header row; or it isn't text in `encoding`
        """
        # Step 2a: Check that the file is there, so a wrong path fails with a message that names it. The messages give
        #          the full path: a relative one is looked for from the folder you're in, and this shows which that was.
        path = self.data_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Knowledge base file not found: {path}")

        # Step 2b: Open it. newline="" is how the csv module wants a file opened. DictReader takes the column names
        #          from the first line, then gives each line after it as a dict, {"title": ..., ...}, skipping empty
        #          lines. Logger calls take their values as arguments (%s, %d): the message is only built if it's shown.
        count = 0
        try:
            with open(path, encoding=self.encoding, newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames is None:
                    raise ValueError(f"Knowledge base file is empty, with no header row: {path}")
                logger.info("Reading %s (%s): %d columns (%s)", path, self.encoding, len(reader.fieldnames),
                            ", ".join(reader.fieldnames))

                # Step 2c: One Document per row. DEBUG logs each one; the default level, INFO, leaves those lines out.
                for number, row in enumerate(reader):
                    doc = self._row_to_document(row, number)
                    logger.debug("Row %d: %s", number, doc.page_content.splitlines()[0])
                    count += 1
                    yield doc
        except UnicodeDecodeError as err:
            # A common Windows surprise: PowerShell 5's `>` saves a file as UTF-16, which can't be read as UTF-8.
            raise ValueError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                             "Save it as UTF-8, or give KBLoader its encoding.") from None

        # Step 2d: The total. A header with no rows under it isn't an error, but it's worth a warning.
        if count == 0:
            logger.warning("%s has a header row but no articles", self.data_path.name)
        else:
            logger.info("Read %d documents from %s", count, self.data_path.name)

    def _row_to_document(self, row: dict[str, str], number: int) -> Document:
        """
        Turn one row of the CSV file into a Document.

        Args:
            row: the row, as {column: value}
            number: the row's place in the file, counted from 0 (the header line isn't counted)

        Returns:
            a Document whose page_content has one "column: value" line per column, and whose metadata says where it
            came from: {"source": the file's name, "row": number}
        """
        text = "\n".join(f"{column}: {value}" for column, value in row.items())
        return Document(page_content=text, metadata={"source": self.data_path.name, "row": number})


# -------------------------------------------------
# Output - What Was Read
# -------------------------------------------------

def print_documents(docs: list[Document]) -> None:
    """
    Print how many Documents were read and each one's row and title, then every Document in full: a heading, its
    text, then its metadata, each with a note saying what it is, and one blank line between Documents.

    This is the program's output, so it goes to stdout with print(). What the program is doing, and anything that
    goes wrong, goes to the log, on stderr.
    """
    print(f"{len(docs)} documents")
    for doc in docs:
        print(f"row {doc.metadata['row']}  {doc.page_content.splitlines()[0]}")   # the first line: the title

    for number, doc in enumerate(docs, 1):
        print()                                       # a blank line before each document
        print(f"Document {number} of {len(docs)}")
        print("Text (page_content):")
        print(doc.page_content)
        print()
        print("Where it came from (metadata):")
        print(doc.metadata)


# -------------------------------------------------
# Entry Point
# -------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """
    Read the command-line options. Each has a default, so `python knowledge_base_loader.py` alone reads the sample file.

    Args:
        argv: the options to read; None means the ones the script was started with (sys.argv)
    """
    parser = argparse.ArgumentParser(
        description="Read the IT knowledge base CSV file into LangChain Documents and print them.")
    parser.add_argument("--data-path", type=Path, default=KB_FILE,
                        help="the CSV file to read (default: data/sample_it_kb.csv, next to this script)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="the least serious log messages to show; DEBUG adds one line per row (default: INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """
    Run step 1: read the knowledge base, then print every Document.

    Args:
        argv: the command-line options; None means the ones the script was started with

    Returns:
        the exit code: 0 when the file was read, 1 when it couldn't be (the log says why)
    """
    args = parse_args(argv)

    # Step 3a: Set up logging, once, here in the entry point. Log lines go to stderr, apart from the printed output.
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)

    # Step 3b: Configure the loader, then load. Making it reads nothing; load() is the line that reads the file.
    #          A file that's missing or empty stops the program with one log line and exit code 1, not a traceback.
    loader = KBLoader(args.data_path)
    try:
        docs = loader.load()
    except (FileNotFoundError, ValueError) as err:
        logger.error("%s", err)
        return 1

    # Step 3c: Print what was read.
    print_documents(docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
