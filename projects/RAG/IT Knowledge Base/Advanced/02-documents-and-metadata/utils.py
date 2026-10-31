"""
IT Knowledge Base: Helpers
==========================

Small, general helpers the project's other files use. Nothing here knows about articles or the knowledge base. It
handles:
  1. Hashes: of a file (its checksum) and of a text (a short, stable fingerprint)
  2. Comparing text: one form for "the same apart from case and spacing", and one for spellings of a label
  3. Printing: the Documents, the data checks and the changes since the last run, to stdout

    simplify("  VPN   Connection ")  ->  "vpn connection"
    spelling_key("Wi-Fi")            ->  "wifi"
"""
import hashlib
import re
from pathlib import Path

# Read a file this many bytes at a time, so a big one never has to fit in memory
HASH_BLOCK_SIZE = 1 << 20

# How many hex digits of a SHA-256 a short hash keeps: 64 bits, so two different texts share one only by chance
SHORT_HASH_LENGTH = 16


# -------------------------------------------------
# Hashes
# -------------------------------------------------

def sha256_file(path: Path) -> str:
    """The SHA-256 of a file's bytes, as 64 hex digits: the same file always gives the same checksum."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(HASH_BLOCK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def short_hash(text: str) -> str:
    """The first 16 hex digits of the text's SHA-256: a fingerprint that changes when any character does."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:SHORT_HASH_LENGTH]


# -------------------------------------------------
# Comparing Text
# -------------------------------------------------

def simplify(text: str) -> str:
    """The text in lower case, with every run of spaces, tabs or newlines made one space: two texts that differ only
    in case or spacing simplify to the same."""
    return " ".join(text.casefold().split())


def spelling_key(text: str) -> str:
    """The text in lower case, without spaces, hyphens or underscores: "Wi-Fi", "WiFi" and "wi fi" are one key."""
    return re.sub(r"[\s_-]+", "", text.casefold())


# -------------------------------------------------
# Printing (stdout; the log goes to stderr)
# -------------------------------------------------

def print_documents(docs: list, heading: str) -> None:
    """Print a heading with the count, each Document's ID and title, then every Document in full."""
    print(f"{heading}: {len(docs)}")
    for doc in docs:
        print(f"  {doc.metadata['doc_id']}  {doc.metadata['title']}")

    for number, doc in enumerate(docs, 1):
        print()
        print(f"Document {number} of {len(docs)}")
        print("Text (page_content):")
        print(doc.page_content)
        print()
        print("Labels and where it came from (metadata):")
        for name, value in doc.metadata.items():
            print(f"  {name}: {value}")


def print_report(report) -> None:
    """Print what the data checks found: every row skipped, removed, normalized, redacted or flagged, and why."""
    blank = f" ({report.blank_lines} blank line{'s' if report.blank_lines != 1 else ''} ignored)" \
        if report.blank_lines else ""
    print(f"Data checks: {report.rows} rows read, {report.kept} kept{blank}")
    if not report.has_issues():
        print("Nothing skipped, removed, normalized, redacted or flagged.")
        return
    for heading, issues in [("Skipped, not read: each can't be trusted as it is", report.skipped),
                            ("Removed as duplicates: the first copy is kept", report.duplicates),
                            ("Normalized, kept: a label changed to its one spelling", report.normalized),
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


def print_changes(changes) -> None:
    """Print what changed since the last run: each article added, changed (and in which fields) or removed."""
    if changes.first_run:
        print(f"Changes: no earlier run to compare with, so all {len(changes.added)} articles are new")
        return
    if changes.full:
        print(f"Changes: --full, so all {len(changes.added)} articles are passed on, whatever changed")
        return
    print(f"Changes since the last run: {len(changes.added)} added, {len(changes.changed)} changed, "
          f"{len(changes.removed)} removed, {len(changes.unchanged)} unchanged")
    for heading, lines in [
            ("Added: passed on", [f"{doc.metadata['doc_id']}  {doc.metadata['title']}" for doc in changes.added]),
            ("Changed: passed on", [f"{doc.metadata['doc_id']}  {doc.metadata['title']}  ({', '.join(fields)} changed)"
                                    for doc, fields in changes.changed]),
            ("Removed: not in this file, listed for deletion", [f"{doc_id}  {title}"
                                                               for doc_id, title in changes.removed]),
            ("Skipped this run: the last run's version stays", [f"{doc_id}  {title}"
                                                               for doc_id, title in changes.held])]:
        if not lines:
            continue
        print()
        print(f"{heading} ({len(lines)})")
        for line in lines:
            print(f"  {line}")
