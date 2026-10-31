"""
Tests for knowledge_base_loader.py: the LangChain Documents read from data/sample_it_kb.csv (the text apart from the
labels, an ID that survives re-sorting, where each came from), Advanced/01's checks on the messy file, the schema and
spelling checks on the labels file, what it logs, and how it fails. tests/test_pipeline.py runs the steps together.

    KBLoader(KB_FILE, settings=SETTINGS).load()  ->  10 Documents, one per article;
        page_content "Title: ...\\n\\nProblem: ...\\n\\nResolution: ...\\n\\nNotes: ...",
        metadata {"doc_id", the labels, "source", "source_sha256", "loaded_at", "loader_version", "row", "content_hash"}

No key, no network: the tests only read CSV files.
"""
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.documents import Document

from knowledge_base_loader import KB_FILE, MANIFEST_FILE, SETTINGS_FILE, KBLoader
from settings import load_settings
from utils import sha256_file

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DATA = FOLDER / "data"
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]
READING = f"Reading {KB_FILE.resolve()} (utf-8): 8 columns ({', '.join(COLUMNS)})"   # the first log line
SETTINGS = load_settings(SETTINGS_FILE)
NOON = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
# The sensitive values in the messy file: none may ever be printed, logged or kept
SENSITIVE = ["jane.doe@example.com", "555-010-0142", "4111 1111 1111 1111", "S3cr3t-Pass", "Winter2026!",
             "123-45-6789"]


def loader(path: Path, **options) -> KBLoader:
    """A loader with the project's settings, and a clock stopped at noon, so every load gives the same Documents."""
    return KBLoader(path, settings=SETTINGS, clock=lambda: NOON, **options)


def issues(found):
    """A report's list as (row, lines, message), the easiest form to compare."""
    return [(issue.row, issue.lines, issue.message) for issue in found]


def write_csv(path, text):
    path.write_text(text, encoding="utf-8")
    return path


docs = loader(KB_FILE).load()
messy_loader = loader(DATA / "sample_it_kb_messy.csv")
messy = messy_loader.load()
labels_loader = loader(DATA / "sample_it_kb_labels.csv")
labelled = labels_loader.load()


# -------------------------------------------------
# The Documents: Text, Labels, ID and Where Each Came From
# -------------------------------------------------

def test_the_paths_point_at_the_files_next_to_the_script():
    assert (KB_FILE, SETTINGS_FILE, MANIFEST_FILE) == (DATA / "sample_it_kb.csv", FOLDER / "kb_settings.toml",
                                                        DATA / "manifest.json")
    assert KB_FILE.is_file() and SETTINGS_FILE.is_file()


def test_there_is_one_document_per_article():
    assert len(docs) == 10
    assert all(isinstance(doc, Document) for doc in docs)


def test_the_text_is_the_text_fields_as_labelled_blocks_in_order():
    for doc in docs:
        blocks = doc.page_content.split("\n\n")
        assert [block.split(": ", 1)[0] for block in blocks] == ["Title", "Problem", "Resolution", "Notes"]
    assert docs[0].page_content.startswith("Title: VPN Connection Timeout\n\nProblem: Users experience timeout")


def test_the_labels_are_metadata_typed_and_the_text_isnt():
    metadata = docs[0].metadata
    assert {name: metadata[name] for name in ("title", "system", "category", "priority", "tags", "visibility",
                                              "team")} == {
        "title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access", "priority": "High",
        "tags": ["vpn", "timeout", "remote", "connection"], "visibility": None, "team": None}
    assert "problem" not in metadata and "resolution" not in metadata


def test_each_document_says_where_and_when_it_came_from_and_by_which_code():
    metadata = docs[0].metadata
    assert list(metadata) == ["doc_id", "title", "system", "category", "priority", "tags", "visibility", "team",
                              "source", "source_sha256", "loaded_at", "loader_version", "row", "content_hash"]
    assert (metadata["source"], metadata["source_sha256"]) == ("sample_it_kb.csv", sha256_file(KB_FILE))
    assert (metadata["loaded_at"], metadata["loader_version"], metadata["row"]) == \
        ("2026-10-30T12:00:00+00:00", "advanced-08", 0)
    assert len(metadata["content_hash"]) == 16


def test_each_article_has_its_own_id():
    ids = [doc.metadata["doc_id"] for doc in docs]
    assert len(set(ids)) == 10
    assert all(the_id.startswith("kb-") and len(the_id) == 19 for the_id in ids)


