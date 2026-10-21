"""
IT Knowledge Base: Read the Knowledge Base
==========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article. It handles:
  1. Checking that the file exists and has a header row
  2. Turning each row into a Document (page_content + metadata)
  3. Logging what it read, and printing every Document

Usage:
    python knowledge_base_loader.py                          # reads data/sample_it_kb.csv
    python knowledge_base_loader.py --data-path other.csv    # reads another CSV file
    python knowledge_base_loader.py --log-level DEBUG        # also logs each row
"""
import argparse
import csv
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Configuration
# -------------------------------------------------

# Found next to this script, whichever folder it's run from
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


# -------------------------------------------------
# KBLoader Class - Reads the Knowledge Base
# -------------------------------------------------

class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores the settings and reads nothing
    Step 2: Load: lazy_load() reads the file, one Document per row (load() collects them into a list)
    """

    def __init__(self, data_path: str | Path, encoding: str = "utf-8"):
        """
        Args:
            data_path: the CSV file to read; its first line must name the columns
            encoding: the file's text encoding
        """
        self.data_path = Path(data_path)
        self.encoding = encoding

    def lazy_load(self) -> Iterator[Document]:
        """
        Yield one Document per row, in the file's order.

        Raises:
            FileNotFoundError: there's no file at data_path
            ValueError: the file is empty, or isn't text in `encoding`
        """
        # Step 2a: Check the file exists (full path, so a relative path shows where it was looked for)
        path = self.data_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Knowledge base file not found: {path}")

        # Step 2b: Open it and read the header row
        count = 0
        try:
            with open(path, encoding=self.encoding, newline="") as file:
                reader = csv.DictReader(file)
                if reader.fieldnames is None:
                    raise ValueError(f"Knowledge base file is empty, with no header row: {path}")
                logger.info("Reading %s (%s): %d columns (%s)", path, self.encoding, len(reader.fieldnames),
                            ", ".join(reader.fieldnames))

                # Step 2c: One Document per row
                for number, row in enumerate(reader):
                    doc = self._row_to_document(row, number)
                    logger.debug("Row %d: %s", number, doc.page_content.splitlines()[0])
                    count += 1
                    yield doc
        except UnicodeDecodeError as err:
            # Often a file saved as UTF-16 by PowerShell 5's `>`
            raise ValueError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                             "Save it as UTF-8, or give KBLoader its encoding.") from None

        # Step 2d: Log the total
        if count == 0:
            logger.warning("%s has a header row but no articles", self.data_path.name)
        else:
            logger.info("Read %d documents from %s", count, self.data_path.name)

    def _row_to_document(self, row: dict[str, str], number: int) -> Document:
        """Turn one row into a Document: one "column: value" line per column, and the file and row as metadata."""
        text = "\n".join(f"{column}: {value}" for column, value in row.items())
        return Document(page_content=text, metadata={"source": self.data_path.name, "row": number})


# -------------------------------------------------
# Output - What Was Read
# -------------------------------------------------

def print_documents(docs: list[Document]) -> None:
    """Print the count and each title, then every Document in full. Output goes to stdout; the log to stderr."""
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


# -------------------------------------------------
# Entry Point
# -------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Read the command-line options; with none, the sample file is read."""
    parser = argparse.ArgumentParser(
        description="Read the IT knowledge base CSV file into LangChain Documents and print them.")
    parser.add_argument("--data-path", type=Path, default=KB_FILE,
                        help="the CSV file to read (default: data/sample_it_kb.csv, next to this script)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="the least serious log messages to show; DEBUG adds one line per row (default: INFO)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Read the knowledge base and print every Document. Returns the exit code: 0 if read, 1 if not."""
    args = parse_args(argv)

    # Step 3a: Set up logging (stderr)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)

    # Step 3b: Configure the loader, then load; a missing or bad file ends with one error line, not a traceback
    loader = KBLoader(args.data_path)
    try:
        docs = loader.load()
    except (FileNotFoundError, ValueError) as err:
        logger.error("%s", err)
        return 1

    # Step 3c: Print what was read
    print_documents(docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
