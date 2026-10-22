"""
Tests for vector_space_models_and_embeddings.ipynb: every cell run in order, as Jupyter runs them, then what the
cells print. The first run downloads the model, all-MiniLM-L6-v2 (about 90 MB), from Hugging Face; after that, it
all runs on this machine. Outside Colab, the first cell installs nothing.
"""
import re
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

FOLDER = Path(__file__).resolve().parent.parent   # the project folder (this file sits in its tests/ folder)
NOTEBOOK = FOLDER / "vector_space_models_and_embeddings.ipynb"
NUMBER = re.compile(r"-?\d+\.\d+")                 # a score, a coordinate or a size, as the cells print them
COLAB = ("https://colab.research.google.com/github/EasyLearnJava/AgenticProgramming/blob/main/projects/RAG/"
         "IT%20Knowledge%20Base/RAG%20series/1.Vector%20Space%20Models%20and%20Embeddings%20in%20RAGs/"
         "vector_space_models_and_embeddings.ipynb")


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


def test_every_cell_runs_and_the_setup_cell_installs_nothing_outside_colab(ran):
    assert len(ran) == 10
    assert not [output for cell in ran for output in cell.outputs if output.output_type == "error"]
    assert printed(ran[0]) == ""


def test_each_sentence_becomes_384_numbers_and_the_money_sentences_are_closest(ran):
    lines = printed(ran[1]).splitlines()
    assert lines[0] == "(3, 384)"
    grid = [[float(n) for n in re.findall(r"\d+\.\d*", line)] for line in lines[1:]]   # "1." is a value too
    assert grid[0][1] > grid[0][2] > grid[1][2]       # money–loan, then money–river, then loan–river


def test_tfidf_gives_the_two_car_documents_no_similarity(ran):
    lines = printed(ran[2]).splitlines()
    assert lines[0] == "(3, 10)"
    assert lines[2].startswith("[[1.    0.    ")      # document 1 vs document 2: 0.0, no shared word


def test_king_minus_man_plus_woman_lands_nearest_queen(ran):
    assert printed(ran[3]).startswith("[('queen', ")


def test_search_and_ranking_put_the_meaning_match_first(ran):
    assert printed(ran[4]).splitlines()[0].endswith("  Chatbots for content creation")
    assert printed(ran[6]).splitlines()[0].endswith("  Global warming impacts on agriculture")
    pairs = dict(line.rsplit(": ", 1) for line in printed(ran[5]).splitlines())
    assert float(pairs["doctor · physician"]) > float(pairs["doctor · banana"])
    assert float(pairs["car · automobile"]) > float(pairs["car · banana"])


def test_the_metrics_and_the_storage_sum_print_exact_values(ran):
    assert printed(ran[7]) == ("a,b  cosine 1.000  euclidean 2.236  dot 10.000\n"
                               "a,c  cosine 0.000  euclidean 3.162  dot 0.000\n"
                               "this model's vectors have length 1.0\n")
    assert printed(ran[9]) == "3.07 TB as float32; 1.02 TB at 256 dimensions\n"


def test_the_saved_notebook_shows_what_a_run_prints(ran):
    # The outputs saved in the notebook, shown by GitHub and Colab before a run, are a real run's. A number's last
    # digit can differ from one computer to another, so numbers are compared to within 0.01, the rest exactly
    # (rounded first: -0.42 - -0.43 comes out as 0.010000000000000009 in floating point).
    saved = [printed(cell) for cell in nbformat.read(NOTEBOOK, as_version=4).cells if cell.cell_type == "code"]
    now = [printed(cell) for cell in ran]
    assert [NUMBER.sub("#", text) for text in saved] == [NUMBER.sub("#", text) for text in now]
    for old, new in zip(NUMBER.findall("".join(saved)), NUMBER.findall("".join(now))):
        assert round(abs(float(old) - float(new)), 6) <= 0.01


def test_the_notebook_opens_with_its_colab_link():
    first = nbformat.read(NOTEBOOK, as_version=4).cells[0]
    assert first.cell_type == "markdown" and f'<a href="{COLAB}"' in first.source