def test_ids_stay_the_same_when_the_file_is_re_sorted():
    reordered = loader(DATA / "sample_it_kb_reordered.csv").load()
    assert [doc.metadata["title"] for doc in reordered] != [doc.metadata["title"] for doc in docs]
    assert {doc.metadata["title"]: doc.metadata["doc_id"] for doc in reordered} == \
        {doc.metadata["title"]: doc.metadata["doc_id"] for doc in docs}


def test_an_id_column_in_the_export_is_used_as_the_id(tmp_path):
    path = write_csv(tmp_path / "ids.csv", "id,title,problem,resolution\nKB0012,VPN,Slow,Restart\n")
    assert loader(path).load()[0].metadata["doc_id"] == "KB0012"


def test_the_fingerprints_hash_each_field_of_each_kept_article():
    vpn = docs[0].metadata["doc_id"]
    assert sorted(messy_loader.fingerprints) == sorted(doc.metadata["doc_id"] for doc in messy)
    first = loader(KB_FILE)
    first.load()
    assert list(first.fingerprints[vpn]) == ["title", "problem", "resolution", "notes", "system", "category",
                                             "priority", "tags", "visibility", "team"]


# -------------------------------------------------
# The Loader: Configure, Then Load
# -------------------------------------------------

def test_the_constructor_stores_the_configuration_and_reads_nothing(tmp_path):
    configured = KBLoader(str(tmp_path / "missing.csv"), settings=SETTINGS)   # no error yet: nothing is opened
    assert (configured.data_path, configured.encoding) == (tmp_path / "missing.csv", "utf-8")
    assert configured.settings is SETTINGS


def test_load_gives_the_same_documents_as_lazy_load():
    same = loader(KB_FILE)
    assert same.load() == list(same.lazy_load()) == docs


def test_a_missing_file_fails_when_loading_with_its_path_in_the_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="Knowledge base file not found: .*missing.csv"):
        loader(tmp_path / "missing.csv").load()


def test_an_empty_file_fails_because_it_has_no_header_row(tmp_path):
    with pytest.raises(ValueError, match="empty, with no header row"):
        loader(write_csv(tmp_path / "empty.csv", "")).load()


def test_a_file_that_isnt_utf8_fails_with_a_message_saying_so(tmp_path):
    path = tmp_path / "utf16.csv"
    path.write_text("title,problem,resolution\nA,B,C\n", encoding="utf-16")   # what PowerShell 5's `>` writes
    with pytest.raises(ValueError, match="isn't utf-8 text"):
        loader(path).load()
    assert loader(path, encoding="utf-16").load()[0].page_content == "Title: A\n\nProblem: B\n\nResolution: C"


def test_any_csv_with_the_required_columns_can_be_read(tmp_path):
    path = write_csv(tmp_path / "two.csv", "title,problem,resolution\nPrinter jam,Paper stuck,Open the tray\n")
    doc = loader(path).load()[0]
    assert doc.page_content == "Title: Printer jam\n\nProblem: Paper stuck\n\nResolution: Open the tray"
    assert (doc.metadata["system"], doc.metadata["tags"], doc.metadata["row"]) == (None, [], 0)


def test_a_column_the_settings_dont_name_is_logged_and_not_read(tmp_path, caplog):
    path = write_csv(tmp_path / "extra.csv", "title,problem,resolution,owner\nA,B,C,Ana\n")
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        doc = loader(path).load()[0]
    assert "Not read: column owner (kb_settings.toml gives it no field)" in caplog.messages
    assert "Ana" not in doc.page_content and "owner" not in doc.metadata


def test_renamed_columns_need_only_a_settings_change(tmp_path):
    text = SETTINGS_FILE.read_text(encoding="utf-8").replace('title = "title"', 'title = "Summary"')
    settings = load_settings(write_csv(tmp_path / "kb_settings.toml", text))
    path = write_csv(tmp_path / "renamed.csv", "Summary,problem,resolution\nVPN,Slow,Restart\n")
    assert KBLoader(path, settings=settings).load()[0].metadata["title"] == "VPN"
    with pytest.raises(ValueError, match=r"missing required columns \(title\)"):
        loader(path).load()                                     # the project's settings look for "title"


def test_the_sample_file_passes_every_check_without_a_warning(caplog):
    checked = loader(KB_FILE)
    with caplog.at_level(logging.DEBUG, logger="knowledge_base_loader"):
        assert len(checked.load()) == 10
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
    assert (checked.report.rows, checked.report.kept, checked.report.blank_lines) == (10, 10, 4)
    assert not checked.report.has_issues()


