"""
Tests for IT Knowledge Base step 1: the LangChain Documents knowledge_base_loader.py reads from
data/sample_it_kb.csv, the checks on the data and their report, what it logs, how it fails, and what the script
prints. data/sample_it_kb_messy.csv has one row for each problem the checks look for.

    KBLoader(KB_FILE).load()  ->  10 Documents, one per article;
                                  page_content "title: ...\nproblem: ...\n...", metadata {"source", "row"}

No key, no network: the tests only read CSV files and run the script.
Run them:   python -m pytest   ->   62 passed        (add -v for one line per test)
"""
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from knowledge_base_loader import KB_FILE, KBLoader, main, parse_args

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]
READING = f"Reading {KB_FILE.resolve()} (utf-8): 8 columns ({', '.join(COLUMNS)})"   # the first log line
MESSY_FILE = FOLDER / "data" / "sample_it_kb_messy.csv"
# The sensitive values in the messy file: none may ever be printed, logged or kept
SENSITIVE = ["jane.doe@example.com", "555-010-0142", "4111 1111 1111 1111", "S3cr3t-Pass", "Winter2026!",
             "123-45-6789"]

docs = KBLoader(KB_FILE).load()
messy_loader = KBLoader(MESSY_FILE)
messy = messy_loader.load()
report = messy_loader.report


def issues(found):
    """A report's list as (row, lines, message), the easiest form to compare."""
    return [(issue.row, issue.lines, issue.message) for issue in found]


