"""
Tests for utils.py: the hashes, the two ways of comparing text, the token estimate, and what the print helpers write.
"""
import hashlib
from types import SimpleNamespace

from langchain_core.documents import Document

from utils import (
    count_tokens,
    print_answers,
    print_changes,
    print_chunk_report,
    print_chunks,
    print_documents,
    print_report,
    print_stats,
    print_store,
    print_traces,
    print_vectors,
    sha256_file,
    short_hash,
    simplify,
    spelling_key,
)


def test_a_files_checksum_is_the_sha256_of_its_bytes(tmp_path):
    path = tmp_path / "file.csv"
    path.write_bytes(b"title\r\nA\r\n" * 300_000)            # over one read block
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_short_hash_is_16_hex_digits_and_changes_with_any_character():
    assert short_hash("VPN") == hashlib.sha256(b"VPN").hexdigest()[:16]
    assert short_hash("VPN") != short_hash("VPN ")


def test_simplify_ignores_case_and_spacing():
    assert simplify("  VPN \t Connection\nTimeout ") == "vpn connection timeout"


def test_a_spelling_key_ignores_case_spaces_hyphens_and_underscores():
    assert {spelling_key(value) for value in ("Wi-Fi", "WiFi", "wi fi", "WI_FI")} == {"wifi"}


def test_a_word_counts_a_token_per_4_letters_and_a_mark_one():
    assert count_tokens("Restart the VPN.") == 5               # Restart 2, the 1, VPN 1, "." 1
    assert count_tokens("") == 0
    assert count_tokens("authentication") == 4                 # 14 letters: a tokenizer makes fewer of it


def test_the_estimate_errs_high_for_ordinary_text():
    # A rule of thumb for English is a token per 4 characters, spaces included: the estimate is above it
    text = "Users experience timeout errors when attempting to connect to the corporate VPN from remote locations"
    assert count_tokens(text) >= len(text) / 4


def test_print_documents_lists_each_id_and_title(capsys):
    docs = [Document(page_content="Title: VPN\n\nProblem: Slow", metadata={"doc_id": "kb-a", "title": "VPN"})]
    print_documents(docs, "Documents passed on")
    assert capsys.readouterr().out == "Documents passed on: 1\n  kb-a  VPN\n"


def test_print_chunks_lists_each_chunk_then_shows_the_first_in_full(capsys):
    metadata = {"chunk_id": "kb-a:problem:1", "doc_id": "kb-a", "section": "problem", "position": 0,
                "token_count": 6, "parent_id": "kb-a:problem"}
    print_chunks([Document(page_content="VPN\nProblem: Slow", metadata=metadata)], parents=1, ceiling=512, shown=1)
    assert capsys.readouterr().out == (
        "Chunks: 1 from 1 article, 6 to 6 tokens each (ceiling 512); 1 parent section kept whole\n"
        "  kb-a:problem:1    6 tokens  Problem: Slow\n\nChunk 1 of 1\nText (page_content):\nVPN\nProblem: Slow\n\n"
        "Its own metadata (and its article's labels and provenance, as in Advanced/02):\n"
        "  chunk_id: kb-a:problem:1\n  doc_id: kb-a\n  section: problem\n  position: 0\n  token_count: 6\n"
        "  parent_id: kb-a:problem\n")


def test_print_vectors_says_where_they_came_from_and_what_the_gate_caught(capsys):
    report = SimpleNamespace(from_cache=1, embedded=1, calls=2, retries=1, failed_calls=1, tokens=1234,
                             redacted=["c1: email address j***@example.com"])
    print_vectors([[0.123456, -1.0, 0.5, 0.25, 9.0], [0.0] * 5], report, model="fake/m", dimensions=5)
    assert capsys.readouterr().out == (
        "Vectors: 2, each 5 numbers, by fake/m\n"
        "  1 from the cache, 1 made by the model in 2 calls (1 retry, 1 failed), about 1,234 tokens sent\n"
        "  the first vector begins [0.1235, -1.0, 0.5, 0.25]\n"
        "Sensitive-data gate: 1 value redacted before sending\n  c1: email address j***@example.com\n")


