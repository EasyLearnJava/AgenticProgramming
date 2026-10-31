"""
IT Knowledge Base: Documents and Metadata
=========================================

Reads the IT knowledge base CSV file into LangChain Documents, one per article: the text to search kept apart from
the labels to filter by, every article checked against a schema, each with an ID and where it came from. It handles:
  1. Checking the file and each row, redacting sensitive data and removing duplicates, as Advanced/01 does
  2. Normalizing the labels: one spelling for each priority, system and category, from kb_settings.toml
  3. Checking each article against the schema (article.py): a value that breaks a rule skips it, with why
  4. Giving each article an ID that survives re-sorting the file, and recording where it came from (provenance)
  5. A hash of each field of each article kept, for comparing with the last run (manifest.py)
  6. Reporting everything skipped, removed, normalized, redacted or flagged, and why

Nothing is dropped or changed without being reported: what, where (row and line), and why. pipeline.py runs it, then
compares with the last run and cuts the articles passed on into chunks.
"""
import csv
import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from pydantic import ValidationError

from article import REQUIRED_FIELDS, Article, Spellings, describe, doc_id
from sensitive_data import redact
from settings import KBSettings
from utils import sha256_file, short_hash, simplify

logger = logging.getLogger(__name__)


# -------------------------------------------------
# Configuration
# -------------------------------------------------

# Found next to this script, whichever folder it's run from
FOLDER = Path(__file__).resolve().parent
KB_FILE = FOLDER / "data" / "sample_it_kb.csv"
SETTINGS_FILE = FOLDER / "kb_settings.toml"
MANIFEST_FILE = FOLDER / "data" / "manifest.json"     # written by each run; not in git

# In every Document's metadata, so any answer can be traced to the code that loaded its article
LOADER_VERSION = "advanced-09"

# Characters you can't see that still change the text: control characters (not tab or newline) and zero-width ones
INVISIBLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‍⁠﻿]")

# A skipped row is shown up to this many characters
SHOW_LIMIT = 500


def utc_now() -> datetime:
    return datetime.now(UTC)


# -------------------------------------------------
# LoadReport - Everything Skipped, Removed, Normalized, Redacted or Flagged
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
    """What load() did with the rows: how many it kept, and every one it skipped, removed, changed or flagged."""
    rows: int = 0
    kept: int = 0
    blank_lines: int = 0
    skipped: list[Issue] = field(default_factory=list)      # not read: the row can't be trusted as it is
    duplicates: list[Issue] = field(default_factory=list)   # removed: the first copy is kept
    normalized: list[Issue] = field(default_factory=list)   # kept, with a label changed to its one spelling
    redacted: list[Issue] = field(default_factory=list)     # kept, with a sensitive value replaced
    flagged: list[Issue] = field(default_factory=list)      # kept, but a person should look
    held: dict[str, str] = field(default_factory=dict)      # {ID: title} of skipped rows whose ID is known
    unidentified: int = 0                                   # skipped rows with no ID to tell which article they were

    def has_issues(self) -> bool:
        return bool(self.skipped or self.duplicates or self.normalized or self.redacted or self.flagged)


@dataclass
class _Seen:
    """What the rows kept so far hold, to find a copy, a shared ID or a reused title."""
    content: dict[str, tuple[int, str]] = field(default_factory=dict)   # simplified content -> (row, exact content)
    ids: dict[str, int] = field(default_factory=dict)                   # ID -> row
    titles: dict[str, int] = field(default_factory=dict)                # title, simplified -> row


# -------------------------------------------------
# KBLoader Class - Reads the Knowledge Base
# -------------------------------------------------

