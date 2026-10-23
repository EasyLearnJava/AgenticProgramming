"""
Tests for knowledge_base.py: the CSV file read into 10 Documents, with each article's text and labels kept apart.
No key, no network.
"""
from pathlib import Path

import pytest
from langchain_core.documents import Document

from knowledge_base import KB_FILE, KBLoader, load_documents

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DOCS = load_documents()


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
