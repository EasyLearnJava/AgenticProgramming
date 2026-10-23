"""
Tests for utils.py: what print_chunks() prints for the 28 chunks. No key, no network.
"""
from chunking import split_documents
from knowledge_base import load_documents
from utils import print_chunks

DOCS = load_documents()


def test_print_chunks_prints_the_counts_then_every_articles_chunks(capsys):
    print_chunks(DOCS, split_documents(DOCS))
    printed = capsys.readouterr().out
    lines = printed.splitlines()
    assert printed.startswith("10 articles -> 28 chunks of at most 512 characters\n"
                              "  2 from VPN Connection Timeout (569 characters)\n")
    assert ("\n\nArticle 1 of 10: VPN Connection Timeout, cut into 2 chunks\n\n"
            "Chunk 1 of 2, from character 0 (") in printed
    articles = [line for line in lines if line.startswith("Article ")]
    assert len(articles) == 10
    assert articles[-1] == "Article 10 of 10: Microsoft Teams Audio Issues, cut into 3 chunks"
    assert sum(line.startswith("Chunk ") for line in lines) == 28
    assert "\n\n\n" not in printed                  # never more than one blank line in a row
