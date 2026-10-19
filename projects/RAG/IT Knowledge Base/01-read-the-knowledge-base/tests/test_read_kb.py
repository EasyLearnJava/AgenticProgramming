"""
Tests for IT Knowledge Base step 1: the LangChain Documents read_kb.py reads from data/sample_it_kb.csv, and what
the script prints.

    docs  ->  10 Documents, one per article; page_content "title: ...\nproblem: ...\n...", metadata {"source", "row"}

No key, no network: the tests only read the CSV file and run the script.
Run them:   python -m pytest   ->   9 passed        (add -v for one line per test)
"""
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from read_kb import KB_FILE, KBLoader, docs

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]


def run_script(cwd):
    """Runs read_kb.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the script gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "read_kb.py")], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


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


def test_making_the_loader_reads_nothing_and_load_reads_the_file(tmp_path):
    loader = KBLoader(tmp_path / "missing.csv")    # no error yet: the loader hasn't opened the file
    with pytest.raises(FileNotFoundError):
        loader.load()                              # load() is what opens it


def test_load_gives_the_same_documents_as_lazy_load():
    loader = KBLoader(KB_FILE)
    assert loader.load() == list(loader.lazy_load()) == docs


def test_running_the_script_prints_the_titles_then_every_document():
    printed = run_script(cwd=FOLDER)
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


def test_the_script_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the script still finds the file (①).
    assert run_script(cwd=tmp_path) == run_script(cwd=FOLDER)
