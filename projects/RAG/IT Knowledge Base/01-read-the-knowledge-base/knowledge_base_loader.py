"""
IT Knowledge Base: Read the Knowledge Base
==========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article. It handles:
  1. Checking the file: it exists, and its header names the required columns, each once
  2. Checking each row: the right number of fields, no blank required value, no invisible characters, and only
     allowed values (a row that can't be trusted is skipped)
  3. Redacting sensitive data (PII, PCI, secrets) before it goes into a Document: see sensitive_data.py
  4. Removing duplicates, and flagging a title used for different content
  5. Reporting everything skipped, removed, redacted or flagged, and why; printing every Document

Nothing is dropped or changed without being reported: what, where (row and line), and why.

Usage:
    python knowledge_base_loader.py                                           # reads data/sample_it_kb.csv
    python knowledge_base_loader.py --data-path data/sample_it_kb_messy.csv   # a file with a problem in most rows
    python knowledge_base_loader.py --log-level DEBUG                         # also logs each row and each issue
"""
import argparse
import csv
import logging
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from sensitive_data import redact

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Configuration
# -------------------------------------------------

# Found next to this script, whichever folder it's run from
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"

# What every article needs: what it's about, the problem, and the fix
REQUIRED_COLUMNS = ("title", "problem", "resolution")

# The values a column may have; another value is flagged, and the row kept
ALLOWED_VALUES = {"priority": ("Low", "Medium", "High", "Critical")}

# Characters you can't see that still change the text: control characters (not tab or newline) and zero-width ones
INVISIBLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‍⁠﻿]")

# A skipped row is shown up to this many characters
SHOW_LIMIT = 500


# -------------------------------------------------
# LoadReport - Everything Skipped, Removed, Redacted or Flagged
# -------------------------------------------------

@dataclass
class Issue:
    """One thing the checks found in a row: where, and what."""
    row: int
    lines: str          # "6", or "15-18" for a row that runs over several lines
    message: str
    content: str = ""   # a skipped row's fields, with sensitive values redacted


@dataclass
class LoadReport:
    """What load() did with the rows: how many it kept, and every one it skipped, removed, redacted or flagged."""
    rows: int = 0
    kept: int = 0
    blank_lines: int = 0
    skipped: list[Issue] = field(default_factory=list)      # not read: the row can't be trusted as it is
    duplicates: list[Issue] = field(default_factory=list)   # removed: the first copy is kept
    redacted: list[Issue] = field(default_factory=list)     # kept, with a sensitive value replaced
    flagged: list[Issue] = field(default_factory=list)      # kept, but a person should look

    def has_issues(self) -> bool:
        return bool(self.skipped or self.duplicates or self.redacted or self.flagged)


# -------------------------------------------------
# KBLoader Class - Reads the Knowledge Base
# -------------------------------------------------

