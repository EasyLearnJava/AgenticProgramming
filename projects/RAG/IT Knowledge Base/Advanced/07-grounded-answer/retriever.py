"""
IT Knowledge Base: The Retriever
================================

Finds the chunks that answer a question, and says so when none do. It handles:
  1. Cleaning the question (spaces, repeated punctuation), and reading label filters from it ("VPN", "High
     priority") with kb_settings.toml's spellings, unless the caller passes its own
  2. Searching two ways: by meaning (the dense vector) and by exact words (the sparse vector), each for 20
     candidates, merged by reciprocal rank fusion (RRF); or one way only, for comparing
  3. A "no match" when even the best candidate's similarity to the question is below a threshold
  4. Re-ranking the candidates with a re-ranker passed in: a cross-encoder model, or one that scores shared words
  5. Variety: at most 2 chunks from one article, picked by maximal marginal relevance (MMR)
  6. A cache of question vectors, so a repeated question costs no call; a hook that rewrites a question into
     several (multi-query), each searched, all fused

    KBRetriever(client=..., embeddings=..., model_name="google/gemini-embedding-001").search("vpn keeps dropping???")
      ->  RetrievalResult(docs=[the 5 best chunks], filters={"system": "VPN"}, no_match=False, ...)
"""
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from qdrant_client import models

from article import Spellings
from embedding import EmbeddingCache, utc_now
from utils import short_hash, spelling_key
from vector_store import ALIAS, DENSE, SPARSE, sparse_vector

# The defaults: kb_settings.toml's [retrieval] can change each one
MODE = "hybrid"             # "dense", "sparse" or "hybrid"
K = 5                       # chunks returned
CANDIDATES = 20             # chunks each search finds, for fusing and re-ranking
RRF_K = 60                  # RRF's constant: a chunk at rank r scores 1 / (60 + r) in each list it's in
MIN_SCORE = -1.0            # the best candidate's dense similarity must reach this, or it's "no match"; -1: never
MAX_PER_ARTICLE = 2         # chunks from one article, at most
MMR_LAMBDA = 0.7            # 1: by relevance only; lower: more variety
READ_FILTERS = True         # read label filters from the question

# Repeated punctuation, such as "???" or "!!!", made one
REPEATED_MARK = re.compile(r"([?!.,])\1+")


class RetrievalError(RuntimeError):
    """The retriever can't run as configured; the message says why and what to do."""


def clean_question(question: str) -> str:
    """The question with its spaces made single and repeated punctuation made one: "vpn  wont work???" ->
    "vpn wont work?"."""
    return REPEATED_MARK.sub(r"\1", " ".join(question.split()))


# The labels read from a question: a category ("Network", "Security") is too common a word to filter on safely
FILTER_LABELS = ("system", "priority")


def read_filters(question: str, spellings: dict[str, Spellings]) -> dict[str, str]:
    """
    Label filters read from the question with the spellings tables: a system named in it ("Wi-Fi", "Active
    Directory": any spelling, as whole words), and a priority written next to the word "priority" ("High priority",
    "priority: critical"). A system is filtered only when exactly one is named: "VPN on my laptop" names two, so
    neither is used.
    """
    words = [spelling_key(word) for word in re.findall(r"\w+", question)]
    runs = {"".join(words[start:start + size]) for size in (1, 2, 3) for start in range(len(words) - size + 1)}
    found = {}
    for label in FILTER_LABELS:
        table = spellings.get(label)
        if table is None:
            continue
        if label == "priority":
            match = re.search(r"\b(\w+)\s+priority\b|\bpriority\W+(\w+)", question, re.IGNORECASE)
            value = table.right_spelling(next(group for group in match.groups() if group)) if match else None
            if value:
                found[label] = value
            continue
        named = {right for right, others in table.table.items()
                 if any(spelling_key(spelling) in runs for spelling in (right, *others))}
        if len(named) == 1:
            found[label] = named.pop()
    return found


# -------------------------------------------------
# Re-rankers - Read the Question and Each Chunk Together
# -------------------------------------------------

class Reranker(Protocol):
    name: str

    def build(self) -> None: ...

    def score(self, question: str, texts: list[str]) -> list[float]: ...


class WordOverlapReranker:
    """
    Scores each chunk by the question's words it holds, each weighed by how rare it is among the candidates (a
    small BM25): no model, no call. Better than no re-ranking for exact terms; a cross-encoder reads meaning too.
    """
    name = "word-overlap"

    def build(self) -> None:
        """Nothing to load."""

    def score(self, question: str, texts: list[str]) -> list[float]:
        asked = set(re.findall(r"\w+", question.casefold()))
        chunks = [re.findall(r"\w+", text.casefold()) for text in texts]
        average = sum(map(len, chunks)) / len(chunks) if chunks else 1
        scores = []
        for words in chunks:
            score = 0.0
            for word in asked:
                count = words.count(word)
                if not count:
                    continue
                holding = sum(word in other for other in chunks)
                rarity = math.log(1 + (len(chunks) - holding + 0.5) / (holding + 0.5))
                score += rarity * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(words) / average))
            scores.append(score)
        return scores


