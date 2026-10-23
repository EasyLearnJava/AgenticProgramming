"""
Tests for knowledge_base.py: the CSV file read into 10 Documents, with each article's text and labels kept apart,
and what print_documents(), in utils.py, prints. No key, no network.
"""
from pathlib import Path

import pytest
from langchain_core.documents import Document

from knowledge_base import KB_FILE, KBLoader, load_documents
from utils import print_documents

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


def test_print_documents_prints_the_split_then_every_document(capsys):
    print_documents(DOCS)
    printed = capsys.readouterr().out
    assert printed.startswith("10 documents\ntext:     title, problem, resolution, notes\n"
                              "metadata: doc_id, title, system, category, priority, tags\n\n"
                              "Document 1 of 10\nText (page_content):\nTitle: VPN Connection Timeout\n\nProblem: ")
    assert ("\n\nLabels (metadata):\n{'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', "
            "'category': 'Remote Access', 'priority': 'High', 'tags': 'vpn;timeout;remote;connection'}\n\n"
            "Document 2 of 10\n") in printed
    headings = [line for line in printed.splitlines() if line.startswith("Document ")]
    assert headings == [f"Document {n} of 10" for n in range(1, 11)]
    assert "\n\n\n" not in printed                  # never more than one blank line in a row
    assert "\n\nLabels (metadata):\n{'doc_id': '9', 'title': 'Microsoft Teams Audio Issues', " in printed
    assert printed.endswith("'tags': 'teams;audio;collaboration;windows'}\n")
