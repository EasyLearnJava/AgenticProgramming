"""
Tests for RAG step 1: the DataFrame read_kb.py reads from data/sample_it_kb.csv, and what the script prints.

    kb  ->  10 rows, the columns title, problem, resolution, system, category, notes, priority, tags

No key, no network: the tests only read the CSV file and run the script.
Run them:   python -m pytest   ->   7 passed        (add -v for one line per test)
"""
import subprocess
import sys
from pathlib import Path

from read_kb import KB_FILE, kb

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
COLUMNS = ["title", "problem", "resolution", "system", "category", "notes", "priority", "tags"]


def run_script(cwd):
    """Runs read_kb.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the script gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "read_kb.py")], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_path_points_at_the_csv_next_to_the_script():
    assert KB_FILE == FOLDER / "data" / "sample_it_kb.csv"
    assert KB_FILE.is_file()


def test_there_are_10_articles_with_the_8_columns_in_order():
    assert len(kb) == 10
    assert kb.columns.tolist() == COLUMNS


def test_no_article_has_an_empty_cell():
    assert not kb.isna().any().any()        # isna(): True where a cell is empty; any().any(): anywhere in the table


def test_every_title_is_different():
    assert kb["title"].is_unique


def test_the_first_article_is_the_vpn_timeout():
    first = kb.iloc[0]
    assert (first["title"], first["system"], first["category"]) == ("VPN Connection Timeout", "VPN", "Remote Access")


def test_running_the_script_prints_the_summary_then_the_first_article():
    printed = run_script(cwd=FOLDER)
    assert printed.startswith(f"10 articles\ncolumns: {COLUMNS}\n\n")
    assert "9     Microsoft Teams Audio Issues   Microsoft Teams        Collaboration\n" in printed   # the last row
    assert printed.endswith("  priority: High\n      tags: vpn;timeout;remote;connection\n")


def test_the_script_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the script still finds the file (①).
    assert run_script(cwd=tmp_path) == run_script(cwd=FOLDER)
