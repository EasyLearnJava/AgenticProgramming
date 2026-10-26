"""
Tests for pipeline.py: the LangChain Documents it reads from data/sample_it_kb.csv, what it prints, and running it.

    load_documents()  ->  10 Documents, one per article;
                          page_content "title: ...\nproblem: ...\n...", metadata {"source", "row"}

No key, no network: the tests only read the CSV file, and make their own two Documents for the printing.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from pipeline import KB_FILE, KBLoader, load_documents, print_documents

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]

docs = load_documents()


# --- The Documents ---

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


# --- The printing ---

TWO_DOCS = [Document(page_content="title: First\nproblem: A", metadata={"source": "kb.csv", "row": 0}),
            Document(page_content="title: Second\nproblem: B", metadata={"source": "kb.csv", "row": 1})]


def test_it_prints_the_count_and_titles_then_every_document(capsys):
    # capsys is pytest's: it catches what the code prints, so the test can read it.
    print_documents(TWO_DOCS)
    assert capsys.readouterr().out == (
        "2 documents\n"
        "row 0  title: First\n"
        "row 1  title: Second\n"
        "\n"
        "Document 1 of 2\nText (page_content):\ntitle: First\nproblem: A\n"
        "\n"
        "Where it came from (metadata):\n{'source': 'kb.csv', 'row': 0}\n"
        "\n"
        "Document 2 of 2\nText (page_content):\ntitle: Second\nproblem: B\n"
        "\n"
        "Where it came from (metadata):\n{'source': 'kb.csv', 'row': 1}\n")


def test_no_documents_prints_only_the_count(capsys):
    print_documents([])
    assert capsys.readouterr().out == "0 documents\n"


# --- Running it ---

def run(args=("pipeline.py",), cwd=FOLDER):
    """Runs Python as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_step_then_the_titles_then_every_document():
    printed = run((str(FOLDER / "pipeline.py"),))
    assert printed.startswith("Step 1: Read the knowledge base\n10 documents\nrow 0  title: VPN Connection Timeout\n")
    assert ("row 9  title: Microsoft Teams Audio Issues\n\n"
            "Document 1 of 10\nText (page_content):\ntitle: VPN Connection Timeout\n") in printed
    headings = [line for line in printed.splitlines() if line.startswith("Document ")]
    assert headings == [f"Document {n} of 10" for n in range(1, 11)]
    assert printed.endswith("Where it came from (metadata):\n{'source': 'sample_it_kb.csv', 'row': 9}\n")


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    script = (str(FOLDER / "pipeline.py"),)
    assert run(script, cwd=tmp_path) == run(script)


def test_importing_the_file_runs_nothing():
    # Imported, as these tests do, it only defines things: main() runs only from `python pipeline.py`
    assert run(("-c", "import pipeline")) == ""