class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores the settings and reads nothing
    Step 2: Load: lazy_load() checks the file, then yields one Document per good row (load() collects them);
            afterwards, self.report says what happened to every other row, and self.fingerprints holds a hash of
            each kept article's fields, for the manifest
    """

    def __init__(self, data_path: str | Path, *, settings: KBSettings, encoding: str = "utf-8",
                 clock: Callable[[], datetime] = utc_now):
        """
        Args:
            data_path: the CSV file to read; its first line must name the columns
            settings: what the file holds and how an article becomes a Document (load_settings() reads them)
            encoding: the file's text encoding
            clock: gives the time each load starts, recorded in every Document as loaded_at
        """
        self.data_path = Path(data_path)
        self.settings = settings
        self.encoding = encoding
        self.clock = clock
        self.report = LoadReport()
        self.fingerprints: dict[str, dict[str, str]] = {}

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
        self.fingerprints = {}
        # Where every article in this load came from, and when, by which code
        provenance = {"source": self.data_path.name, "source_sha256": sha256_file(path),
                      "loaded_at": self.clock().isoformat(timespec="seconds"), "loader_version": LOADER_VERSION}
        spellings = {label: Spellings(table) for label, table in self.settings.spellings.items()}
        seen = _Seen()
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
                    doc = self._check_row(fields, columns, report.rows, lines, seen, spellings, provenance)
                    report.rows += 1
                    if doc:
                        report.kept += 1
                        logger.debug("Row %d: %s %s", doc.metadata["row"], doc.metadata["doc_id"],
                                     doc.metadata["title"])
                        yield doc
        except UnicodeDecodeError as err:
            # Often a file saved as UTF-16 by PowerShell 5's `>`
            raise ValueError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                             "Save it as UTF-8, or give KBLoader its encoding.") from None
        except csv.Error as err:
            # For example a field over csv.field_size_limit() characters: the rest of the file can't be trusted
            raise ValueError(f"Knowledge base file can't be read as CSV at line {reader.line_num} ({err}): {path}") \
                from None

        # Step 2k: Log the totals
        if report.rows == 0:
            logger.warning("%s has a header row but no articles", self.data_path.name)
            return
        logger.info("Read %d documents from %s", report.kept, self.data_path.name)
        if report.has_issues():
            logger.warning("Data checks on %s: %d skipped, %d duplicates removed, %d normalized, %d sensitive values "
                           "redacted, %d flagged (the report lists each one)", self.data_path.name,
                           len(report.skipped), len(report.duplicates), len(report.normalized),
                           len(report.redacted), len(report.flagged))

    def _check_header(self, header: list[str] | None, path: Path) -> list[str]:
        """The header's column names, cleaned. A missing header, a blank or repeated name, or a missing required
        column fails; a column the settings don't name is logged, and not read."""
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
        required = [self.settings.columns[name] for name in REQUIRED_FIELDS]
        missing = [column for column in required if column not in columns]
        if missing:
            raise ValueError(f"Knowledge base file is missing required columns ({', '.join(missing)}): {path}")
        if columns != header:
            logger.info("Column names cleaned of spaces or a BOM: %s", ", ".join(columns))
        unread = [name for name in columns if name not in self.settings.columns.values()]
        if unread:
            logger.info("Not read: column%s %s (kb_settings.toml gives %s no field)", "s" if len(unread) > 1 else "",
                        ", ".join(unread), "them" if len(unread) > 1 else "it")
        return columns

    def _check_row(self, fields: list[str], columns: list[str], number: int, lines: str, seen: _Seen,
                   spellings: dict[str, Spellings], provenance: dict[str, str]) -> Document | None:
        """Check one row and record what was found. Returns its Document, or None if it's skipped or removed."""
        report = self.report

        def skip(message: str, values: dict[str, str] | None = None, *, kept_id: bool = False) -> None:
            report.skipped.append(Issue(number, lines, message, self._show(fields, columns)))
            # The article this row was, if it can be told: its last version stays (manifest.py), and isn't removed.
            # kept_id: its ID is a kept article's, so there's nothing to hold.
            the_id = doc_id(values, self.settings.id_fields) if values else None
            if the_id:
                report.held[the_id] = values.get("title", "")
            elif not kept_id:
                report.unidentified += 1
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

        # Step 2d: Remove invisible characters (flagged), trim spaces, keep the columns the settings name, and check
        # the required values
        field_of = {column: name for name, column in self.settings.columns.items()}
        values, flags, redactions, normalized = {}, [], [], []
        for column, value in zip(columns, fields, strict=True):
            if column not in field_of:
                continue
            value, count = INVISIBLE.subn("", value)
            if count:
                flags.append(f"{count} invisible character{'s' if count > 1 else ''} removed from {column}")
            values[field_of[column]] = value.strip()
        blank = [self.settings.columns[name] for name in REQUIRED_FIELDS if not values[name]]
        if blank:
            skip(f"no value for {', '.join(blank)}", values)
            return None

        # Step 2e: Redact sensitive values before they go into the Document
        for name, value in values.items():
            values[name], findings = redact(value)
            for found in findings:
                advice = ": change it, it's been exposed" if found.category == "secret" else ""
                redactions.append(f"{name}: {found.kind} {found.masked} ({found.category}{advice})")

        # Step 2f: One spelling for each label value; a system or category the table doesn't know is flagged
        for label, table in spellings.items():
            value = values.get(label)
            if not value:
                continue
            right = table.right_spelling(value)
            if right is None:
                if label != "priority":                # an unknown priority fails the schema, next
                    flags.append(f'{label} "{value}" has no spelling in kb_settings.toml: kept as written')
            elif right != value:
                normalized.append(f'{label}: "{value}" made "{right}"')
                values[label] = right

        # Step 2g: The schema: a value that breaks a rule skips the article, naming the field and why
        try:
            article = Article.model_validate(values)
        except ValidationError as err:
            skip(f"doesn't fit the schema: {describe(err)}", values)
            return None
        data = article.model_dump(mode="json")

        # Step 2h: Remove a duplicate (the same values, ignoring case and spacing)
        exact = json.dumps({name: value for name, value in data.items() if name != "id"}, ensure_ascii=False)
        key = simplify(exact)
        if key in seen.content:
            row, first = seen.content[key]
            how = "" if first == exact else " apart from upper and lower case or spacing"
            report.duplicates.append(Issue(number, lines, f"the same as row {row}{how}: {data['title']}"))
            logger.debug("Row %d removed: a duplicate of row %d", number, row)
            return None

        # Step 2i: Its ID: two different articles can't share one, or an update to one would overwrite the other
        the_id = doc_id(data, self.settings.id_fields)
        if the_id in seen.ids:
            fields_used = " and ".join(self.settings.id_fields)
            why = "two articles can't share an id" if data["id"] else \
                f"the same {fields_used}: give one a different title, or the file an id column"
            skip(f"the same ID as row {seen.ids[the_id]} ({the_id}), with different content: {why}", kept_id=True)
            return None
        seen.content[key] = (number, exact)
        seen.ids[the_id] = number

        # Step 2j: Flag a title used for two articles (the ID tells them apart: their systems differ)
        title = simplify(data["title"])
        if title in seen.titles:
            flags.append(f"the same title as row {seen.titles[title]}, with different content: {data['title']}")
        else:
            seen.titles[title] = number

        report.normalized += [Issue(number, lines, message) for message in normalized]
        report.redacted += [Issue(number, lines, message) for message in redactions]
        report.flagged += [Issue(number, lines, message) for message in flags]
        for message in normalized + redactions + flags:
            logger.debug("Row %d: %s", number, message)
        return self._to_document(data, the_id, number, provenance)

    def _show(self, fields: list[str], columns: list[str]) -> str:
        """A skipped row's fields, as `column: value | ...`, with sensitive values redacted, on one line."""
        names = columns + [f"extra {place}" for place in range(1, len(fields) - len(columns) + 1)]
        # A short row has fewer fields than names: zip stops at the last field
        text, _ = redact(" | ".join(f"{name}: {value.strip()}" for name, value in zip(names, fields, strict=False)))
        text = INVISIBLE.sub("", text).replace("\r", "").replace("\n", "\\n")
        return text if len(text) <= SHOW_LIMIT else f"{text[:SHOW_LIMIT]}... ({len(text) - SHOW_LIMIT} more characters)"

    def _to_document(self, data: dict, the_id: str, number: int, provenance: dict[str, str]) -> Document:
        """The text fields as "Title: ..." blocks; the labels, ID and provenance as metadata; the fields' hashes kept
        in self.fingerprints, for the manifest."""
        text = "\n\n".join(f"{name.capitalize()}: {data[name]}" for name in self.settings.text_fields if data[name])
        fingerprint = {name: short_hash(json.dumps(value, ensure_ascii=False))
                       for name, value in data.items() if name != "id"}
        self.fingerprints[the_id] = fingerprint
        metadata = {"doc_id": the_id, **{name: data[name] for name in self.settings.label_fields}, **provenance,
                    "row": number, "content_hash": short_hash(json.dumps(fingerprint, sort_keys=True))}
        return Document(page_content=text, metadata=metadata)