def run_script(*args, cwd=FOLDER):
    """Runs knowledge_base_loader.py as its own process, started in the folder `cwd`, and gives back the process."""
    # sys.executable is the Python running these tests (the venv's), so the script gets the same packages.
    return subprocess.run([sys.executable, str(FOLDER / "knowledge_base_loader.py"), *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")


def write_csv(path, text):
    path.write_text(text, encoding="utf-8")
    return path


# -------------------------------------------------
# The Documents
# -------------------------------------------------

def test_the_path_points_at_the_csv_next_to_the_script():
    assert KB_FILE == FOLDER / "data" / "sample_it_kb.csv"
    assert KB_FILE.is_file()


def test_there_is_one_document_per_article():
    assert len(docs) == 10
    assert all(isinstance(doc, Document) for doc in docs)


def test_each_document_has_every_column_as_a_line_in_order():
    for doc in docs:
        lines = doc.page_content.splitlines()
        assert [line.split(": ", 1)[0] for line in lines] == COLUMNS
        assert all(line.split(": ", 1)[1].strip() for line in lines)      # no column is empty


def test_the_metadata_names_the_file_and_the_row():
    assert [doc.metadata for doc in docs] == [{"source": "sample_it_kb.csv", "row": n} for n in range(10)]


def test_the_first_document_is_the_vpn_timeout():
    lines = docs[0].page_content.splitlines()
    assert lines[0] == "title: VPN Connection Timeout"
    assert "system: VPN" in lines
    assert "category: Remote Access" in lines


# -------------------------------------------------
# The Loader: Configure, Then Load
# -------------------------------------------------

def test_the_constructor_stores_the_configuration_and_reads_nothing(tmp_path):
    loader = KBLoader(str(tmp_path / "missing.csv"))     # no error yet: the loader hasn't opened the file
    assert loader.data_path == tmp_path / "missing.csv"  # a str is turned into a Path
    assert loader.encoding == "utf-8"
    assert loader.required_columns == ("title", "problem", "resolution")


def test_load_gives_the_same_documents_as_lazy_load():
    loader = KBLoader(KB_FILE)
    assert loader.load() == list(loader.lazy_load()) == docs


def test_a_missing_file_fails_when_loading_with_its_path_in_the_message(tmp_path):
    loader = KBLoader(tmp_path / "missing.csv")
    with pytest.raises(FileNotFoundError, match="Knowledge base file not found: .*missing.csv"):
        loader.load()                                  # load() is what opens it


def test_an_empty_file_fails_because_it_has_no_header_row(tmp_path):
    with pytest.raises(ValueError, match="empty, with no header row"):
        KBLoader(write_csv(tmp_path / "empty.csv", "")).load()


def test_a_file_that_isnt_utf8_fails_with_a_message_saying_so(tmp_path):
    path = tmp_path / "utf16.csv"
    path.write_text("title,problem,resolution\nA,B,C\n", encoding="utf-16")   # what PowerShell 5's `>` writes
    with pytest.raises(ValueError, match="isn't utf-8 text"):
        KBLoader(path).load()


def test_the_encoding_is_part_of_the_configuration(tmp_path):
    path = tmp_path / "utf16.csv"
    path.write_text("title,problem,resolution\nA,B,C\n", encoding="utf-16")
    assert KBLoader(path, encoding="utf-16").load()[0].page_content == "title: A\nproblem: B\nresolution: C"


def test_any_csv_with_the_required_columns_can_be_read(tmp_path):
    text = ("title,problem,resolution,system\n"
            "Printer jam,Paper stuck,Open the tray,Printing\n"
            "Disk full,No space,Clean up,Storage\n")
    loaded = KBLoader(write_csv(tmp_path / "two.csv", text)).load()
    assert [doc.page_content.splitlines()[0] for doc in loaded] == ["title: Printer jam", "title: Disk full"]
    assert [doc.metadata for doc in loaded] == [{"source": "two.csv", "row": 0}, {"source": "two.csv", "row": 1}]


def test_the_required_columns_are_part_of_the_configuration(tmp_path):
    path = write_csv(tmp_path / "two.csv", "title,system\nPrinter jam,Printing\n")
    with pytest.raises(ValueError, match=r"missing required columns \(problem, resolution\)"):
        KBLoader(path).load()
    assert KBLoader(path, required_columns=("title",)).load()[0].page_content == "title: Printer jam\nsystem: Printing"


# -------------------------------------------------
# Checking the Data
# -------------------------------------------------

def test_the_sample_file_passes_every_check_without_a_warning(caplog):
    loader = KBLoader(KB_FILE)
    with caplog.at_level(logging.DEBUG, logger="knowledge_base_loader"):
        assert len(loader.load()) == 10
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []
    assert (loader.report.rows, loader.report.kept, loader.report.blank_lines) == (10, 10, 4)
    assert not loader.report.has_issues()


def test_the_column_names_are_cleaned_of_an_excel_bom_and_spaces(tmp_path):
    path = tmp_path / "excel.csv"
    path.write_text("title, problem ,resolution\nA,B,C\n", encoding="utf-8-sig")   # Excel's "CSV UTF-8"
    assert KBLoader(path).load()[0].page_content == "title: A\nproblem: B\nresolution: C"


def test_a_column_named_twice_fails(tmp_path):
    with pytest.raises(ValueError, match=r"a column more than once \(title\)"):
        KBLoader(write_csv(tmp_path / "twice.csv", "title,problem,resolution,title\nA,B,C,D\n")).load()


def test_a_missing_required_column_fails(tmp_path):
    with pytest.raises(ValueError, match=r"missing required columns \(resolution\): .*no_fix.csv"):
        KBLoader(write_csv(tmp_path / "no_fix.csv", "title,problem\nA,B\n")).load()


def test_a_column_with_no_name_fails(tmp_path):
    with pytest.raises(ValueError, match=r"a column with no name \(column 4\)"):
        KBLoader(write_csv(tmp_path / "trailing.csv", "title,problem,resolution,\nA,B,C,D\n")).load()


def test_a_field_too_big_for_the_csv_reader_fails_with_its_line(tmp_path):
    path = write_csv(tmp_path / "huge.csv", "title,problem,resolution\nA,B,C\nD,E," + "x" * 140_000 + "\n")
    with pytest.raises(ValueError, match=r"can't be read as CSV at line 3 \(field larger than field limit"):
        KBLoader(path).load()


def test_values_are_trimmed_and_a_blank_optional_value_is_kept(tmp_path):
    loaded = KBLoader(write_csv(tmp_path / "spaces.csv", "title,problem,resolution,notes\n  A  , B ,C,\n")).load()
    assert loaded[0].page_content == "title: A\nproblem: B\nresolution: C\nnotes: "


# -------------------------------------------------
# The Messy File: Every Row Kept, Skipped, Removed, Redacted or Flagged Is Reported
# -------------------------------------------------

def test_the_messy_file_keeps_8_of_14_rows_and_every_row_is_accounted_for():
    assert (report.rows, report.kept, report.blank_lines) == (14, 8, 1)
    kept = [doc.metadata["row"] for doc in messy]
    assert kept == [0, 3, 7, 8, 9, 10, 11, 12]                    # rows keep their place in the file
    removed = [issue.row for issue in report.skipped + report.duplicates]
    assert sorted(kept + removed) == list(range(14))               # nothing dropped without being reported


def test_rows_that_cant_be_trusted_are_skipped_and_shown_with_why():
    assert issues(report.skipped) == [
        (4, "6", "9 fields, but the header has 8: usually a comma inside a value that isn't in quotes"),
        (5, "7", "3 fields, but the header has 8"),
        (6, "8", "no value for resolution"),
        (13, "16-18", "2 fields, but the header has 8: a quote that's never closed made lines 16-18 into one row"),
    ]
    shown = [issue.content for issue in report.skipped]
    assert shown[0].startswith("title: Printer Not Found | problem: Users cannot see the office printer | "
                               "resolution: Check the printer is on | system: then re-add it in Settings")
    assert shown[0].endswith("| extra 1: printer;network")
    assert "\\nPrinter Not Found,Printers do not show up" in shown[3]   # the rows a missing quote swallowed


def test_duplicates_are_removed_and_shown_with_the_row_they_copy():
    assert issues(report.duplicates) == [
        (1, "3", "the same as row 0: VPN Connection Timeout"),
        (2, "4", "the same as row 0 apart from upper and lower case or spacing: vpn connection timeout"),
    ]


def test_sensitive_values_are_redacted_and_reported_masked():
    assert issues(report.redacted) == [
        (7, "10", "problem: email address j***@example.com (PII)"),
        (7, "10", "problem: phone number ***-***-0142 (PII)"),
        (8, "11", "notes: card number **** 1111 (PCI)"),
        (9, "12", "resolution: password in a URL (hidden, 11 characters) (secret: change it, it's been exposed)"),
        (9, "12", "notes: password or key (hidden, 11 characters) (secret: change it, it's been exposed)"),
        (10, "13", "notes: Social Security number ***-**-6789 (PII)"),
    ]
    text = {doc.metadata["row"]: doc.page_content for doc in messy}
    assert "problem: User [REDACTED:EMAIL] (call back on [REDACTED:PHONE]) cannot send a 30 MB file" in text[7]
    assert "postgres://kb_app:[REDACTED:PASSWORD]@db01:5432/kb" in text[9]


def test_no_sensitive_value_is_kept_in_any_document():
    for doc in messy:
        for value in SENSITIVE:
            assert value not in doc.page_content


def test_rows_a_person_should_look_at_are_kept_and_flagged():
    assert issues(report.flagged) == [
        (3, "5", "the same title as row 0, with different content: VPN Connection Timeout"),
        (11, "14", 'priority is "Urgent", not one of Low, Medium, High, Critical'),
        (12, "15", "1 invisible character removed from title"),
    ]
    titles = [doc.page_content.splitlines()[0] for doc in messy]
    assert "title: Microsoft Teams Audio Issues" in titles                 # spaces trimmed
    assert "title: WiFi Connectivity Issues Office" in titles              # the zero-width space removed


def test_the_allowed_values_are_part_of_the_configuration():
    loader = KBLoader(MESSY_FILE, allowed_values={"priority": ("Low", "Medium", "High", "Critical", "Urgent")})
    loader.load()
    assert [issue.row for issue in loader.report.flagged] == [3, 12]
    assert KBLoader("x.csv").allowed_values == {"priority": ("Low", "Medium", "High", "Critical")}


def test_one_warning_line_counts_what_the_checks_found(caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        KBLoader(MESSY_FILE).load()
    assert caplog.messages[-1] == ("Data checks on sample_it_kb_messy.csv: 4 skipped, 2 duplicates removed, "
                                   "6 sensitive values redacted, 3 flagged (the report lists each one)")


# -------------------------------------------------
# Logging
# -------------------------------------------------

def test_loading_logs_the_columns_and_the_total(caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        KBLoader(KB_FILE).load()
    assert caplog.messages == [READING, "Read 10 documents from sample_it_kb.csv"]


def test_debug_logs_one_line_per_row(caplog):
    with caplog.at_level(logging.DEBUG, logger="knowledge_base_loader"):
        KBLoader(KB_FILE).load()
    rows = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert rows[0] == "Row 0: title: VPN Connection Timeout"
    assert len(rows) == 10


def test_a_header_with_no_rows_gives_no_documents_and_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="knowledge_base_loader"):
        assert KBLoader(write_csv(tmp_path / "header.csv", "title,problem,resolution\n")).load() == []
    assert [(record.levelname, record.getMessage()) for record in caplog.records][-1] == \
        ("WARNING", "header.csv has a header row but no articles")


# -------------------------------------------------
# The Script
# -------------------------------------------------

def test_the_options_default_to_the_sample_file_and_info():
    args = parse_args([])
    assert (args.data_path, args.log_level) == (KB_FILE, "INFO")


def test_main_returns_1_and_logs_the_reason_when_the_file_is_missing(tmp_path, caplog, capsys):
    assert main(["--data-path", str(tmp_path / "missing.csv")]) == 1
    assert "Knowledge base file not found" in caplog.text
    assert capsys.readouterr().out == ""               # nothing printed: there's nothing to show


def test_running_the_script_prints_the_titles_then_every_document():
    result = run_script()
    printed = result.stdout
    assert result.returncode == 0
    assert printed.startswith("10 documents\nrow 0  title: VPN Connection Timeout\n")
    assert ("row 9  title: Microsoft Teams Audio Issues\n\n"
            "Document 1 of 10\nText (page_content):\ntitle: VPN Connection Timeout\n") in printed
    assert ("tags: vpn;timeout;remote;connection\n\n"
            "Where it came from (metadata):\n{'source': 'sample_it_kb.csv', 'row': 0}\n\n"
            "Document 2 of 10\n") in printed
    headings = [line for line in printed.splitlines() if line.startswith("Document ")]
    assert headings == [f"Document {n} of 10" for n in range(1, 11)]
    assert "\n\n\n" not in printed                  # never more than one blank line in a row
    assert printed.endswith("tags: teams;audio;collaboration;windows\n\n"
                            "Where it came from (metadata):\n{'source': 'sample_it_kb.csv', 'row': 9}\n\n"
                            "Data checks: 10 rows read, 10 kept (4 blank lines ignored)\n"
                            "Nothing skipped, removed, redacted or flagged.\n")
    # The log goes to stderr, apart from the printed output: one line when reading starts, one at the end.
    assert [line.split(" ", 2)[2] for line in result.stderr.splitlines()] == [
        f"INFO {READING}",
        "INFO Read 10 documents from sample_it_kb.csv",
    ]


def test_the_script_prints_the_report_for_the_messy_file_and_never_a_sensitive_value():
    result = run_script("--data-path", str(MESSY_FILE))
    assert result.returncode == 0
    report_part = result.stdout.split("\nData checks: ", 1)[1]
    assert report_part.startswith("14 rows read, 8 kept (1 blank line ignored)\n")
    for heading in ["Skipped, not read: each can't be trusted as it is (4)",
                    "Removed as duplicates: the first copy is kept (2)",
                    "Sensitive values redacted: replaced in the text, never shown in full (6)",
                    "Flagged, kept: a person should look at these (3)"]:
        assert f"\n{heading}\n" in report_part
    assert "  row 13 (lines 16-18): 2 fields, but the header has 8" in report_part
    for value in SENSITIVE:
        assert value not in result.stdout and value not in result.stderr


def test_the_script_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the script still finds the file.
    assert run_script(cwd=tmp_path).stdout == run_script().stdout


def test_a_missing_file_ends_the_script_with_exit_code_1_and_no_traceback(tmp_path):
    result = run_script("--data-path", str(tmp_path / "missing.csv"))
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR Knowledge base file not found:" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_missing_required_column_ends_the_script_with_exit_code_1(tmp_path):
    result = run_script("--data-path", str(write_csv(tmp_path / "no_fix.csv", "title,problem\nA,B\n")))
    assert result.returncode == 1
    assert "ERROR Knowledge base file is missing required columns (resolution):" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_relative_path_is_logged_as_the_full_path_it_was_looked_for_at(tmp_path):
    # Started in tmp_path, "data/it_kb.csv" means tmp_path/data/it_kb.csv: the message says so.
    result = run_script("--data-path", "data/it_kb.csv", cwd=tmp_path)
    assert result.returncode == 1
    assert f"Knowledge base file not found: {(tmp_path / 'data' / 'it_kb.csv').resolve()}\n" in result.stderr
