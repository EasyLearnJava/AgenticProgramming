"""
Tests for pipeline.py: the steps run in order as the script does them, run after run: the first run passes on every
article and cuts it into chunks, the next only what changed; the manifest is saved only when every step succeeds;
and a missing or bad file of any kind ends the run with exit code 1 and one error line, never a traceback.
"""
import json
import subprocess
import sys
from pathlib import Path

from knowledge_base_loader import KB_FILE, MANIFEST_FILE, SETTINGS_FILE
from pipeline import main, parse_args

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DATA = FOLDER / "data"
# The sensitive values in the messy file: none may ever be printed, logged or kept
SENSITIVE = ["jane.doe@example.com", "555-010-0142", "4111 1111 1111 1111", "S3cr3t-Pass", "Winter2026!",
             "123-45-6789"]


def run_script(*args, cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back the process."""
    # sys.executable is the Python running these tests (the venv's), so the script gets the same packages.
    return subprocess.run([sys.executable, str(FOLDER / "pipeline.py"), *args], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8")


def write_file(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_the_options_default_to_the_files_next_to_the_scripts():
    args = parse_args([])
    assert (args.data_path, args.settings, args.manifest_path, args.full, args.log_level) == \
        (KB_FILE, SETTINGS_FILE, MANIFEST_FILE, False, "INFO")


def test_main_returns_1_and_logs_the_reason_when_a_file_is_missing(tmp_path, caplog, capsys):
    assert main(["--data-path", str(tmp_path / "missing.csv"), "--manifest-path", str(tmp_path / "m.json")]) == 1
    assert main(["--settings", str(tmp_path / "missing.toml"), "--manifest-path", str(tmp_path / "m.json")]) == 1
    assert "Knowledge base file not found" in caplog.text and "Settings file not found" in caplog.text
    assert capsys.readouterr().out == "" and not (tmp_path / "m.json").exists()


def test_the_first_run_cuts_every_article_and_the_second_nothing(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    first, second = run_script("--manifest-path", manifest), run_script("--manifest-path", manifest)
    assert (first.returncode, second.returncode) == (0, 0)
    assert first.stdout.startswith("Documents passed on to the next step: 10\n  kb-")
    assert "\nChunks: 39 from 10 articles, 25 to 127 tokens each (ceiling 512); 30 parent sections kept whole\n" \
        in first.stdout
    assert "\nChunk checks: 10 articles cut into 39 chunks\nNothing merged, cut again or removed.\n" in first.stdout
    assert first.stdout.endswith("Changes: no earlier run to compare with, so all 10 articles are new\n")
    assert second.stdout.startswith("Documents passed on to the next step: 0\n\n"
                                    "Chunks: 0 from 0 articles; 0 parent sections kept whole\n\n")
    assert second.stdout.endswith("Changes since the last run: 0 added, 0 changed, 0 removed, 10 unchanged\n")
    assert len(json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["articles"]) == 10
    log = [line.split(" ", 2)[2] for line in first.stderr.splitlines()]
    assert log[-2:] == ["INFO Cut 10 articles into 39 chunks", "INFO Manifest saved: manifest.json (10 articles)"]


def test_the_next_export_cuts_only_the_articles_that_changed(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    run_script("--manifest-path", manifest)
    result = run_script("--data-path", str(DATA / "sample_it_kb_next.csv"), "--manifest-path", manifest)
    assert result.returncode == 0
    assert "\nChunks: 10 from 3 articles," in result.stdout      # VPN 3, the laptop article 4, the new one 3
    changes = result.stdout.split("\nChanges since the last run: ", 1)[1]
    assert changes.startswith("1 added, 2 changed, 1 removed, 7 unchanged\n")
    assert "VPN Connection Timeout  (resolution changed)\n" in changes
    assert "Laptop Performance Degradation  (priority changed)\n" in changes
    assert "Removed: not in this file, listed for deletion (1)\n" in changes


def test_the_chunking_file_shows_each_check(tmp_path):
    result = run_script("--data-path", str(DATA / "sample_it_kb_chunking.csv"), "--manifest-path",
                        str(tmp_path / "m.json"))
    assert result.returncode == 0
    report = result.stdout.split("\nChunk checks: ", 1)[1]
    assert report.startswith("6 articles cut into 22 chunks\n")
    for heading in ["Removed: repeated in the article (2)", "Merged: a fragment joined to the chunk before it (1)",
                    "Cut again: a piece with no spaces, too big for a chunk (1)"]:
        assert f"\n{heading}\n" in report


def test_full_passes_on_every_article_whatever_changed(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    run_script("--manifest-path", manifest)
    result = run_script("--manifest-path", manifest, "--full")
    assert result.stdout.startswith("Documents passed on to the next step: 10\n")
    assert result.stdout.endswith("Changes: --full, so all 10 articles are passed on, whatever changed\n")


def test_a_row_skipped_this_run_isnt_taken_for_a_removed_article(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    first = run_script("--manifest-path", manifest)
    vpn = first.stdout.splitlines()[1].split()[0]                            # its ID, the first one listed
    broken = KB_FILE.read_text(encoding="utf-8").replace(",High,vpn;timeout", ",Urgent,vpn;timeout", 1)
    result = run_script("--data-path", str(write_file(tmp_path / "it_kb.csv", broken)), "--manifest-path", manifest)
    assert "0 removed" in result.stdout
    assert f"Skipped this run: the last run's version stays (1)\n  {vpn}  VPN Connection Timeout\n" in result.stdout
    assert vpn in json.loads(Path(manifest).read_text(encoding="utf-8"))["articles"]


def test_the_messy_file_report_never_shows_a_sensitive_value(tmp_path):
    result = run_script("--data-path", str(DATA / "sample_it_kb_messy.csv"), "--manifest-path",
                        str(tmp_path / "m.json"))
    assert result.returncode == 0
    assert "\nData checks: 14 rows read, 6 kept (1 blank line ignored)\n" in result.stdout
    for value in SENSITIVE:
        assert value not in result.stdout and value not in result.stderr


def test_the_script_finds_its_files_from_any_folder(tmp_path):
    here = run_script("--manifest-path", str(tmp_path / "a.json"), cwd=tmp_path)
    there = run_script("--manifest-path", str(tmp_path / "b.json"))
    assert here.returncode == 0 and here.stdout == there.stdout


def test_bad_files_end_the_script_with_exit_code_1_one_line_and_no_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    missing = run_script("--data-path", str(tmp_path / "missing.csv"), "--manifest-path", str(manifest))
    bad_settings = run_script("--settings", str(write_file(tmp_path / "s.toml", "[chunking]\nchunk_size = 4\n")),
                              "--manifest-path", str(manifest))
    for result, message in [(missing, "ERROR Knowledge base file not found:"),
                            (bad_settings, "ERROR Settings file has a bad setting (")]:
        assert (result.returncode, result.stdout) == (1, "")
        assert message in result.stderr and "Traceback" not in result.stderr
    assert not manifest.exists()


def test_a_broken_manifest_says_what_to_do_and_full_gets_past_it(tmp_path):
    manifest = write_file(tmp_path / "manifest.json", "{not json")
    result = run_script("--manifest-path", str(manifest))
    assert (result.returncode, result.stdout) == (1, "")
    assert "Delete it, or run with --full, and every article is passed on." in result.stderr
    assert run_script("--manifest-path", str(manifest), "--full").returncode == 0
