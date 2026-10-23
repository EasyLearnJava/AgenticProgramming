"""
Tests for pipeline.py: what it prints when it's run, from any folder, and that it's the only file that runs anything.

No key, no network: the tests run the files as their own processes, which only read the CSV file.
"""
import subprocess
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def run(script="pipeline.py", cwd=FOLDER):
    """Runs a file of this project as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / script)], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_step_then_the_titles_then_every_document():
    printed = run()
    assert printed.startswith("Step 1: Read the knowledge base\n10 documents\nrow 0  title: VPN Connection Timeout\n")
    assert ("row 9  title: Microsoft Teams Audio Issues\n\n"
            "Document 1 of 10\nText (page_content):\ntitle: VPN Connection Timeout\n") in printed
    headings = [line for line in printed.splitlines() if line.startswith("Document ")]
    assert headings == [f"Document {n} of 10" for n in range(1, 11)]
    assert printed.endswith("Where it came from (metadata):\n{'source': 'sample_it_kb.csv', 'row': 9}\n")


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    assert run(cwd=tmp_path) == run()


def test_the_other_files_only_define_what_the_pipeline_runs():
    # Run on their own, they print nothing: pipeline.py runs the steps
    assert run("knowledge_base_loader.py") == ""
    assert run("utils.py") == ""
