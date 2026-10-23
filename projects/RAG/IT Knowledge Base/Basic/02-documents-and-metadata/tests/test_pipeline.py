"""
Tests for pipeline.py: what it prints when it's run, from any folder, and that it's the only file that runs anything.

No key, no network: the tests run pipeline.py as its own process, which only reads the CSV file.
"""
import subprocess
import sys
from pathlib import Path

from knowledge_base import load_documents
from utils import print_documents

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)


def run(cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "pipeline.py")], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_step_then_every_document(capsys):
    print_documents(load_documents())
    assert run() == "Step 1: Read the knowledge base\n" + capsys.readouterr().out


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    assert run(cwd=tmp_path) == run()


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
