"""
Tests for knowledge_base_loader.py: the LangChain Documents it reads from data/sample_it_kb.csv.

    KBLoader(KB_FILE).load()  ->  10 Documents, one per article;
                                  page_content "title: ...\nproblem: ...\n...", metadata {"source", "row"}

No key, no network: the tests only read the CSV file.
"""
from pathlib import Path

from langchain_core.documents import Document

from knowledge_base_loader import KB_FILE, KBLoader

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]

docs = KBLoader(KB_FILE).load()


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


def test_making_the_loader_reads_nothing(tmp_path):
    KBLoader(tmp_path / "missing.csv")             # no error: the loader hasn't opened the file yet


def test_load_gives_the_same_documents_as_lazy_load():
    loader = KBLoader(KB_FILE)
    assert loader.load() == list(loader.lazy_load()) == docs
