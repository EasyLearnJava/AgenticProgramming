"""
Tests for IT Knowledge Base step 1: the LangChain Documents read_kb.py reads from data/sample_it_kb.csv, what it logs,
how it fails, and what the script prints.

    KBLoader(KB_FILE).load()  ->  10 Documents, one per article;
                                  page_content "title: ...\nproblem: ...\n...", metadata {"source", "row"}

No key, no network: the tests only read CSV files and run the script.
Run them:   python -m pytest   ->   21 passed        (add -v for one line per test)
"""
import logging
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from read_kb import KB_FILE, KBLoader, main, parse_args

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]
READING = f"Reading {KB_FILE.resolve()} (utf-8): 8 columns ({', '.join(COLUMNS)})"   # the first log line

docs = KBLoader(KB_FILE).load()


def run_script(*args, cwd=FOLDER):
    """Runs read_kb.py as its own process, started in the folder `cwd`, and gives back the finished process."""
    # sys.executable is the Python running these tests (the venv's), so the script gets the same packages.
    return subprocess.run([sys.executable, str(FOLDER / "read_kb.py"), *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8")


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
    path.write_text("title,system\nA,B\n", encoding="utf-16")   # what PowerShell 5's `>` writes
    with pytest.raises(ValueError, match="isn't utf-8 text"):
        KBLoader(path).load()


def test_the_encoding_is_part_of_the_configuration(tmp_path):
    path = tmp_path / "utf16.csv"
    path.write_text("title,system\nA,B\n", encoding="utf-16")
    assert KBLoader(path, encoding="utf-16").load()[0].page_content == "title: A\nsystem: B"


def test_any_csv_with_a_header_row_can_be_read(tmp_path):
    loaded = KBLoader(write_csv(tmp_path / "two.csv", "title,system\nPrinter jam,Printing\nDisk full,Storage\n")).load()
    assert [doc.page_content for doc in loaded] == ["title: Printer jam\nsystem: Printing",
                                                    "title: Disk full\nsystem: Storage"]
    assert [doc.metadata for doc in loaded] == [{"source": "two.csv", "row": 0}, {"source": "two.csv", "row": 1}]


# -------------------------------------------------
# Logging
# -------------------------------------------------

def test_loading_logs_the_columns_and_the_total(caplog):
    with caplog.at_level(logging.INFO, logger="read_kb"):
        KBLoader(KB_FILE).load()
    assert caplog.messages == [READING, "Read 10 documents from sample_it_kb.csv"]


def test_debug_logs_one_line_per_row(caplog):
    with caplog.at_level(logging.DEBUG, logger="read_kb"):
        KBLoader(KB_FILE).load()
    rows = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert rows[0] == "Row 0: title: VPN Connection Timeout"
    assert len(rows) == 10


def test_a_header_with_no_rows_gives_no_documents_and_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.INFO, logger="read_kb"):
        assert KBLoader(write_csv(tmp_path / "header.csv", "title,problem\n")).load() == []
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
                            "Where it came from (metadata):\n{'source': 'sample_it_kb.csv', 'row': 9}\n")
    # The log goes to stderr, apart from the printed output: one line when reading starts, one at the end.
    assert [line.split(" ", 2)[2] for line in result.stderr.splitlines()] == [
        f"INFO {READING}",
        "INFO Read 10 documents from sample_it_kb.csv",
    ]


def test_the_script_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the script still finds the file.
    assert run_script(cwd=tmp_path).stdout == run_script().stdout


def test_a_missing_file_ends_the_script_with_exit_code_1_and_no_traceback(tmp_path):
    result = run_script("--data-path", str(tmp_path / "missing.csv"))
    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR Knowledge base file not found:" in result.stderr
    assert "Traceback" not in result.stderr


def test_a_relative_path_is_logged_as_the_full_path_it_was_looked_for_at(tmp_path):
    # Started in tmp_path, "data/it_kb.csv" means tmp_path/data/it_kb.csv: the message says so.
    result = run_script("--data-path", "data/it_kb.csv", cwd=tmp_path)
    assert result.returncode == 1
    assert f"Knowledge base file not found: {(tmp_path / 'data' / 'it_kb.csv').resolve()}\n" in result.stderr
