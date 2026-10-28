"""
Tests for pipeline.py: the CSV file read into 10 Documents, with each article's text and labels kept apart, and what
it prints when it's run, from any folder, and that it's the only file that runs anything.

No key, no network: the tests only read the CSV file, and run pipeline.py as its own process.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from pipeline import KB_FILE, METADATA_COLUMNS, TEXT_COLUMNS, KBLoader, load_documents
from utils import print_documents

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DOCS = load_documents()


# --- The Documents ---

def test_one_document_per_article():
    assert KB_FILE == FOLDER / "data" / "sample_it_kb.csv"
    assert len(DOCS) == 10
    assert all(isinstance(doc, Document) for doc in DOCS)


def test_the_text_has_title_problem_resolution_and_notes_in_order():
    for doc in DOCS:
        sections = doc.page_content.split("\n\n")
        assert [section.split(": ", 1)[0] for section in sections] == ["Title", "Problem", "Resolution", "Notes"]
        assert all(section.split(": ", 1)[1].strip() for section in sections)     # no section is empty


def test_the_labels_are_metadata_not_text():
    assert DOCS[0].metadata == {"doc_id": "0", "title": "VPN Connection Timeout", "system": "VPN",
                                "category": "Remote Access", "priority": "High",
                                "tags": "vpn;timeout;remote;connection"}
    assert [doc.metadata["doc_id"] for doc in DOCS] == [str(n) for n in range(10)]
    for doc in DOCS:
        assert "System:" not in doc.page_content and "Priority:" not in doc.page_content


def test_making_the_loader_reads_nothing_and_load_reads_the_file(tmp_path):
    loader = KBLoader(tmp_path / "missing.csv")    # no error yet: the loader hasn't opened the file
    with pytest.raises(FileNotFoundError):
        loader.load()                              # load() is what opens it


# --- Running it ---

def run(cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "pipeline.py")], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_step_then_every_document(capsys):
    print_documents(DOCS, TEXT_COLUMNS, METADATA_COLUMNS)
    assert run() == "Step 1: Read the knowledge base\n" + capsys.readouterr().out


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    assert run(cwd=tmp_path) == run()


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # utils.py only defines the helper
