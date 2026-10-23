"""
Tests for utils.py: what print_documents() prints for a list of Documents.

No key, no network: the tests make their own two Documents.
"""
from langchain_core.documents import Document

from utils import print_documents

DOCS = [Document(page_content="title: First\nproblem: A", metadata={"source": "kb.csv", "row": 0}),
        Document(page_content="title: Second\nproblem: B", metadata={"source": "kb.csv", "row": 1})]


def test_it_prints_the_count_and_titles_then_every_document(capsys):
    # capsys is pytest's: it catches what the code prints, so the test can read it.
    print_documents(DOCS)
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
