"""
Tests for rag_basics.ipynb: every cell run in order, as Jupyter runs them, then what the cells print. The first run
downloads the model, all-MiniLM-L6-v2 (about 90 MB), from Hugging Face; after that, it all runs on this machine.
"""
import re
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
NOTEBOOK = FOLDER / "rag_basics.ipynb"
DOCUMENTS = ("['The Eiffel Tower is in Paris.', 'The Colosseum is in Rome.', "
             "'The Statue of Liberty is in New York.', 'The Burj Khalifa is in Dubai.']")
SCORE = re.compile(r"score=(\d+\.\d+)")   # a score as cell 5 prints it


def printed(cell) -> str:
    """What a code cell printed (its stdout)."""
    return "".join(output.text for output in cell.outputs
                   if output.output_type == "stream" and output.name == "stdout")


@pytest.fixture(scope="module")
def ran():
    """The notebook's code cells after a run of the whole notebook, in a new kernel."""
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    NotebookClient(notebook, timeout=600, resources={"metadata": {"path": str(FOLDER)}}).execute()
    return [cell for cell in notebook.cells if cell.cell_type == "code"]


def test_every_cell_runs_without_an_error(ran):
    assert len(ran) == 5
    assert not [output for cell in ran for output in cell.outputs if output.output_type == "error"]


def test_the_four_documents_are_indexed(ran):
    assert printed(ran[2]) == f"Indexed documents: {DOCUMENTS}\n"


def test_the_query_finds_the_eiffel_tower_first(ran):
    assert printed(ran[3]) == ("\nBasic RAG Results: "
                               "['The Eiffel Tower is in Paris.', 'The Burj Khalifa is in Dubai.']\n")


def test_hybrid_search_keeps_the_one_keyword_match_with_its_score(ran):
    lines = printed(ran[4]).splitlines()
    assert lines[:2] == ["", "Hybrid Search + Reranking Results:"]
    assert len(lines) == 3 and lines[2].startswith("The Eiffel Tower is in Paris. (score=0.")


def test_the_saved_notebook_shows_what_a_run_prints(ran):
    # The outputs saved in the notebook, shown by GitHub and Jupyter before a run, are a real run's. A score's last
    # digit can differ from one computer to another, so the scores are compared to within 0.001, the rest exactly.
    saved = [printed(cell) for cell in nbformat.read(NOTEBOOK, as_version=4).cells if cell.cell_type == "code"]
    now = [printed(cell) for cell in ran]
    assert [SCORE.sub("score=?", text) for text in saved] == [SCORE.sub("score=?", text) for text in now]
    for old, new in zip(SCORE.findall("".join(saved)), SCORE.findall("".join(now))):
        assert abs(float(old) - float(new)) < 0.001