def test_print_store_says_where_the_points_went_and_what_the_checks_found(capsys):
    report = SimpleNamespace(collection="it_kb_v2", rebuilt=True, rebuilt_from="it_kb_v1", added=3, updated=1,
                             deleted_stale=1, deleted_removed=2, points=9, problems=[], orphans=["kb-x"])
    print_store(report, alias="it_kb", location=":memory:")
    assert capsys.readouterr().out == (
        "Vector store: it_kb -> it_kb_v2 (rebuilt; it_kb_v1 kept for rollback), Qdrant in memory\n"
        "  4 points written: 3 added, 1 updated; 3 deleted (1 old chunk of changed articles, 2 of removed articles); "
        "9 points in all\n  Checks: passed\n"
        "  1 article not in the knowledge base still has points: kb-x (--rebuild clears them)\n")


def test_print_traces_shows_each_stage_with_its_time(capsys):
    trace = SimpleNamespace(trace_id="0123456789abcdef", seconds=0.0123, spans=[
        SimpleNamespace(name="condense", seconds=0.0, fields={"history_turns": 1, "rewritten": True,
                                                              "question": "VPN, and on Mac?"}),
        SimpleNamespace(name="retrieve", seconds=0.0081, fields={"candidates": 3, "chunk_ids": ["a", "b"]})])
    asked = SimpleNamespace(question="and on Mac?", asked="VPN, and on Mac?", trace=trace, cached="", cost_usd=0.00015)
    print_traces([asked])
    assert capsys.readouterr().out == (
        "Traces: a line per stage, with its time\n"
        "  and on Mac? (asked as: VPN, and on Mac?): trace 0123456789abcdef, 12 ms, $0.000150\n"
        "    condense     0.0 ms  history_turns 1, rewritten True\n"
        "    retrieve     8.1 ms  candidates 3, chunk_ids 2\n")


def test_print_stats_lists_what_the_engine_runs_with(capsys):
    print_stats({"chat_model": "fake/m", "points": 39})
    assert capsys.readouterr().out == "Engine: what it's running with\n  chat_model: fake/m\n  points: 39\n"


def test_print_answers_shows_each_answer_its_sources_and_its_checks(capsys):
    source = Document(page_content="VPN\nResolution: Open the ports.",
                      metadata={"title": "VPN", "section": "resolution"})
    answers = [SimpleNamespace(question="vpn?", status="answered", answer="Open the ports.", prompt_version="answer-v1",
                               sources=[source], calls=1, context_tokens=42, problems=[], flagged=["kb-x:notes:1"],
                               dropped=[], redacted=[], unsupported=[], faithfulness=1.0),
               SimpleNamespace(question="lunch?", status="no_match", answer="Not covered here.",
                               prompt_version="answer-v1", sources=[], calls=0, context_tokens=0, problems=[],
                               flagged=[], dropped=[], redacted=[], unsupported=[], faithfulness=None)]
    print_answers(answers, model="fake/m", budget=3000)
    assert capsys.readouterr().out == (
        "Answers: by fake/m, with the prompt answer-v1; the context's budget 3,000 tokens\n"
        "  Question: vpn?\n    Answer: Open the ports.\n    Sources: VPN (resolution)\n"
        "    1 call; context 42 tokens; checks: passed\n"
        "    kept out of the context, they speak to the model: kb-x:notes:1\n    faithfulness: 1.00\n"
        "  Question: lunch?\n    No match: Not covered here.\n    0 calls; context 0 tokens; checks: passed\n")


def test_print_chunk_report_says_when_nothing_was_found(capsys):
    print_chunk_report(SimpleNamespace(articles=1, chunks=3, has_issues=lambda: False))
    assert capsys.readouterr().out == ("Chunk checks: 1 article cut into 3 chunks\n"
                                       "Nothing merged, cut again or removed.\n")


def test_print_report_says_when_nothing_was_found(capsys):
    report = SimpleNamespace(rows=10, kept=10, blank_lines=1, has_issues=lambda: False)
    print_report(report)
    assert capsys.readouterr().out == ("Data checks: 10 rows read, 10 kept (1 blank line ignored)\n"
                                       "Nothing skipped, removed, normalized, redacted or flagged.\n")


def test_print_changes_says_why_everything_is_passed_on(capsys):
    print_changes(SimpleNamespace(first_run=True, added=[1, 2]))
    print_changes(SimpleNamespace(first_run=False, full=True, added=[1, 2]))
    assert capsys.readouterr().out == ("Changes: no earlier run to compare with, so all 2 articles are new\n"
                                       "Changes: --full, so all 2 articles are passed on, whatever changed\n")
