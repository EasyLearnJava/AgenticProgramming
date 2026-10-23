"""
Tests for utils.py: what print_documents() prints for the 10 Documents. No key, no network.
"""
from knowledge_base import load_documents
from utils import print_documents

DOCS = load_documents()


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
