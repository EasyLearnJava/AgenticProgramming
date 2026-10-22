"""
Tests for rag_basics.ipynb: every cell run in order, as Jupyter runs them, then what the cells print. The first run
downloads the two models, all-MiniLM-L6-v2 and cross-encoder/ms-marco-MiniLM-L-6-v2 (about 90 MB each), from Hugging
Face; after that, it all runs on this machine.
"""
import re
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
NOTEBOOK = FOLDER / "rag_basics.ipynb"
TOWERS = ["The Eiffel Tower is in Paris.", "Montparnasse Tower is in Paris.", "Tokyo Tower is in Tokyo."]
SCORE = re.compile(r"score=(-?\d+\.\d+)")   # a score as cell 4 prints it


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
    assert len(ran) == 5
    assert not [output for cell in ran for output in cell.outputs if output.output_type == "error"]
    assert [printed(cell) for cell in ran[:2]] == ["", ""]


def test_the_baseline_finds_the_eiffel_tower_then_the_other_towers(ran):
    assert printed(ran[2]) == "Baseline Retrieval Results:\n" + "".join(f"- {doc}\n" for doc in TOWERS)


def test_the_cross_encoder_scores_the_3_and_keeps_their_order(ran):
    lines = printed(ran[3]).splitlines()
    assert lines[:2] == ["", "Reranked Results (Cross-Encoder):"]
    assert [SCORE.sub("score=?", line) for line in lines[2:]] == [f"- {doc} (score=?)" for doc in TOWERS]
    scores = [float(score) for score in SCORE.findall(printed(ran[3]))]
    assert scores[0] > 0 > scores[1]                  # the Eiffel Tower a strong match, the other towers weak


def test_precision_at_1_is_1_before_and_after_reranking(ran):
    assert printed(ran[4]) == "\nPrecision@1 Baseline: 1\nPrecision@1 Reranked: 1\n"


def test_the_saved_notebook_shows_what_a_run_prints(ran):
    # The outputs saved in the notebook, shown by GitHub and Jupyter before a run, are a real run's. A score's last
    # digit can differ from one computer to another, so the scores are compared to within 0.001, the rest exactly.
    saved = [printed(cell) for cell in nbformat.read(NOTEBOOK, as_version=4).cells if cell.cell_type == "code"]
    now = [printed(cell) for cell in ran]
    assert [SCORE.sub("score=?", text) for text in saved] == [SCORE.sub("score=?", text) for text in now]
    for old, new in zip(SCORE.findall("".join(saved)), SCORE.findall("".join(now))):
        assert abs(float(old) - float(new)) < 0.001
