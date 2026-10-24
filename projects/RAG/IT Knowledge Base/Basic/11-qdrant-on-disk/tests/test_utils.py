"""
Tests for utils.py: what print_result() prints for an answer and its sources. No key, no network.
"""
from utils import print_result


def test_print_result_prints_the_question_the_answer_and_each_source(capsys):
    source = {"title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access", "snippet": "Title: VPN"}
    print_result("My VPN won't connect", {"answer": "An answer.", "sources": [source]})
    assert capsys.readouterr().out == ("Q: My VPN won't connect\nA: An answer.\n"
                                       "   found by the search: VPN Connection Timeout (VPN, Remote Access)\n\n")
