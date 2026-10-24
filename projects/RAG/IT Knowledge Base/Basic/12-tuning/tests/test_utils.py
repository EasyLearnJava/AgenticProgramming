"""
Tests for utils.py: what print_result() prints for an answer and its sources, and what print_table() and
print_misses() print for the tuning scores. No key, no network.
"""
from utils import print_misses, print_result, print_table


def test_print_result_prints_the_question_the_answer_and_each_source(capsys):
    source = {"title": "VPN Connection Timeout", "system": "VPN", "category": "Remote Access", "snippet": "Title: VPN"}
    print_result("My VPN won't connect", {"answer": "An answer.", "sources": [source]})
    assert capsys.readouterr().out == ("Q: My VPN won't connect\nA: An answer.\n"
                                       "   found by the search: VPN Connection Timeout (VPN, Remote Access)\n\n")


def test_the_table_has_a_line_per_chunk_size_and_search_with_each_score_under_its_heading(capsys):
    print_table([{"chunk_size": 200, "chunks": 49, "search": "gemini", "top_1": 1, "top_3": 2},
                 {"chunk_size": 200, "chunks": 49, "search": "random", "top_1": 0.2, "top_3": 1.0},
                 {"chunk_size": 1000, "chunks": 10, "search": "gemini", "top_1": 2, "top_3": 2}], total=2)
    lines = capsys.readouterr().out.splitlines()
    assert lines == ["chunk size  chunks  search    found in top 1  found in top 3",
                     "       200      49  gemini            1 of 2          2 of 2",
                     "       200      49  random          0.2 of 2          1 of 2",
                     "",
                     "      1000      10  gemini            2 of 2          2 of 2"]
    for line in lines[1:]:                          # each score ends where its heading ends: "... of 2"
        assert line == "" or (line[43] == "2" and line[59] == "2")


def test_the_misses_are_gemini_s_for_each_chunk_size_by_article(capsys):
    missed = ["MFA Setup Failure", "Printer Not Found"]
    print_misses([{"chunk_size": 200, "search": "gemini", "missed_in_top_1": missed},
                  {"chunk_size": 200, "search": "keywords", "missed_in_top_1": ["Password Reset Failed"]},
                  {"chunk_size": 200, "search": "random"},
                  {"chunk_size": 1000, "search": "gemini", "missed_in_top_1": []}])
    assert capsys.readouterr().out.splitlines() == ["", "Not in Gemini's top 1, by article:",
                                                   "       200  MFA Setup Failure, Printer Not Found",
                                                   "      1000  none"]
