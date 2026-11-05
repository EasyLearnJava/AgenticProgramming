"""BM25 + vector similarity → reciprocal rank fusion → transparent lexical reranking."""

import math
from collections import Counter

import numpy as np

from policylens.models import Chunk, SearchHit
from policylens.text import tokens
from policylens.grounding import terms as meaningful_terms


def bm25_scores(query: list[str], documents: list[list[str]]) -> np.ndarray:
    # Okapi BM25 with a positive IDF; repeated query tokens count once.
    counts = [Counter(doc) for doc in documents]
    average_length = sum(map(len, documents)) / max(len(documents), 1)
    scores = np.zeros(len(documents), dtype=np.float32)
    for term in set(query):
        frequency = sum(term in doc for doc in counts)
        idf = math.log(1 + (len(documents) - frequency + 0.5) / (frequency + 0.5))
        for i, doc in enumerate(counts):
            tf = doc[term]
            denominator = tf + 1.5 * (0.25 + 0.75 * len(documents[i]) / max(average_length, 1))
            scores[i] += idf * tf * 2.5 / max(denominator, 1e-9)
    return scores


def search(question: str, chunks: list[Chunk], matrix: np.ndarray, query_vector: list[float],
           candidates: int, top_k: int, source_ids: list[str] | None = None, profile=None) -> list[SearchHit]:
    selected = [i for i, c in enumerate(chunks) if not source_ids or c.source_id in source_ids]
    if not selected:
        return []
    chunks = [chunks[i] for i in selected]
    matrix = matrix[selected]
    query = np.asarray(query_vector, dtype=np.float32)
    if matrix.shape[1] != len(query):
        raise ValueError("Embedding dimensions changed. Rebuild the index.")
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    cosine = (matrix @ query) / np.maximum(norms, 1e-9)
    document_tokens = [profile.retrieval_tokens[c.id] if profile else tokens(c.text + " " + c.title + " " + c.location) for c in chunks]
    terms = sorted(meaningful_terms(question))
    keyword = bm25_scores(terms, document_tokens)
    fused = np.zeros(len(chunks), dtype=np.float32)
    for scores in [cosine, keyword]:
        for rank, i in enumerate(np.argsort(-scores)[:candidates]):
            if scores[i] > 0:
                fused[i] += 1 / (60 + rank + 1)
    pool = np.argsort(-fused)[:candidates]
    query_terms = set(terms)
    hits = []
    for i in pool:
        if fused[i] <= 0:
            continue
        coverage = len(query_terms & set(document_tokens[i])) / max(len(query_terms), 1)
        # RRF joins incompatible score scales; reranking adds exact-term coverage.
        score = 0.50 * fused[i] * 61 / 2 + 0.35 * coverage + 0.15 * max(float(cosine[i]), 0)
        hits.append(SearchHit(chunk=chunks[i], score=round(score, 4),
                              keyword_score=round(float(keyword[i]), 4),
                              vector_score=round(float(cosine[i]), 4), coverage=round(coverage, 4)))
    return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]

