"""
IT Knowledge Base: Read the Knowledge Base
==========================================

Reads the knowledge base CSV file into LangChain Documents, one per article, after checking all of it: either every
row is read, or nothing is and the error says what's wrong. It handles:
  1. Checking the file: it exists and can be opened, is text in its encoding, can be read as CSV, and its header
     names every column the settings ask for
  2. Checking each row: the right number of fields and a value for each required column; every bad row is listed in
     one error, with its row and line, so they can all be fixed at once
  3. Each article's text ("Title: ...", "Problem: ..." sections), and its labels and where it came from as metadata

Usage:
    loader = KBLoader(path, text_columns=[...], metadata_columns=[...], required_columns=[...])   # reads nothing
    docs = loader.load()     ->  one Document per article; or IngestionError
"""
import csv
import logging
from collections.abc import Iterator
from pathlib import Path

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document

from src.exceptions import IngestionError
from src.observability.tracing import span

logger = logging.getLogger(__name__)

MAX_ROW_PROBLEMS = 5        # the error lists this many bad rows, then how many more there are


class KBLoader(BaseLoader):
    """
    A LangChain document loader for the knowledge base CSV file.

    Step 1: Configure: the constructor stores the settings and reads nothing
    Step 2: Load: lazy_load() reads and checks the whole file, then yields one Document per article (load()
            collects them into a list)

    Each Document's metadata has doc_id (its row, from 0), source (the file's name) and the metadata columns: the
    chunker and the sources of each answer rely on doc_id, source and title.
    """

    def __init__(self, path: str | Path, *, text_columns: list[str], metadata_columns: list[str],
                 required_columns: list[str], encoding: str = "utf-8"):
        self.path = Path(path)
        self.text_columns = list(text_columns)
        self.metadata_columns = list(metadata_columns)
        self.required_columns = list(required_columns)
        self.encoding = encoding

    def lazy_load(self) -> Iterator[Document]:
        """
        Yield one Document per article, in the file's order, once the whole file has passed its checks.

        Raises:
            IngestionError: the file is missing, can't be opened, is empty, isn't text in `encoding`, isn't CSV,
                has no articles, lacks a column, or has rows that can't be read (each one listed)
        """
        with span("ingestion.load", file=self.path.name) as fields:
            rows = self._read_rows()
            fields["documents"] = len(rows)
        for number, row in enumerate(rows):
            yield self._to_document(number, row)

    def _read_rows(self) -> list[dict[str, str]]:
        """Every row as {column: value}, trimmed; or IngestionError."""
        path = self.path.resolve()
        if not path.is_file():
            raise IngestionError(f"Knowledge base file not found: {path}")
        try:
            with open(path, encoding=self.encoding, newline="") as file:
                # Step 2a: The header names every column the settings read
                reader = csv.DictReader(file)
                # Excel's "CSV UTF-8" starts the file with an invisible BOM; spaces after commas are common too
                columns = [name.lstrip("﻿").strip() for name in reader.fieldnames or []]
                if not columns:
                    raise IngestionError(f"Knowledge base file is empty, with no header row: {path}")
                missing = [name for name in dict.fromkeys(self.text_columns + self.metadata_columns)
                           if name not in columns]
                if missing:
                    raise IngestionError(f"Knowledge base file is missing columns ({', '.join(missing)}): {path}")
                reader.fieldnames = columns

                # Step 2b: Each row has every field, and a value for each required column
                rows, problems = [], []
                for row in reader:
                    problem = self._check_row(row, len(columns))
                    if problem:
                        problems.append(f"row {len(rows) + len(problems)} (line {reader.line_num}): {problem}")
                    else:
                        rows.append({name: value.strip() for name, value in row.items()})
        except UnicodeDecodeError as err:
            raise IngestionError(f"Knowledge base file isn't {self.encoding} text ({err.reason}): {path}. "
                                 "Save it as UTF-8.") from None
        except csv.Error as err:
            raise IngestionError(f"Knowledge base file can't be read as CSV ({err}): {path}") from None
        except LookupError:
            raise IngestionError(f"Knowledge base file's encoding isn't one Python knows: {self.encoding}") from None
        except OSError as err:          # a folder by that name, or no permission to read it
            raise IngestionError(f"Knowledge base file can't be opened ({err.strerror}): {path}") from None

        # Step 2c: All or nothing: a knowledge base with a row missing would answer without saying so
        if problems:
            shown = "; ".join(problems[:MAX_ROW_PROBLEMS])
            more = f"; and {len(problems) - MAX_ROW_PROBLEMS} more" if len(problems) > MAX_ROW_PROBLEMS else ""
            raise IngestionError(f"Knowledge base file has {len(problems)} row(s) that can't be read: {shown}{more}. "
                                 f"Fix them in {path}")
        if not rows:
            raise IngestionError(f"Knowledge base file has a header row but no articles: {path}")
        return rows

    def _check_row(self, row: dict, column_count: int) -> str | None:
        """What's wrong with one row, or None. DictReader puts extra fields under None and missing ones as None."""
        if None in row or None in row.values():
            fields = column_count + len(row.get(None, [])) - sum(value is None for value in row.values())
            return f"{fields} fields, but the header has {column_count}"
        blank = [name for name in self.required_columns if not row[name].strip()]
        return f"no value for {', '.join(blank)}" if blank else None

    def _to_document(self, number: int, row: dict[str, str]) -> Document:
        """The text as labelled sections, so the model can tell the problem from the fix; the labels as metadata."""
        text = "\n\n".join(f"{column.capitalize()}: {row[column]}" for column in self.text_columns)
        metadata = {"doc_id": str(number), "source": self.path.name,
                    **{column: row[column] for column in self.metadata_columns}}
        return Document(page_content=text, metadata=metadata)