class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores the settings and reads nothing
    Step 2: Load: lazy_load() checks the file, then yields one Document per good row (load() collects them);
            afterwards, self.report says what happened to every other row
    """

    def __init__(self, data_path: str | Path, encoding: str = "utf-8",
                 required_columns: tuple[str, ...] = REQUIRED_COLUMNS,
                 allowed_values: dict[str, tuple[str, ...]] | None = None):
        """
        Args:
            data_path: the CSV file to read; its first line must name the columns
            encoding: the file's text encoding
            required_columns: the columns the header must have, and every row must fill in
            allowed_values: the values a column may have (default: ALLOWED_VALUES); others are flagged
        """
        self.data_path = Path(data_path)
        self.encoding = encoding
        self.required_columns = tuple(required_columns)
        self.allowed_values = dict(ALLOWED_VALUES if allowed_values is None else allowed_values)
        self.report = LoadReport()

    def lazy_load(self) -> Iterator[Document]:
        """
        Yield one Document per good row, in the file's order. Every other row goes into self.report, with why.

        Raises:
            FileNotFoundError: there's no file at data_path
            ValueError: the file is empty, isn't text in `encoding`, can't be read as CSV, or its header can't be used
        """
        # Step 2a: Check the file exists (full path, so a relative path shows where it was looked for)
        path = self.data_path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Knowledge base file not found: {path}")

        self.report = report = LoadReport()
        first_text: dict[str, tuple[int, str]] = {}    # a Document's text, simplified -> (its row, its exact text)
        first_title: dict[str, int] = {}               # a title, in lower case -> its row
        try:
            with open(path, encoding=self.encoding, newline="") as file:
                # Step 2b: Read the header row and check it; a bad header stops everything
                reader = csv.reader(file)
                header = next((fields for fields in reader if fields), None)
                columns = self._check_header(header, path)
                report.blank_lines = reader.line_num - 1 if header else 0
                logger.info("Reading %s (%s): %d columns (%s)", path, self.encoding, len(columns), ", ".join(columns))

                last_line = reader.line_num
                for fields in reader:
                    lines = str(reader.line_num) if reader.line_num == last_line + 1 else \
                        f"{last_line + 1}-{reader.line_num}"
                    last_line = reader.line_num
                    if not fields:                     # a blank line: nothing to read
                        report.blank_lines += 1
                        continue
                    doc = self._check_row(fields, columns, report.rows, lines, first_text, first_title)
                    report.rows += 1
                    if doc:
                        report.kept += 1
                        logger.debug("Row %d: %s", doc.metadata["row"], doc.page_content.splitlines()[0])
                        yield doc
        except UnicodeDecodeError as err:
            # Often a file saved as UTF-16 by PowerShell 5's `>`
            raise ValueError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                             "Save it as UTF-8, or give KBLoader its encoding.") from None
        except csv.Error as err:
            # For example a field over csv.field_size_limit() characters: the rest of the file can't be trusted
            raise ValueError(f"Knowledge base file can't be read as CSV at line {reader.line_num} ({err}): {path}") \
                from None

        # Step 2h: Log the totals
        if report.rows == 0:
            logger.warning("%s has a header row but no articles", self.data_path.name)
            return
        logger.info("Read %d documents from %s", report.kept, self.data_path.name)
        if report.has_issues():
            logger.warning("Data checks on %s: %d skipped, %d duplicates removed, %d sensitive values redacted, "
                           "%d flagged (the report lists each one)", self.data_path.name, len(report.skipped),
                           len(report.duplicates), len(report.redacted), len(report.flagged))

    def _check_header(self, header: list[str] | None, path: Path) -> list[str]:
        """The header's column names, cleaned. A missing header, a blank or repeated name, or a missing required
        column fails."""
        if header is None:
            raise ValueError(f"Knowledge base file is empty, with no header row: {path}")
        # Excel's "CSV UTF-8" starts the file with an invisible BOM (﻿); spaces after commas are common too
        columns = [name.lstrip("﻿").strip() for name in header]
        unnamed = [str(place) for place, name in enumerate(columns, 1) if not name]
        if unnamed:
            raise ValueError(f"Knowledge base file has a column with no name (column {', '.join(unnamed)}): {path}")
        repeated = sorted({name for name in columns if columns.count(name) > 1})
        if repeated:
            raise ValueError(f"Knowledge base file has a column more than once ({', '.join(repeated)}): {path}")
        missing = [name for name in self.required_columns if name not in columns]
        if missing:
            raise ValueError(f"Knowledge base file is missing required columns ({', '.join(missing)}): {path}")
        if columns != header:
            logger.info("Column names cleaned of spaces or a BOM: %s", ", ".join(columns))
        return columns

    def _check_row(self, fields: list[str], columns: list[str], number: int, lines: str,
                   first_text: dict[str, tuple[int, str]], first_title: dict[str, int]) -> Document | None:
        """Check one row and record what was found. Returns its Document, or None if it's skipped or removed."""
        report = self.report

        def skip(message: str) -> None:
            report.skipped.append(Issue(number, lines, message, self._show(fields, columns)))
            logger.debug("Row %d skipped: %s", number, message)

        # Step 2c: The right number of fields, or the values may be under the wrong columns
        if len(fields) != len(columns):
            message = f"{len(fields)} fields, but the header has {len(columns)}"
            if len(fields) > len(columns):
                message += ": usually a comma inside a value that isn't in quotes"
            elif "-" in lines:
                message += f": a quote that's never closed made lines {lines} into one row"
            skip(message)
            return None

        # Step 2d: Remove invisible characters (flagged), trim spaces, and check the required values
        values, flags, redactions = {}, [], []
        for name, value in zip(columns, fields):
            value, count = INVISIBLE.subn("", value)
            if count:
                flags.append(f"{count} invisible character{'s' if count > 1 else ''} removed from {name}")
            values[name] = value.strip()
        blank = [name for name in self.required_columns if not values[name]]
        if blank:
            skip(f"no value for {', '.join(blank)}")
            return None

        # Step 2e: Redact sensitive values before they go into the Document
        for name, value in values.items():
            values[name], findings = redact(value)
            for found in findings:
                advice = ": change it, it's been exposed" if found.category == "secret" else ""
                redactions.append(f"{name}: {found.kind} {found.masked} ({found.category}{advice})")

        # Step 2f: Values outside the allowed ones are flagged, not skipped
        for name, allowed in self.allowed_values.items():
            if values.get(name) and values[name] not in allowed:
                flags.append(f'{name} is "{values[name]}", not one of {", ".join(allowed)}')

        # Step 2g: Remove a duplicate (the same text, ignoring case and spacing); flag a reused title
        doc = self._to_document(values, number)
        key = " ".join(doc.page_content.casefold().split())
        if key in first_text:
            row, text = first_text[key]
            how = "" if text == doc.page_content else " apart from upper and lower case or spacing"
            report.duplicates.append(Issue(number, lines, f"the same as row {row}{how}: {values.get('title', '')}"))
            logger.debug("Row %d removed: a duplicate of row %d", number, row)
            return None
        first_text[key] = (number, doc.page_content)
        title = values.get("title", "").casefold()
        if title in first_title:
            flags.append(f"the same title as row {first_title[title]}, with different content: {values['title']}")
        elif title:
            first_title[title] = number

        report.redacted += [Issue(number, lines, message) for message in redactions]
        report.flagged += [Issue(number, lines, message) for message in flags]
        for message in redactions + flags:
            logger.debug("Row %d: %s", number, message)
        return doc

    def _show(self, fields: list[str], columns: list[str]) -> str:
        """A skipped row's fields, as `column: value | ...`, with sensitive values redacted, on one line."""
        names = columns + [f"extra {place}" for place in range(1, len(fields) - len(columns) + 1)]
        text, _ = redact(" | ".join(f"{name}: {value.strip()}" for name, value in zip(names, fields)))
        text = INVISIBLE.sub("", text).replace("\r", "").replace("\n", "\\n")
        return text if len(text) <= SHOW_LIMIT else f"{text[:SHOW_LIMIT]}... ({len(text) - SHOW_LIMIT} more characters)"

    def _to_document(self, values: dict[str, str], number: int) -> Document:
        """One "column: value" line per column, and the file and row as metadata."""
        text = "\n".join(f"{column}: {value}" for column, value in values.items())
        return Document(page_content=text, metadata={"source": self.data_path.name, "row": number})


