"""
IT Knowledge Base: Measuring the Retriever
==========================================

Measures how well the retriever finds the article that answers each question of a labeled set, and how well it says
"no match" to the questions the knowledge base can't answer, so every change is measured, not guessed. It handles:
  1. The labeled set (data/eval_questions.csv): each question, and the title of the article that answers it, or
     none for an off-topic question
  2. The scores: Recall@k (the article is among the k chunks), MRR (1 / the rank of its first chunk), nDCG@k (each of
     its chunks counted by its rank), and the "no match" decisions, right and wrong
  3. The variants side by side: dense only, sparse only, hybrid, and hybrid with re-ranking
  4. The no-match threshold, tuned on the set: the dense similarity that gets the most decisions right

Run it after pipeline.py has stored the chunks:
    python evaluation.py                   # every variant, on data/eval_questions.csv
    python evaluation.py --k 3
"""
import argparse
import csv
import logging
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from config import MissingKeyError, load_api_key
from embedding import EmbeddingCache, make_embedding_model
from knowledge_base_loader import FOLDER, SETTINGS_FILE
from retriever import CrossEncoderReranker, KBRetriever, RetrievalError, WordOverlapReranker
from settings import KBSettings, load_settings
from vector_store import StoreError
from wiring import make_query_cache, make_retriever, make_store

logger = logging.getLogger(__name__)

QUESTIONS_FILE = FOLDER / "data" / "eval_questions.csv"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


@dataclass(frozen=True)
class LabeledQuestion:
    question: str
    answer: str | None          # the title of the article that answers it; None: nothing in the knowledge base does


@dataclass
class Scores:
    """One variant's results on the labeled set."""
    name: str
    answered: int = 0           # questions with an article
    off_topic: int = 0          # questions with none
    recall: float = 0.0         # Recall@k, over the answered questions
    mrr: float = 0.0
    ndcg: float = 0.0
    no_match_right: int = 0     # off-topic questions that got "no match"
    no_match_wrong: int = 0     # answered questions that got "no match"
    seconds: float = 0.0


