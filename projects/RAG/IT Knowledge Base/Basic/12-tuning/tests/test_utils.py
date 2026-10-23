"""
Tests for utils.py: what print_result() prints for an answer and its sources, and what print_table() prints
for the tuning scores. No key, no network.
"""
from utils import print_result, print_table


def test_print_result_prints_the_question_the_answer_and_each_source(capsys):
    source = {"title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access", "snippet": "Title: VPN"}
    print_result("My VPN won't connect", {"answer": "An answer.", "sources": [source]})
    assert capsys.readouterr().out == ("Q: My VPN won't connect\nA: An answer.\n"
                                       "   source: VPN Connection Timeout (VPN, Remote Access)\n\n")


def test_the_table_has_a_line_per_chunk_size(capsys):
    print_table([{"chunk_size": 200, "chunks": 49, "top_1": 1, "top_3": 2},
                 {"chunk_size": 1000, "chunks": 10, "top_1": 2, "top_3": 2}], total=2)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "chunk size  chunks  found in top 1  found in top 3"
    assert lines[1].split() == ["200", "49", "1", "of", "2", "2", "of", "2"]
    assert lines[2].split() == ["1000", "10", "2", "of", "2", "2", "of", "2"]