# -------------------------------------------------
# Output - What Was Read, and What the Checks Found
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


def print_report(report: LoadReport) -> None:
    """Print what the checks found: every row skipped, removed, redacted or flagged, with where and why."""
    blank = f" ({report.blank_lines} blank line{'s' if report.blank_lines != 1 else ''} ignored)" \
        if report.blank_lines else ""
    print(f"Data checks: {report.rows} rows read, {report.kept} kept{blank}")
    if not report.has_issues():
        print("Nothing skipped, removed, redacted or flagged.")
        return
    for heading, issues in [("Skipped, not read: each can't be trusted as it is", report.skipped),
                            ("Removed as duplicates: the first copy is kept", report.duplicates),
                            ("Sensitive values redacted: replaced in the text, never shown in full", report.redacted),
                            ("Flagged, kept: a person should look at these", report.flagged)]:
        if not issues:
            continue
        print()
        print(f"{heading} ({len(issues)})")
        for issue in issues:
            print(f"  row {issue.row} (line{'s' if '-' in issue.lines else ''} {issue.lines}): {issue.message}")
            if issue.content:
                print(f"      {issue.content}")


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
    """Read the knowledge base, print every Document, then the data checks. Returns the exit code: 0 if read."""
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

    # Step 3c: Print what was read, then what the checks found
    print_documents(docs)
    print()
    print_report(loader.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
