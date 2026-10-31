"""
IT Knowledge Base: What Changed Since the Last Run
==================================================

Remembers each run's articles in a small JSON file, the manifest, so the next run passes on only what changed. It
handles:
  1. Reading the last run's manifest: each article's ID, title, and a short hash of each of its fields
  2. Comparing this run's articles with it: added, changed (and in which fields), removed, unchanged, and skipped
     this run (their last version stays: a row that fails a check is never taken for a removed article)
  3. Writing this run's manifest whole or not at all: a temporary file first, then a rename

    Manifest(path).compare(docs, fingerprints)  ->  Changes(added=[...], changed=[(doc, ["resolution"])], ...)
"""
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.documents import Document

# The manifest's layout; a file in another layout isn't read
MANIFEST_VERSION = 1


@dataclass
class Changes:
    """This run's articles compared with the last run's."""
    first_run: bool = False                     # no manifest yet: every article is new
    full: bool = False                          # --full: every article passed on, whatever changed
    added: list[Document] = field(default_factory=list)
    changed: list[tuple[Document, list[str]]] = field(default_factory=list)     # each with the fields that changed
    unchanged: list[Document] = field(default_factory=list)
    removed: list[tuple[str, str]] = field(default_factory=list)                # (ID, title): listed for deletion
    held: list[tuple[str, str]] = field(default_factory=list)                   # (ID, title): skipped this run

    def passed_on(self) -> list[Document]:
        """The articles the next step needs, added and changed, in the file's order."""
        return sorted(self.added + [doc for doc, _ in self.changed], key=lambda doc: doc.metadata["row"])


class Manifest:
    """
    The manifest file.

    Step 1: Configure: the constructor stores the path and reads nothing
    Step 2: compare() reads the last run's manifest and compares this run's articles with it
    Step 3: write() saves this run's, for the next run to compare with
    """

    def __init__(self, path: str | Path):
        """
        Args:
            path: the manifest's JSON file; there's none before the first run
        """
        self.path = Path(path)

    def read(self) -> dict[str, dict] | None:
        """
        The last run's articles, {ID: {"title": ..., "fields": {field: hash}}}, or None when there's no manifest.

        Raises:
            ValueError: the file is there but isn't a manifest this code can read
        """
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != MANIFEST_VERSION:
                raise ValueError(f"layout {data.get('version')}, not {MANIFEST_VERSION}")
            articles = data["articles"]
            if not all(isinstance(entry["title"], str) and isinstance(entry["fields"], dict)
                       for entry in articles.values()):
                raise ValueError("an article without a title or fields")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError,
                ValueError) as err:
            raise ValueError(f"The manifest can't be read ({type(err).__name__}: {err}): {self.path.resolve()}. "
                             "Delete it, or run with --full, and every article is passed on.") from None
        return articles

    def compare(self, docs: list[Document], fingerprints: dict[str, dict[str, str]], *,
                held: dict[str, str] | None = None, full: bool = False) -> Changes:
        """
        This run's articles compared with the last run's.

        Args:
            docs: this run's Documents, each with its doc_id in metadata
            fingerprints: each doc_id's {field: hash}, from the loader
            held: {ID: title} of rows skipped this run whose ID is known: they're not removed, their last version stays
            full: pass on every article, whatever changed (the manifest isn't read)
        """
        if full:
            return Changes(full=True, added=list(docs))
        last = self.read()
        if last is None:
            return Changes(first_run=True, added=list(docs))

        changes = Changes()
        for doc in docs:
            before = last.get(doc.metadata["doc_id"])
            if before is None:
                changes.added.append(doc)
                continue
            now = fingerprints[doc.metadata["doc_id"]]
            fields = [name for name in dict.fromkeys([*now, *before["fields"]])
                      if now.get(name) != before["fields"].get(name)]
            if fields:
                changes.changed.append((doc, fields))
            else:
                changes.unchanged.append(doc)

        ids = {doc.metadata["doc_id"] for doc in docs}
        for the_id, before in last.items():
            if the_id not in ids:
                (changes.held if the_id in (held or {}) else changes.removed).append((the_id, before["title"]))
        return changes

    def write(self, docs: list[Document], fingerprints: dict[str, dict[str, str]], *,
              keep: tuple[str, ...] = ()) -> None:
        """
        Save this run's articles, and the last run's entries for the IDs in keep (skipped this run), whole or not at
        all: written to a temporary file, then renamed over the old manifest.

        Raises:
            ValueError: the file can't be written (the message says why); the old manifest is left as it was
        """
        last = (self.read() or {}) if keep else {}
        articles = {the_id: last[the_id] for the_id in keep if the_id in last}
        for doc in docs:
            articles[doc.metadata["doc_id"]] = {"title": doc.metadata["title"],
                                                "fields": fingerprints[doc.metadata["doc_id"]]}
        data = {"version": MANIFEST_VERSION, "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "articles": articles}
        temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as err:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"The manifest can't be saved ({err}): {self.path.resolve()}") from None
