"""
Tests for pipeline.py: the steps run in order as the script does them, run after run: the first run passes on every
article, cuts it into chunks and embeds them; the next passes on only what changed, and with --full takes every
vector from the cache; the manifest is saved only when every step succeeds; a missing key stops the run before
anything is read; and a missing or bad file of any kind ends the run with exit code 1 and one error line.

The script runs with a copy of kb_settings.toml whose embedding model is the stand-in ("fake"): no key, no call.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from support import fake_settings

from knowledge_base_loader import KB_FILE, MANIFEST_FILE, SETTINGS_FILE
from pipeline import main, parse_args

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
DATA = FOLDER / "data"
# The sensitive values in the messy file: none may ever be printed, logged or kept
SENSITIVE = ["jane.doe@example.com", "555-010-0142", "4111 1111 1111 1111", "S3cr3t-Pass", "Winter2026!",
             "123-45-6789"]
FIRST_VECTORS = ("Vectors: 39, each 768 numbers, by fake/gemini-embedding-001\n"
                 "  0 from the cache, 39 made by the model in 1 call (0 retries, 0 failed), about 2,271 tokens sent\n")


def run_script(*args, settings: Path | None, cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back the process. GOOGLE_API_KEY
    is empty, and .env can't fill it, so even a run with Gemini's settings can't reach it."""
    options = [*args, "--settings", str(settings)] if settings else list(args)
    return subprocess.run([sys.executable, str(FOLDER / "pipeline.py"), *options], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", env={**os.environ, "GOOGLE_API_KEY": ""})


def write_file(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_the_options_default_to_the_files_next_to_the_scripts():
    args = parse_args([])
    assert (args.data_path, args.settings, args.manifest_path, args.full, args.log_level) == \
        (KB_FILE, SETTINGS_FILE, MANIFEST_FILE, False, "INFO")


def test_main_returns_1_and_logs_the_reason_when_a_file_is_missing(tmp_path, caplog, capsys):
    settings = str(fake_settings(tmp_path))
    assert main(["--data-path", str(tmp_path / "missing.csv"), "--manifest-path", str(tmp_path / "m.json"),
                 "--settings", settings]) == 1
    assert main(["--settings", str(tmp_path / "missing.toml"), "--manifest-path", str(tmp_path / "m.json")]) == 1
    assert "Knowledge base file not found" in caplog.text and "Settings file not found" in caplog.text
    assert capsys.readouterr().out == "" and not (tmp_path / "m.json").exists()


def test_the_first_run_embeds_every_chunk_and_the_second_nothing(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    first = run_script("--manifest-path", manifest, settings=settings)
    second = run_script("--manifest-path", manifest, settings=settings)
    assert (first.returncode, second.returncode) == (0, 0)
    assert first.stdout.startswith("Documents passed on to the next step: 10\n  kb-")
    assert "\nChunks: 39 from 10 articles, 25 to 127 tokens each (ceiling 512); 30 parent sections kept whole\n" \
        in first.stdout
    assert f"\n{FIRST_VECTORS}" in first.stdout
    assert "\nSensitive-data gate: nothing to redact before sending\n" in first.stdout
    assert first.stdout.endswith("Changes: no earlier run to compare with, so all 10 articles are new\n")
    assert "\nVectors: 0, each 768 numbers" in second.stdout and "0 made by the model in 0 calls" in second.stdout
    assert second.stdout.endswith("Changes since the last run: 0 added, 0 changed, 0 removed, 10 unchanged\n")
    log = [line.split(" ", 2)[2] for line in first.stderr.splitlines()]
    assert log[-6] == "INFO Cut 10 articles into 39 chunks"
    assert log[-5].startswith("INFO Embedded 39 chunks: 0 from the cache, 39 by the model in 1 call (0 retries)")
    assert log[-4].startswith("INFO Payload indexes asked for on doc_id, system, category, priority, tags, "
                              "visibility, team: Qdrant in a process keeps none")
    assert log[-3:] == ["INFO Made collection it_kb_v1, behind the alias it_kb",
                        "INFO Stored: 39 added, 0 updated, 0 deleted; 39 points in it_kb_v1",
                        "INFO Manifest saved: manifest.json (10 articles)"]
    assert "\nVector store: it_kb -> it_kb_v1, Qdrant on disk, in data/qdrant\n  39 points written: 39 added, 0 " \
           "updated; 0 deleted (0 old chunks of changed articles, 0 of removed articles); 39 points in all\n" \
           "  Checks: passed\n" in first.stdout
    assert "\n  0 points written: 0 added, 0 updated; 0 deleted (0 old chunks of changed articles, 0 of removed " \
           "articles); 39 points in all\n" in second.stdout
    assert "\nAnswers: by fake/gemini-3.5-flash-lite, with the prompt answer-v1; the context's budget 3,000 tokens\n" \
           "  Question: My VPN keeps timing out when I work from home\n    Answer: " in first.stdout
    assert "\n    1 call; context " in first.stdout and "; checks: passed\n" in first.stdout
    traces = first.stdout.split("\nTraces: a line per stage, with its time\n", 1)[1]
    assert re.match(r"  My VPN keeps timing out when I work from home: trace [0-9a-f]{16}, \d+ ms\n    condense ",
                    traces)
    assert "\nEngine: what it's running with\n  embedding_model: fake/gemini-embedding-001\n" in first.stdout
    assert "\n  collection: it_kb -> it_kb_v1\n  points: 39\n" in first.stdout


def test_a_follow_up_and_a_repeat_in_one_run(tmp_path):
    result = run_script("--manifest-path", str(tmp_path / "m.json"), "--question", "My VPN keeps timing out",
                        "--question", "and on Mac?", "--question", "my vpn keeps timing out",
                        settings=fake_settings(tmp_path))
    answers = result.stdout.split("\nAnswers: ", 1)[1]
    assert "  Question: My VPN keeps timing out, and on Mac?\n" in answers          # the follow-up, rewritten
    assert "and on Mac? (asked as: My VPN keeps timing out, and on Mac?): trace " in answers
    assert re.search(r"  my vpn keeps timing out: trace [0-9a-f]{16}, \d+ ms, from the cache \(exact\)", answers)
    assert "\n  cached_answers: 2\n  breakers: vector store closed, chat model closed\n  sessions: 1\n" in answers


def test_an_article_that_speaks_to_the_model_is_kept_out_of_the_answers_context(tmp_path):
    result = run_script("--data-path", str(DATA / "sample_it_kb_injected.csv"), "--manifest-path",
                        str(tmp_path / "m.json"), "--question", "MFA setup fails on my new iPhone",
                        settings=fake_settings(tmp_path))
    assert result.returncode == 0
    answers = result.stdout.split("\nAnswers: ", 1)[1]
    assert "  Question: MFA setup fails on my new iPhone\n    Answer: 1. Ensure device time is synchronized" in answers
    assert "    kept out of the context, they speak to the model: kb-" in answers
    assert "disable MFA" not in answers.split("\nData checks:")[0]
    assert (tmp_path / "data" / "embedding_cache.sqlite3").is_file() and (tmp_path / "data" / "qdrant").is_dir()


def test_a_full_rerun_takes_every_vector_from_the_cache(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    first = run_script("--manifest-path", manifest, settings=settings)
    again = run_script("--manifest-path", manifest, "--full", settings=settings)
    assert "\n  39 from the cache, 0 made by the model in 0 calls (0 retries, 0 failed), about 0 tokens sent\n" \
        in again.stdout
    first_vector = [line for line in first.stdout.splitlines() if line.startswith("  the first vector begins")]
    assert first_vector == [line for line in again.stdout.splitlines() if line.startswith("  the first vector begins")]


def test_the_next_export_embeds_only_the_articles_that_changed(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    run_script("--manifest-path", manifest, settings=settings)
    result = run_script("--data-path", str(DATA / "sample_it_kb_next.csv"), "--manifest-path", manifest,
                        settings=settings)
    assert result.returncode == 0
    assert "\nChunks: 10 from 3 articles," in result.stdout      # VPN 3, the laptop article 4, the new one 3
    # The laptop article's priority changed, not its text, so its 4 chunks are cached, as are VPN's problem and
    # notes: only VPN's edited fix and the new article's 3 chunks are sent
    assert "\n  6 from the cache, 4 made by the model in 1 call" in result.stdout
    # VPN's old fix chunk and the removed printer article's 4 chunks are deleted: 39 - 5 + 4 new = 38
    assert "\n  10 points written: 4 added, 6 updated; 5 deleted (1 old chunk of changed articles, 4 of removed " \
           "articles); 38 points in all\n  Checks: passed\n" in result.stdout
    changes = result.stdout.split("\nChanges since the last run: ", 1)[1]
    assert changes.startswith("1 added, 2 changed, 1 removed, 7 unchanged\n")


def test_a_rebuild_fills_a_new_collection_and_rollback_goes_back(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    run_script("--manifest-path", manifest, settings=settings)
    rebuilt = run_script("--manifest-path", manifest, "--rebuild", "--data-path", str(DATA / "sample_it_kb_next.csv"),
                         settings=settings)
    assert "\nVector store: it_kb -> it_kb_v2 (rebuilt; it_kb_v1 kept for rollback), Qdrant on disk, in data/qdrant\n" \
           "  38 points written: 38 added, 0 updated;" in rebuilt.stdout
    back = run_script("--rollback", settings=settings)
    assert (back.returncode, back.stdout.split(".")[0]) == (0, "The alias it_kb now points at it_kb_v1")
    again = run_script("--rollback", settings=settings)
    assert again.returncode == 1 and "ERROR There's no collection before it_kb_v1 to go back to" in again.stderr


def test_full_rebuild_and_rollback_cant_be_combined(tmp_path):
    result = run_script("--full", "--rebuild", settings=fake_settings(tmp_path))
    assert result.returncode == 2 and "not allowed with argument" in result.stderr


def test_a_model_of_another_size_stops_the_run_and_says_to_rebuild(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    run_script("--manifest-path", manifest, settings=settings)
    write_file(settings, settings.read_text(encoding="utf-8").replace("dimensions = 768", "dimensions = 256"))
    result = run_script("--manifest-path", manifest, "--full", settings=settings)
    assert (result.returncode, result.stdout) == (1, "")
    assert "holds vectors of 768 numbers, but the embedding model makes 256: nothing written. Run with --rebuild" \
        in result.stderr
    assert run_script("--manifest-path", manifest, "--rebuild", settings=settings).returncode == 0


def test_the_chunking_file_shows_each_check(tmp_path):
    result = run_script("--data-path", str(DATA / "sample_it_kb_chunking.csv"), "--manifest-path",
                        str(tmp_path / "m.json"), settings=fake_settings(tmp_path))
    assert result.returncode == 0
    report = result.stdout.split("\nChunk checks: ", 1)[1]
    assert report.startswith("6 articles cut into 22 chunks\n")


def test_a_row_skipped_this_run_isnt_taken_for_a_removed_article(tmp_path):
    settings, manifest = fake_settings(tmp_path), str(tmp_path / "manifest.json")
    first = run_script("--manifest-path", manifest, settings=settings)
    vpn = first.stdout.splitlines()[1].split()[0]                            # its ID, the first one listed
    broken = KB_FILE.read_text(encoding="utf-8").replace(",High,vpn;timeout", ",Urgent,vpn;timeout", 1)
    result = run_script("--data-path", str(write_file(tmp_path / "it_kb.csv", broken)), "--manifest-path", manifest,
                        settings=settings)
    assert "0 removed" in result.stdout
    assert f"Skipped this run: the last run's version stays (1)\n  {vpn}  VPN Connection Timeout\n" in result.stdout
    assert vpn in json.loads(Path(manifest).read_text(encoding="utf-8"))["articles"]


def test_the_messy_file_report_never_shows_a_sensitive_value(tmp_path):
    result = run_script("--data-path", str(DATA / "sample_it_kb_messy.csv"), "--manifest-path",
                        str(tmp_path / "m.json"), settings=fake_settings(tmp_path))
    assert result.returncode == 0
    assert "\nData checks: 14 rows read, 6 kept (1 blank line ignored)\n" in result.stdout
    for value in SENSITIVE:
        assert value not in result.stdout and value not in result.stderr


def test_the_script_finds_its_files_from_any_folder(tmp_path):
    here = run_script("--manifest-path", str(tmp_path / "a.json"), settings=fake_settings(tmp_path / "a"),
                      cwd=tmp_path)
    there = run_script("--manifest-path", str(tmp_path / "b.json"), settings=fake_settings(tmp_path / "b"))

    def without_traces(output):                       # trace IDs and times differ from run to run
        return [line for line in output.splitlines() if not re.search(r"\bms\b|kb_version", line)]

    assert here.returncode == 0 and without_traces(here.stdout) == without_traces(there.stdout)


def test_a_missing_key_stops_the_run_before_anything_is_read(tmp_path):
    result = run_script("--manifest-path", str(tmp_path / "m.json"), settings=None)    # Gemini: it needs the key
    assert (result.returncode, result.stdout) == (1, "")
    assert "ERROR GOOGLE_API_KEY is not set." in result.stderr and "Reading" not in result.stderr
    assert "Traceback" not in result.stderr and not (tmp_path / "m.json").exists()


def test_bad_files_end_the_script_with_exit_code_1_one_line_and_no_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    missing = run_script("--data-path", str(tmp_path / "missing.csv"), "--manifest-path", str(manifest),
                         settings=fake_settings(tmp_path))
    bad = fake_settings(tmp_path / "bad")
    write_file(bad, bad.read_text(encoding="utf-8").replace('provider = "fake"', 'provider = "openai"'))
    bad_settings = run_script("--manifest-path", str(manifest), settings=bad)
    for result, message in [(missing, "ERROR Knowledge base file not found:"),
                            (bad_settings, "ERROR Settings file has a bad setting (embeddings.provider: Input should "
                                           "be 'google' or 'fake'")]:
        assert (result.returncode, result.stdout) == (1, "")
        assert message in result.stderr and "Traceback" not in result.stderr
    assert not manifest.exists()


def test_a_broken_manifest_says_what_to_do_and_full_gets_past_it(tmp_path):
    settings = fake_settings(tmp_path)
    manifest = write_file(tmp_path / "manifest.json", "{not json")
    result = run_script("--manifest-path", str(manifest), settings=settings)
    assert (result.returncode, result.stdout) == (1, "")
    assert "Delete it, or run with --full, and every article is passed on." in result.stderr
    assert run_script("--manifest-path", str(manifest), "--full", settings=settings).returncode == 0
