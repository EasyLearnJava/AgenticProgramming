"""
Tests for rag_basics.ipynb: every cell run in order, as Jupyter runs them, then what the cells print. The first run
downloads the model, all-MiniLM-L6-v2 (about 90 MB), from Hugging Face; after that, it all runs on this machine.
"""
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
NOTEBOOK = FOLDER / "rag_basics.ipynb"
STATUE = "'The Statue of Liberty is a gift from France, located in New York, USA.'"


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


def test_every_cell_runs_and_the_setup_cells_print_nothing(ran):
    assert len(ran) == 6
    assert not [output for cell in ran for output in cell.outputs if output.output_type == "error"]
    assert [printed(cell) for cell in ran[:3]] == ["", "", ""]          # the setup cells print nothing


def test_parent_doc_retrieval_finds_the_statue_then_the_colosseum(ran):
    assert printed(ran[3]) == (f"Parent-doc results: [[{STATUE}, "
                               "'The Colosseum is in Rome, Italy. It is an ancient amphitheater.']]\n")


def test_the_reworded_query_brings_the_eiffel_tower_second(ran):
    assert printed(ran[4]) == (f"Reformulated results: [[{STATUE}, "
                               "'The Eiffel Tower is in Paris, France. It is one of the most famous landmarks.']]\n")


def test_window_retrieval_returns_sentences_not_whole_documents(ran):
    assert printed(ran[5]) == f"Window results: [[{STATUE}, 'It is one of the most famous landmarks.']]\n"


def test_the_saved_notebook_shows_what_a_run_prints(ran):
    # The outputs saved in the notebook, shown by GitHub and Jupyter before a run, are a real run's
    saved = [cell for cell in nbformat.read(NOTEBOOK, as_version=4).cells if cell.cell_type == "code"]
    assert [printed(cell) for cell in saved] == [printed(cell) for cell in ran]
