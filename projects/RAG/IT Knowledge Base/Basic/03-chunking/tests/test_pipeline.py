"""
Tests for pipeline.py: the CSV file read into 10 Documents, with each article's text and labels kept apart; the 10
articles cut into chunks, each no longer than the chunk size, each keeping its article's metadata and where in the
article it starts; and what it prints when it's run, with the default chunk size and another one, from any folder,
and that it's the only file that runs anything.

No key, no network: the tests only read the CSV file, and run pipeline.py as its own process.
"""
import subprocess
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from pipeline import CHUNK_OVERLAP, CHUNK_SIZE, KB_FILE, KBLoader, load_documents, split_documents
from utils import print_chunks

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DOCS = load_documents()
STEPS = "Step 1: Read the knowledge base: 10 documents\nStep 2: Chunk\n"


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


# --- The chunks ---

def test_512_characters_cut_each_article_into_2_or_3_chunks():
    assert (CHUNK_SIZE, CHUNK_OVERLAP) == (512, 50)
    chunks = split_documents(DOCS)
    assert len(chunks) == 28
    per_article = [sum(c.metadata["doc_id"] == d.metadata["doc_id"] for c in chunks) for d in DOCS]
    assert set(per_article) == {2, 3}


@pytest.mark.parametrize("size", [200, 512, 1000])
def test_no_chunk_is_longer_than_the_chunk_size(size):
    assert all(len(chunk.page_content) <= size for chunk in split_documents(DOCS, chunk_size=size))


def test_each_chunk_keeps_its_articles_metadata_and_where_it_starts():
    by_id = {doc.metadata["doc_id"]: doc for doc in DOCS}
    for chunk in split_documents(DOCS):
        article = by_id[chunk.metadata["doc_id"]]
        start = chunk.metadata["start_index"]
        assert {k: v for k, v in chunk.metadata.items() if k != "start_index"} == article.metadata
        assert article.page_content[start:start + len(chunk.page_content)] == chunk.page_content


def test_chunks_break_between_sections_first():
    # The empty lines between Title, Problem, Resolution and Notes are the first places the splitter tries.
    for chunk in split_documents(DOCS):
        assert chunk.page_content.split(": ", 1)[0] in {"Title", "Problem", "Resolution", "Notes"}


def test_1000_characters_keep_every_article_whole():
    chunks = split_documents(DOCS, chunk_size=1000)
    assert [chunk.page_content for chunk in chunks] == [doc.page_content for doc in DOCS]


# --- Running it ---

def run(*args, cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "pipeline.py"), *args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_steps_then_every_chunk(capsys):
    print_chunks(DOCS, split_documents(DOCS), CHUNK_SIZE)
    assert run() == STEPS + capsys.readouterr().out


def test_a_number_after_pipeline_py_is_the_chunk_size(capsys):
    print_chunks(DOCS, split_documents(DOCS, chunk_size=200), 200)
    printed = run("200")
    assert printed == STEPS + capsys.readouterr().out
    assert printed.startswith(STEPS + "10 articles -> 49 chunks of at most 200 characters\n")


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    assert run(cwd=tmp_path) == run()


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # utils.py only defines the helper