def test_the_column_names_are_cleaned_of_an_excel_bom_and_spaces(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_text("title, problem ,resolution\nA,B,C\n", encoding="utf-8-sig")   # Excel's "CSV UTF-8"
    assert loader(path).load()[0].page_content == "Title: A\n\nProblem: B\n\nResolution: C"


@pytest.mark.parametrize("text, message", [
    ("title,problem,resolution,title\nA,B,C,D\n", r"a column more than once \(title\)"),
    ("title,problem\nA,B\n", r"missing required columns \(resolution\)"),
    ("title,problem,resolution,\nA,B,C,D\n", r"a column with no name \(column 4\)"),
    ("title,problem,resolution\nA,B,C\nD,E," + "x" * 140_000 + "\n",
     r"can't be read as CSV at line 3 \(field larger than field limit"),
], ids=["named twice", "required column missing", "unnamed column", "field too big"])
def test_a_header_or_file_that_cant_be_used_fails(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        loader(write_csv(tmp_path / "bad.csv", text)).load()


# -------------------------------------------------
# The Messy File: Advanced/01's Checks, Each Row Accounted For
# -------------------------------------------------

def test_the_messy_file_keeps_6_of_14_rows_and_every_row_is_accounted_for():
    report = messy_loader.report
    assert (report.rows, report.kept, report.blank_lines) == (14, 6, 1)
    kept = [doc.metadata["row"] for doc in messy]
    assert kept == [0, 7, 8, 9, 10, 12]                            # rows keep their place in the file
    removed = [issue.row for issue in report.skipped + report.duplicates]
    assert sorted(kept + removed) == list(range(14))               # nothing dropped without being reported


def test_rows_that_cant_be_trusted_are_skipped_and_shown_with_why():
    assert issues(messy_loader.report.skipped) == [
        (3, "5", "the same ID as row 0 (" + messy[0].metadata["doc_id"] + "), with different content: the same "
                 "title and system: give one a different title, or the file an id column"),
        (4, "6", "9 fields, but the header has 8: usually a comma inside a value that isn't in quotes"),
        (5, "7", "3 fields, but the header has 8"),
        (6, "8", "no value for resolution"),
        (11, "14", "doesn't fit the schema: priority: Input should be 'Low', 'Medium', 'High' or 'Critical' "
                   "(given \"Urgent\")"),
        (13, "16-18", "2 fields, but the header has 8: a quote that's never closed made lines 16-18 into one row"),
    ]
    shown = [issue.content for issue in messy_loader.report.skipped]
    assert shown[1].endswith("| extra 1: printer;network")
    assert "\\nPrinter Not Found,Printers do not show up" in shown[5]   # the rows a missing quote swallowed


def test_duplicates_are_removed_and_shown_with_the_row_they_copy():
    assert issues(messy_loader.report.duplicates) == [
        (1, "3", "the same as row 0: VPN Connection Timeout"),
        (2, "4", "the same as row 0 apart from upper and lower case or spacing: vpn connection timeout"),
    ]


def test_sensitive_values_are_redacted_and_reported_masked():
    assert issues(messy_loader.report.redacted) == [
        (7, "10", "problem: email address j***@example.com (PII)"),
        (7, "10", "problem: phone number ***-***-0142 (PII)"),
        (8, "11", "notes: card number **** 1111 (PCI)"),
        (9, "12", "resolution: password in a URL (hidden, 11 characters) (secret: change it, it's been exposed)"),
        (9, "12", "notes: password or key (hidden, 11 characters) (secret: change it, it's been exposed)"),
        (10, "13", "notes: Social Security number ***-**-6789 (PII)"),
    ]
    text = {doc.metadata["row"]: doc.page_content for doc in messy}
    assert "Problem: User [REDACTED:EMAIL] (call back on [REDACTED:PHONE]) cannot send a 30 MB file" in text[7]
    assert "postgres://kb_app:[REDACTED:PASSWORD]@db01:5432/kb" in text[9]


def test_no_sensitive_value_is_kept_in_any_document():
    for doc in messy:
        for value in SENSITIVE:
            assert value not in doc.page_content and value not in str(doc.metadata)


def test_an_invisible_character_is_removed_and_flagged():
    assert issues(messy_loader.report.flagged) == [(12, "15", "1 invisible character removed from title")]
    assert "WiFi Connectivity Issues Office" in [doc.metadata["title"] for doc in messy]


def test_one_warning_line_counts_what_the_checks_found(caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        loader(DATA / "sample_it_kb_messy.csv").load()
    assert caplog.messages[-1] == ("Data checks on sample_it_kb_messy.csv: 6 skipped, 2 duplicates removed, "
                                   "0 normalized, 6 sensitive values redacted, 1 flagged (the report lists each one)")


# -------------------------------------------------
# The Labels File: The Schema and One Spelling per Value
# -------------------------------------------------

def test_the_labels_file_keeps_6_of_11_rows_and_every_row_is_accounted_for():
    report = labels_loader.report
    assert (report.rows, report.kept) == (11, 6)
    kept = [doc.metadata["row"] for doc in labelled]
    assert kept == [0, 1, 2, 3, 4, 10]
    assert sorted(kept + [issue.row for issue in report.skipped]) == list(range(11))


def test_an_article_that_breaks_the_schema_is_skipped_naming_the_field_and_why():
    assert issues(labels_loader.report.skipped)[:4] == [
        (5, "7", "doesn't fit the schema: priority: Input should be 'Low', 'Medium', 'High' or 'Critical' "
                 "(given \"Urgent\")"),
        (6, "8", "doesn't fit the schema: visibility: Input should be 'public', 'internal' or 'restricted' "
                 "(given \"secret\")"),
        (7, "9", "doesn't fit the schema: title: String should have at most 200 characters"),
        (8, "10", "no value for resolution"),
    ]


def test_two_articles_with_one_id_keep_the_first_and_skip_the_second():
    row, lines, message = issues(labels_loader.report.skipped)[4]
    assert (row, lines) == (9, "11")
    assert message.startswith(f"the same ID as row 0 ({labelled[0].metadata['doc_id']}), with different content")


def test_three_spellings_of_one_system_become_one_and_each_change_is_reported():
    systems = {doc.metadata["row"]: doc.metadata["system"] for doc in labelled}
    assert (systems[1], systems[2], systems[3], systems[10]) == ("WiFi", "WiFi", "WiFi", "Microsoft Teams")
    assert issues(labels_loader.report.normalized) == [
        (1, "3", 'priority: "high" made "High"'),
        (1, "3", 'system: "Wi-Fi" made "WiFi"'),
        (2, "4", 'system: "wifi" made "WiFi"'),
        (2, "4", 'category: "Networking" made "Network"'),
        (3, "5", 'priority: "P1" made "Critical"'),
        (10, "12", 'system: "Teams" made "Microsoft Teams"'),
    ]


def test_tags_visibility_and_team_are_typed_labels():
    metadata = {doc.metadata["row"]: doc.metadata for doc in labelled}
    assert metadata[1]["tags"] == ["wifi", "meeting rooms"]                       # "WiFi; wifi ;Meeting Rooms;;"
    assert (metadata[1]["visibility"], metadata[1]["team"]) == ("public", None)  # "Public", blank
    assert (metadata[10]["visibility"], metadata[10]["team"]) == ("restricted", "Collaboration Tools")


def test_a_system_with_no_spelling_is_kept_as_written_and_flagged():
    assert issues(labels_loader.report.flagged) == [
        (4, "6", 'system "Kiosk" has no spelling in kb_settings.toml: kept as written')]
    assert [doc.metadata["system"] for doc in labelled if doc.metadata["row"] == 4] == ["Kiosk"]


def test_a_title_used_for_two_systems_is_two_articles_and_flagged(tmp_path):
    path = write_csv(tmp_path / "titles.csv", "title,problem,resolution,system\nSlow,A,B,VPN\nSlow,C,D,WiFi\n")
    used_twice = loader(path)
    assert len({doc.metadata["doc_id"] for doc in used_twice.load()}) == 2
    assert issues(used_twice.report.flagged) == [(1, "3", "the same title as row 0, with different content: Slow")]


# -------------------------------------------------
# Logging
# -------------------------------------------------

def test_loading_logs_the_columns_and_the_total(caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        loader(KB_FILE).load()
    assert caplog.messages == [READING, "Read 10 documents from sample_it_kb.csv"]


def test_debug_logs_one_line_per_row(caplog):
    with caplog.at_level(logging.DEBUG, logger="knowledge_base_loader"):
        loader(KB_FILE).load()
    rows = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert rows[0] == f"Row 0: {docs[0].metadata['doc_id']} VPN Connection Timeout"
    assert len(rows) == 10


def test_a_header_with_no_rows_gives_no_documents_and_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        assert loader(write_csv(tmp_path / "header.csv", "title,problem,resolution\n")).load() == []
    assert caplog.records[-1].getMessage() == "header.csv has a header row but no articles"

