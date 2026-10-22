"""
Tests for rag_basics.ipynb: every cell run in order, as Jupyter runs them, then what the cells print and draw. The
first run downloads the model, all-MiniLM-L6-v2 (about 90 MB), from Hugging Face; after that, it all runs on this
machine.
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
LABELS = ["D1", "D2", "D3", "D4", "Q"]   # the 4 documents and the query, as cells 8 and 9 name them
NUMBER = re.compile(r"-?\d+\.\d*")      # a number with a decimal point, as the cells print them
POINT = re.compile(r"^(D\d|Q): \((-?\d+\.\d+), (-?\d+\.\d+)(?:, (-?\d+\.\d+))?\)", re.MULTILINE)
PLOTLY = "application/vnd.plotly.v1+json"


def printed(cell) -> str:
    """What a code cell printed (its stdout)."""
    return "".join(output.text for output in cell.outputs
                   if output.output_type == "stream" and output.name == "stdout")


def points(cell) -> dict:
    """The coordinates a graph cell printed, by label: {"D1": (x, y), ...}, or (x, y, z) in 3D."""
    return {label: tuple(float(n) for n in numbers if n) for label, *numbers in POINT.findall(printed(cell))}


@pytest.fixture(scope="module")
def ran():
    """The notebook's code cells after a run of the whole notebook, in a new kernel."""
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    NotebookClient(notebook, timeout=600, resources={"metadata": {"path": str(FOLDER)}}).execute()
    return [cell for cell in notebook.cells if cell.cell_type == "code"]


def test_every_cell_runs_without_an_error(ran):
    assert len(ran) == 9
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


def test_each_document_is_384_numbers(ran):
    text = printed(ran[5])
    assert text.startswith("Embedding matrix shape: (4, 384)\n")
    assert text.count("Dimensions: 384") == 4
    assert text.count("First 10 values: [") == 4


def test_the_query_is_most_like_the_eiffel_tower_sentence(ran):
    documents_part, query_part = printed(ran[6]).split("Query vs documents:")
    assert documents_part.count("1. ") + documents_part.count("1.]") == 4   # each document with itself
    scores = {label: float(score) for label, score in re.findall(r"^(D\d): (\d\.\d+)", query_part, re.MULTILINE)}
    assert list(scores) == LABELS[:4]
    assert max(scores, key=scores.get) == "D1" and abs(scores["D1"] - 0.850) < 0.002


def test_the_2d_graph_draws_the_query_next_to_the_eiffel_tower(ran):
    assert any("image/png" in output.get("data", {}) for output in ran[7].outputs)
    xy = points(ran[7])
    assert list(xy) == LABELS and all(len(point) == 2 for point in xy.values())
    distance = {label: (xy[label][0] - xy["Q"][0]) ** 2 + (xy[label][1] - xy["Q"][1]) ** 2 for label in LABELS[:4]}
    assert min(distance, key=distance.get) == "D1"


def test_the_3d_graph_has_the_five_points(ran):
    figures = [output["data"][PLOTLY] for output in ran[8].outputs if PLOTLY in output.get("data", {})]
    assert len(figures) == 1
    traces = figures[0]["data"]
    assert [trace["name"] for trace in traces] == LABELS
    assert all(trace["text"] == [trace["name"]] for trace in traces)   # one point each, with its label
    xyz, xy = points(ran[8]), points(ran[7])
    assert list(xyz) == LABELS
    assert all(xyz[label][:2] == xy[label] for label in LABELS)   # PCA's first 2 directions are the 2D graph's


def test_the_saved_notebook_shows_what_a_run_prints(ran):
    # The outputs saved in the notebook, shown by GitHub and Jupyter before a run, are a real run's. A number's last
    # digit can differ from one computer to another, so the numbers are compared to within 0.002, and the rest of
    # the text exactly but for its spacing (NumPy pads its arrays to line up their numbers).
    saved = [printed(cell) for cell in nbformat.read(NOTEBOOK, as_version=4).cells if cell.cell_type == "code"]
    now = [printed(cell) for cell in ran]
    assert [" ".join(NUMBER.sub("?", text).split()) for text in saved] == \
           [" ".join(NUMBER.sub("?", text).split()) for text in now]
    for old, new in zip(NUMBER.findall("".join(saved)), NUMBER.findall("".join(now))):
        assert abs(float(old) - float(new)) < 0.002
