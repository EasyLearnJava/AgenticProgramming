"""
IT Knowledge Base: Read the Knowledge Base
==========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article. It handles:
  1. Checking the file: it exists, and its header names the required columns, each once
  2. Checking each row: the right number of fields and no blank required value (a bad row is skipped)
  3. Turning each good row into a Document (page_content + metadata), skipping exact duplicates
  4. Logging what it read and skipped, and printing every Document

Usage:
    python knowledge_base_loader.py                          # reads data/sample_it_kb.csv
    python knowledge_base_loader.py --data-path other.csv    # reads another CSV file
    python knowledge_base_loader.py --log-level DEBUG        # also logs each row
"""
import argparse
import csv
import logging
import sys
from collections import Counter
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

# What every article needs: what it's about, the problem, and the fix
REQUIRED_COLUMNS = ("title", "problem", "resolution")

# Why a row is skipped, in the order the summary lists them
MALFORMED, MISSING_VALUE, DUPLICATE = "malformed", "missing a required value", "duplicate"


# -------------------------------------------------
# KBLoader Class - Reads the Knowledge Base
# -------------------------------------------------

class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores the settings and reads nothing
    Step 2: Load: lazy_load() checks the file, then yields one Document per good row (load() collects them)
    """

    def __init__(self, data_path: str | Path, encoding: str = "utf-8",
                 required_columns: tuple[str, ...] = REQUIRED_COLUMNS):
        """
        Args:
            data_path: the CSV file to read; its first line must name the columns
            encoding: the file's text encoding
            required_columns: the columns the header must have, and every row must fill in
        """
        self.data_path = Path(data_path)
        self.encoding = encoding
        self.required_columns = tuple(required_columns)

    def lazy_load(self) -> Iterator[Document]:
        """
        Yield one Document per good row, in the file's order. A bad or duplicate row is skipped, with a warning.

        Raises:
            FileNotFoundError: there's no file at data_path
            ValueError: the file is empty, isn't text in `encoding`, or its header can't be used
        """
        # Step 2a: Check the file exists (full path, so a relative path shows where it was looked for)
        path = self.data_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Knowledge base file not found: {path}")

        count = 0
        skipped: Counter[str] = Counter()     # why -> how many rows
        first_row: dict[str, int] = {}        # a Document's text -> the row it first came from
        title_row: dict[str, int] = {}        # a title -> the row it first came from
        try:
            with open(path, encoding=self.encoding, newline="") as file:
                # Step 2b: Read the header row and check it; a bad header stops everything
                reader = csv.DictReader(file)
                reader.fieldnames = self._check_header(reader.fieldnames, path)
                logger.info("Reading %s (%s): %d columns (%s)", path, self.encoding, len(reader.fieldnames),
                            ", ".join(reader.fieldnames))

                for number, row in enumerate(reader):
                    # Step 2c: Check the row; a bad row is skipped, not fatal
                    problem = self._row_problem(row)
                    if problem:
                        logger.warning("Skipping row %d (line %d): %s", number, reader.line_num, problem[1])
                        skipped[problem[0]] += 1
                        continue

                    # Step 2d: Skip an exact duplicate; flag a title reused for different content
                    doc = self._row_to_document(row, number)
                    if doc.page_content in first_row:
                        logger.warning("Skipping row %d (line %d): a duplicate of row %d", number, reader.line_num,
                                       first_row[doc.page_content])
                        skipped[DUPLICATE] += 1
                        continue
                    first_row[doc.page_content] = number
                    title = (row.get("title") or "").strip()
                    if title in title_row:
                        logger.warning("Row %d (line %d) has the same title as row %d, with different content: %s",
                                       number, reader.line_num, title_row[title], title)
                    elif title:
                        title_row[title] = number

                    logger.debug("Row %d: %s", number, doc.page_content.splitlines()[0])
                    count += 1
                    yield doc
        except UnicodeDecodeError as err:
            # Often a file saved as UTF-16 by PowerShell 5's `>`
            raise ValueError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                             "Save it as UTF-8, or give KBLoader its encoding.") from None

        # Step 2e: Log the totals, and what was skipped and why
        rows = count + sum(skipped.values())
        if rows == 0:
            logger.warning("%s has a header row but no articles", self.data_path.name)
            return
        logger.info("Read %d documents from %s", count, self.data_path.name)
        if skipped:
            reasons = ", ".join(f"{skipped[why]} {why}" for why in (MALFORMED, MISSING_VALUE, DUPLICATE)
                                if skipped[why])
            logger.warning("Skipped %d of %d rows in %s: %s", rows - count, rows, self.data_path.name, reasons)

    def _check_header(self, columns: list[str] | None, path: Path) -> list[str]:
        """The header's column names, cleaned. An empty file, a repeated name or a missing required column fails."""
        if columns is None:
            raise ValueError(f"Knowledge base file is empty, with no header row: {path}")
        # Excel's "CSV UTF-8" starts the file with an invisible BOM (﻿); spaces after commas are common too
        columns = [name.lstrip("﻿").strip() for name in columns]
        repeated = sorted({name for name in columns if columns.count(name) > 1})
        if repeated:
            raise ValueError(f"Knowledge base file has a column more than once ({', '.join(repeated)}): {path}")
        missing = [name for name in self.required_columns if name not in columns]
        if missing:
            raise ValueError(f"Knowledge base file is missing required columns ({', '.join(missing)}): {path}")
        return columns

    def _row_problem(self, row: dict) -> tuple[str, str] | None:
        """Why a row can't be used, as (reason, detail), or None when it's fine."""
        # DictReader puts extra fields under the key None, and fills in missing ones with None
        if None in row:
            extra = len(row[None])
            return MALFORMED, f"{extra} more field{'s' if extra > 1 else ''} than the header"
        if None in row.values():
            return MALFORMED, "fewer fields than the header"
        blank = [name for name in self.required_columns if not row[name].strip()]
        if blank:
            return MISSING_VALUE, f"no value for {', '.join(blank)}"
        return None

    def _row_to_document(self, row: dict[str, str], number: int) -> Document:
        """Turn one row into a Document: one "column: value" line per column, and the file and row as metadata."""
        text = "\n".join(f"{column}: {value.strip()}" for column, value in row.items())
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
