"""
Tests for pipeline.py: what it prints when it's run, with the default chunk size and another one, from any folder,
and that it's the only file that runs anything.

No key, no network: the tests run pipeline.py as its own process, which only reads the CSV file.
"""
import subprocess
import sys
from pathlib import Path

from chunking import split_documents
from knowledge_base import load_documents
from utils import print_chunks

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
STEPS = "Step 1: Read the knowledge base: 10 documents\nStep 2: Chunk\n"


def run(*args, cwd=FOLDER):
    """Runs pipeline.py as its own process, started in the folder `cwd`, and gives back what it printed."""
    # sys.executable is the Python running these tests (the venv's), so the file gets the same packages.
    result = subprocess.run([sys.executable, str(FOLDER / "pipeline.py"), *args], cwd=cwd, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    return result.stdout


def test_the_pipeline_prints_the_steps_then_every_chunk(capsys):
    docs = load_documents()
    print_chunks(docs, split_documents(docs))
    assert run() == STEPS + capsys.readouterr().out


def test_a_number_after_pipeline_py_is_the_chunk_size(capsys):
    docs = load_documents()
    print_chunks(docs, split_documents(docs, chunk_size=200), 200)
    printed = run("200")
    assert printed == STEPS + capsys.readouterr().out
    assert printed.startswith(STEPS + "10 articles -> 49 chunks of at most 200 characters\n")


def test_the_pipeline_finds_the_csv_from_any_folder(tmp_path):
    # tmp_path is an empty folder pytest makes for this test: started there, the pipeline still finds the file.
    assert run(cwd=tmp_path) == run()


def test_only_the_pipeline_runs_anything():
    runnable = sorted(path.name for path in FOLDER.glob("*.py")
                      if '__name__ == "__main__"' in path.read_text(encoding="utf-8"))
    assert runnable == ["pipeline.py"]                # the other files only define the steps
