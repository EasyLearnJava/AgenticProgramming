"""
Tests for utils.py: the hashes, the two ways of comparing text, and what the print helpers write.
"""
import hashlib
from types import SimpleNamespace

from langchain_core.documents import Document

from utils import print_changes, print_documents, print_report, sha256_file, short_hash, simplify, spelling_key


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


def test_print_documents_lists_each_id_and_title_then_each_document(capsys):
    docs = [Document(page_content="Title: VPN\n\nProblem: Slow", metadata={"doc_id": "kb-a", "title": "VPN",
                                                                          "tags": ["vpn"]})]
    print_documents(docs, "Documents passed on")
    assert capsys.readouterr().out == ("Documents passed on: 1\n  kb-a  VPN\n\nDocument 1 of 1\nText (page_content):\n"
                                       "Title: VPN\n\nProblem: Slow\n\nLabels and where it came from (metadata):\n"
                                       "  doc_id: kb-a\n  title: VPN\n  tags: ['vpn']\n")


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
