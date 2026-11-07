"""
Tests for evaluation.py: the labeled set, the scores worked out by hand (Recall@k, reciprocal rank, nDCG), the tuned
threshold, a variant measured on the keyword stand-in, and the script run after the pipeline: its sparse numbers
need no model, so they're real ones.
"""
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from support import fake_settings, sample_chunks
from support import keyword_retriever as retriever

from evaluation import QUESTIONS_FILE, LabeledQuestion, evaluate, load_questions, score_ranking, tune_threshold

FOLDER = Path(__file__).resolve().parent.parent
CHUNKS = sample_chunks()
TITLES = {chunk.metadata["title"] for chunk in CHUNKS}


def run(script: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(FOLDER / script), *args], cwd=FOLDER, capture_output=True, text=True,
                          encoding="utf-8", env={**os.environ, "GOOGLE_API_KEY": ""})


def test_the_labeled_set_has_44_answered_and_8_off_topic_questions():
    questions = load_questions(QUESTIONS_FILE)
    answered = [labeled for labeled in questions if labeled.answer]
    assert (len(questions), len(answered)) == (52, 44)
    assert {labeled.answer for labeled in answered} == TITLES                  # every article, and only those


def test_a_labeled_set_without_its_columns_fails(tmp_path):
    path = tmp_path / "questions.csv"
    path.write_text("text\nMy VPN\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs a question and an answer column"):
        load_questions(path)


def test_the_scores_of_one_ranking_worked_out_by_hand():
    found, reciprocal, ndcg = score_ranking(["b", "a", "c", "a"], "a", k=5, relevant=2)
    ideal = 1 + 1 / math.log2(3)
    assert (found, reciprocal) == (True, 0.5)
    assert ndcg == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / ideal)
    assert score_ranking(["b", "c"], "a", k=5, relevant=1) == (False, 0.0, 0.0)
    assert score_ranking(["b", "a"], "a", k=1, relevant=1)[0] is False          # rank 2 is past k = 1


def test_the_threshold_is_the_score_that_gets_most_decisions_right():
    best = [(LabeledQuestion("a", "VPN"), 0.9), (LabeledQuestion("b", "VPN"), 0.7), (LabeledQuestion("c", None), 0.4),
            (LabeledQuestion("d", None), 0.75)]
    assert tune_threshold(best) == (0.55, 3, 4)                                 # 0.4 below, 0.7 and 0.9 above
    assert tune_threshold([(LabeledQuestion("a", None), None)]) is None


def test_a_variant_is_measured_on_the_labeled_set():
    questions = [LabeledQuestion("My VPN keeps timing out", "VPN Connection Timeout"),
                 LabeledQuestion("No sound in Teams meetings", "Microsoft Teams Audio Issues"),
                 LabeledQuestion("What's on the cafeteria menu?", None)]
    ids = {chunk.metadata["title"]: chunk.metadata["doc_id"] for chunk in CHUNKS}
    chunks_of = {doc_id: sum(chunk.metadata["doc_id"] == doc_id for chunk in CHUNKS) for doc_id in ids.values()}
    scores, best = evaluate(retriever(min_score=0.3), questions, name="keywords", ids=ids, chunks_of=chunks_of, k=5)
    assert (scores.answered, scores.off_topic, scores.recall, scores.mrr) == (2, 1, 1.0, 1.0)
    assert (scores.no_match_right, scores.no_match_wrong) == (1, 0) and len(best) == 3


def test_the_script_measures_every_variant_after_the_pipeline(tmp_path):
    settings = fake_settings(tmp_path)
    assert run("evaluation.py", "--settings", str(settings)).returncode == 1          # nothing stored yet
    run("pipeline.py", "--settings", str(settings), "--manifest-path", str(tmp_path / "m.json"))
    result = run("evaluation.py", "--settings", str(settings))
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[0] == ("Retrieval on 52 labeled questions (44 answered by an article, 8 off-topic), k = 5, by "
                        "fake/gemini-embedding-001")
    assert [line.split()[0] for line in lines[2:6]] == ["dense", "sparse", "hybrid", "hybrid"]
    # The sparse search needs no model, so its numbers are real ones, even with the stand-in
    assert lines[3].split()[1:4] == ["1.00", "0.94", "0.92"]
    assert lines[-1].startswith("The stand-in model's vectors mean nothing")


def test_the_script_says_to_run_the_pipeline_first(tmp_path):
    result = run("evaluation.py", "--settings", str(fake_settings(tmp_path)))
    assert result.returncode == 1 and "run python pipeline.py first" in result.stderr