def load_questions(path: Path) -> list[LabeledQuestion]:
    """The labeled set: a "question" and an "answer" column (an article's title, or blank for off-topic)."""
    with open(path, encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows or not {"question", "answer"} <= set(rows[0]):
        raise ValueError(f"The labeled set needs a question and an answer column: {path}")
    return [LabeledQuestion(row["question"].strip(), row["answer"].strip() or None) for row in rows
            if row["question"].strip()]


def score_ranking(doc_ids: list[str], answer_id: str, k: int, relevant: int) -> tuple[bool, float, float]:
    """(found in the top k, reciprocal rank, nDCG@k) for one question: a chunk counts when it's from the answer's
    article; `relevant` is how many of its chunks could be returned at best."""
    ranked = doc_ids[:k]
    gains = [1.0 if doc_id == answer_id else 0.0 for doc_id in ranked]
    first = gains.index(1.0) + 1 if 1.0 in gains else 0
    dcg = sum(gain / math.log2(place + 2) for place, gain in enumerate(gains))
    ideal = sum(1 / math.log2(place + 2) for place in range(min(relevant, k)))
    return bool(first), (1 / first if first else 0.0), (dcg / ideal if ideal else 0.0)


def evaluate(retriever: KBRetriever, questions: list[LabeledQuestion], *, name: str, ids: dict[str, str],
             chunks_of: dict[str, int], k: int) -> tuple[Scores, list[tuple[LabeledQuestion, float | None]]]:
    """A variant's Scores, and each question's best dense similarity (for tuning the threshold)."""
    scores = Scores(name)
    best: list[tuple[LabeledQuestion, float | None]] = []
    started = time.perf_counter()
    for labeled in questions:
        result = retriever.search(labeled.question)
        best.append((labeled, result.best_score))
        if labeled.answer is None:
            scores.off_topic += 1
            scores.no_match_right += result.no_match
            continue
        scores.answered += 1
        scores.no_match_wrong += result.no_match
        answer_id = ids[labeled.answer]
        relevant = min(chunks_of.get(answer_id, 1), retriever.max_per_article)
        found, reciprocal, ndcg = score_ranking([doc.metadata["doc_id"] for doc in result.docs], answer_id, k,
                                                relevant)
        scores.recall += found
        scores.mrr += reciprocal
        scores.ndcg += ndcg
    if scores.answered:
        scores.recall, scores.mrr, scores.ndcg = (value / scores.answered for value in
                                                  (scores.recall, scores.mrr, scores.ndcg))
    scores.seconds = time.perf_counter() - started
    return scores, best


def tune_threshold(best: list[tuple[LabeledQuestion, float | None]]) -> tuple[float, int, int] | None:
    """The dense similarity that gets the most no-match decisions right (answered questions at or above it,
    off-topic ones below), as (threshold, right, of), halfway between two neighbouring scores; None without scores."""
    known = sorted((score, labeled.answer is not None) for labeled, score in best if score is not None)
    if not known:
        return None
    values = [score for score, _ in known]
    choices = [values[0] - 0.01] + [(low + high) / 2 for low, high in zip(values, values[1:], strict=False)] + \
        [values[-1] + 0.01]
    right = [(sum((score >= threshold) == answered for score, answered in known), threshold) for threshold in choices]
    count, threshold = max(right, key=lambda pair: (pair[0], -pair[1]))
    return round(threshold, 4), count, len(known)


def collection_articles(retriever: KBRetriever) -> tuple[dict[str, str], dict[str, int]]:
    """({title: doc_id}, {doc_id: how many chunks}) of the articles in the collection."""
    ids: dict[str, str] = {}
    chunks: dict[str, int] = {}
    offset = None
    while True:
        points, offset = retriever.client.scroll(retriever.collection, limit=256, offset=offset,
                                                 with_payload=["metadata.title", "metadata.doc_id"])
        for point in points:
            metadata = point.payload["metadata"]
            ids[metadata["title"]] = metadata["doc_id"]
            chunks[metadata["doc_id"]] = chunks.get(metadata["doc_id"], 0) + 1
        if offset is None:
            return ids, chunks


def variants(settings: KBSettings, client, embeddings,
             query_cache: EmbeddingCache | None = None) -> list[tuple[str, KBRetriever]]:
    """Dense only, sparse only, hybrid, and hybrid re-ranked (by the configured re-ranker, or word overlap)."""
    reranker = CrossEncoderReranker(settings.retrieval.cross_encoder_model) \
        if settings.retrieval.reranker == "cross-encoder" else WordOverlapReranker()
    made = []
    for name, mode, rerank in [("dense", "dense", None), ("sparse", "sparse", None), ("hybrid", "hybrid", None),
                               (f"hybrid + {reranker.name}", "hybrid", reranker)]:
        made.append((name, make_retriever(settings, client, embeddings, mode=mode, reranker=rerank,
                                          query_cache=query_cache).build()))
    return made


def print_scores(results: list[Scores], *, k: int, model: str, tuned: tuple[float, int, int] | None) -> None:
    first = results[0]
    print(f"Retrieval on {first.answered + first.off_topic} labeled questions ({first.answered} answered by an "
          f"article, {first.off_topic} off-topic), k = {k}, by {model}")
    print(f"  {'variant':<28} {'Recall@' + str(k):>9} {'MRR':>6} {'nDCG@' + str(k):>7}   {'no match: right':>15} "
          f"{'wrong':>6}")
    for scores in results:
        print(f"  {scores.name:<28} {scores.recall:>9.2f} {scores.mrr:>6.2f} {scores.ndcg:>7.2f}   "
              f"{scores.no_match_right:>8} of {scores.off_topic:<4} {scores.no_match_wrong:>6}")
    if tuned:
        threshold, right, of = tuned
        print(f"The no-match threshold that gets the most decisions right on this set: min_score = {threshold} "
              f"(dense similarity), {right} of {of} right")
    if model.startswith("fake/"):
        print("The stand-in model's vectors mean nothing: the dense and hybrid numbers, and the threshold, are noise "
              "here. The sparse numbers are real. Run with Gemini for the others.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure the retriever on a labeled set of questions.")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE, help="default: kb_settings.toml")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_FILE, help="default: data/eval_questions.csv")
    parser.add_argument("--k", type=int, default=None, help="chunks per question (default: [retrieval] k)")
    parser.add_argument("--log-level", default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Measure every variant and print them side by side. Returns the exit code: 0 if it ran."""
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format=LOG_FORMAT)
    store = None
    try:
        settings = load_settings(args.settings)
        if args.k:
            settings = settings.model_copy(update={"retrieval": settings.retrieval.model_copy(update={"k": args.k})})
        questions = load_questions(args.questions)
        api_key = load_api_key() if settings.embeddings.provider == "google" else None
        store = make_store(settings.vectorstore, settings.embeddings.dimensions, args.settings)
        if store.current() is None:
            raise StoreError("There's no collection to measure yet: run python pipeline.py first")
        embeddings = make_embedding_model(provider=settings.embeddings.provider, model=settings.embeddings.model,
                                          dimensions=settings.embeddings.dimensions,
                                          timeout_seconds=settings.embeddings.timeout_seconds, api_key=api_key)
        built = variants(settings, store.client, embeddings, make_query_cache(settings.embeddings, args.settings))
        ids, chunks_of = collection_articles(built[0][1])
        unknown = sorted({labeled.answer for labeled in questions if labeled.answer and labeled.answer not in ids})
        if unknown:
            raise ValueError(f"The labeled set names articles the collection doesn't hold: {', '.join(unknown)}")
        results, tuned = [], None
        for name, retriever in built:
            scores, best = evaluate(retriever, questions, name=name, ids=ids, chunks_of=chunks_of,
                                    k=settings.retrieval.k)
            results.append(scores)
            if name == "dense":
                tuned = tune_threshold(best)
    except (FileNotFoundError, ValueError, MissingKeyError, StoreError, RetrievalError) as err:
        logger.error("%s", err)
        return 1
    finally:
        if store is not None:
            store.client.close()
    print_scores(results, k=settings.retrieval.k, model=settings.embeddings.model_name, tuned=tuned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