class CrossEncoderReranker:
    """
    A cross-encoder reads the question and a chunk together and scores how well the chunk answers it: the most
    accurate re-ranker, and the slowest. It needs sentence-transformers, which isn't in requirements.txt (it brings
    PyTorch); build() loads the model, downloading it the first time.
    """
    name = "cross-encoder"

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None

    def build(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError:
            raise RetrievalError("The cross-encoder re-ranker needs sentence-transformers: pip install "
                                 "sentence-transformers, or set reranker = \"word-overlap\" or \"none\"") from None
        self.model = CrossEncoder(self.model_name)

    def score(self, question: str, texts: list[str]) -> list[float]:
        if self.model is None:
            raise RetrievalError("The cross-encoder isn't loaded: call build() first")
        return [float(score) for score in self.model.predict([(question, text) for text in texts])]


# -------------------------------------------------
# KBRetriever Class - Hybrid Search, Checked
# -------------------------------------------------

@dataclass
class Candidate:
    """A chunk one of the searches found, with each score it got."""
    point_id: str
    doc: Document
    vector: list[float] | None = None    # its dense vector, for MMR
    dense: float | None = None           # its similarity to the question (cosine)
    sparse: float | None = None          # its sparse score (shared words, weighed by IDF)
    fused: float = 0.0                   # its RRF score
    rerank: float | None = None


@dataclass
class RetrievalResult:
    """What search() found, and how."""
    question: str                        # as cleaned
    queries: list[str]                   # the question, and its rewrites
    filters: dict[str, str]              # the label filters used
    docs: list[Document] = field(default_factory=list)   # the chunks, best first; none when no_match
    no_match: bool = False
    best_score: float | None = None      # the best candidate's dense similarity: what the threshold is compared with
    candidates: int = 0                  # chunks the searches found, before the cut
    cached_query: bool = False           # the question's vector came from the cache
    seconds: float = 0.0


class KBRetriever(BaseRetriever):
    """
    A LangChain retriever over the knowledge base's Qdrant collection.

    Step 1: Configure: every part is passed in (the Qdrant client, the embedding model, the re-ranker, the
            rewriter); making it reads nothing and calls nothing
    Step 2: build() loads the re-ranker's model, if it has one
    Step 3: search() gives a RetrievalResult; invoke(), inherited from BaseRetriever, gives its chunks
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Any                                   # a QdrantClient
    embeddings: Embeddings
    model_name: str                               # "<provider>/<model>": the question cache's key
    collection: str = ALIAS
    query_cache: EmbeddingCache | None = None
    mode: Literal["dense", "sparse", "hybrid"] = MODE
    k: int = K
    candidates: int = CANDIDATES
    rrf_k: int = RRF_K
    min_score: float = MIN_SCORE
    max_per_article: int = MAX_PER_ARTICLE
    mmr_lambda: float = MMR_LAMBDA
    reranker: Any = None                          # a Reranker, or None
    spellings: dict[str, Spellings] = {}          # for reading filters from the question
    read_filters: bool = READ_FILTERS
    rewrite: Callable[[str], list[str]] | None = None   # a question -> other ways to ask it

    def build(self) -> "KBRetriever":
        """Load what the parts need (the re-ranker's model); a model that can't be loaded fails here, at start."""
        if self.reranker is not None:
            self.reranker.build()
        return self

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        return self.search(query).docs

    def search(self, question: str, filters: dict[str, str] | None = None) -> RetrievalResult:
        """The chunks that answer the question, best first, or a "no match"."""
        started = time.perf_counter()
        cleaned = clean_question(question)
        if filters is None:
            filters = read_filters(cleaned, self.spellings) if self.read_filters else {}
        queries = [cleaned, *(self.rewrite(cleaned) if self.rewrite else [])]
        result = RetrievalResult(question=cleaned, queries=queries, filters=dict(filters))
        selector = models.Filter(must=[models.FieldCondition(key=f"metadata.{label}",
                                                             match=models.MatchValue(value=value))
                                       for label, value in filters.items()]) if filters else None

        # Step 1: Each search, for each way of asking, as a ranked list
        found: dict[str, Candidate] = {}
        lists: list[list[str]] = []
        query_vector = None
        for query in queries:
            if self.mode in ("dense", "hybrid"):
                vector, cached = self._question_vector(query)
                query_vector = query_vector or vector
                result.cached_query = result.cached_query or cached
                lists.append(self._dense(vector, selector, found))
            if self.mode in ("sparse", "hybrid"):
                lists.append(self._sparse(query, selector, found))

        # Step 2: Fuse the lists: a chunk scores 1 / (rrf_k + rank) in each one it's in
        for ranked in lists:
            for rank, point_id in enumerate(ranked, 1):
                found[point_id].fused += 1 / (self.rrf_k + rank)
        ordered = sorted(found.values(), key=lambda candidate: candidate.fused, reverse=True)
        result.candidates = len(ordered)

        # Step 3: No match when even the best similarity is too low (the dense score: sparse ones aren't comparable)
        similarities = [candidate.dense for candidate in ordered if candidate.dense is not None]
        result.best_score = max(similarities) if similarities else None
        if not ordered or (result.best_score is not None and result.best_score < self.min_score):
            result.no_match = True
            result.seconds = time.perf_counter() - started
            return result

        # Step 4: Re-rank, then pick for relevance and variety
        if self.reranker is not None:
            scores = self.reranker.score(cleaned, [candidate.doc.page_content for candidate in ordered])
            for candidate, score in zip(ordered, scores, strict=True):
                candidate.rerank = score
            ordered.sort(key=lambda candidate: candidate.rerank, reverse=True)
        picked = self._pick(ordered)
        result.docs = [self._labelled(candidate) for candidate in picked]
        result.seconds = time.perf_counter() - started
        return result

    def _question_vector(self, query: str) -> tuple[list[float], bool]:
        """The question's vector, from the cache when it was asked before; (vector, it came from the cache)."""
        key = short_hash(query)
        if self.query_cache is not None:
            known = self.query_cache.get([key])
            if key in known:
                return known[key][0], True
        vector = [float(value) for value in self.embeddings.embed_query(query)]
        if self.query_cache is not None:
            self.query_cache.put({key: vector}, utc_now().isoformat(timespec="seconds"))
        return vector, False

    def _dense(self, vector: list[float], selector, found: dict[str, Candidate]) -> list[str]:
        points = self.client.query_points(self.collection, query=vector, using=DENSE, query_filter=selector,
                                          limit=self.candidates, with_payload=True, with_vectors=[DENSE]).points
        for point in points:
            candidate = self._candidate(point, found)
            candidate.dense = max(candidate.dense or -1.0, point.score)
            candidate.vector = candidate.vector or point.vector[DENSE]
        return [str(point.id) for point in points]

    def _sparse(self, query: str, selector, found: dict[str, Candidate]) -> list[str]:
        points = self.client.query_points(self.collection, query=sparse_vector(query), using=SPARSE,
                                          query_filter=selector, limit=self.candidates, with_payload=True).points
        for point in points:
            candidate = self._candidate(point, found)
            candidate.sparse = max(candidate.sparse or 0.0, point.score)
        return [str(point.id) for point in points]

    @staticmethod
    def _candidate(point, found: dict[str, Candidate]) -> Candidate:
        if str(point.id) not in found:
            found[str(point.id)] = Candidate(str(point.id), Document(page_content=point.payload["page_content"],
                                                                     metadata=point.payload["metadata"]))
        return found[str(point.id)]

    def _pick(self, ordered: list[Candidate]) -> list[Candidate]:
        """The k best, at most max_per_article from one article, each next pick the one that adds most: relevance
        (its place in the order) against likeness to the ones picked already (MMR, on the dense vectors)."""
        relevance = {candidate.point_id: 1 - place / len(ordered) for place, candidate in enumerate(ordered)}
        picked: list[Candidate] = []
        per_article: dict[str, int] = {}
        pool = list(ordered)
        while pool and len(picked) < self.k:
            def gain(candidate: Candidate) -> float:
                likeness = max((_cosine(candidate.vector, chosen.vector) for chosen in picked
                                if candidate.vector and chosen.vector), default=0.0)
                return self.mmr_lambda * relevance[candidate.point_id] - (1 - self.mmr_lambda) * likeness

            best = max(pool, key=gain)
            pool.remove(best)
            article = best.doc.metadata.get("doc_id", "")
            if per_article.get(article, 0) >= self.max_per_article:
                continue
            per_article[article] = per_article.get(article, 0) + 1
            picked.append(best)
        return picked

    @staticmethod
    def _labelled(candidate: Candidate) -> Document:
        """The chunk, with its scores added to its metadata (None for a search that didn't find it)."""
        scores = {"score_dense": candidate.dense, "score_sparse": candidate.sparse,
                  "score_fused": round(candidate.fused, 6), "score_rerank": candidate.rerank}
        return Document(page_content=candidate.doc.page_content, metadata={**candidate.doc.metadata, **scores})


def _cosine(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    size = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / size if size else 0.0
