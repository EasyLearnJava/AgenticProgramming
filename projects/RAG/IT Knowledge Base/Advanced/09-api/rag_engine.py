"""
IT Knowledge Base: The RAG Engine
=================================

The dependable core a service is built on: every part passed in, every outside call bounded, repeated questions
answered from a cache, every stage traced, and follow-up questions understood. It handles:
  1. RAGEngine: the retriever and the answerer (Advanced 06 and 07), each behind a circuit breaker, with a deadline on
     every question; ask(), and aask() for code that's already async; stream() and astream(), the answer as it's
     written
  2. CircuitBreaker: after `failures` failures in a row, calls stop for `reset_seconds` and fail at once; then one call
     is let through to try again; a streamed call is guarded whole
  3. AnswerCache: answers kept in SQLite under the question, found exactly or by meaning, for the same prompt
     version, model and knowledge base, for `ttl_seconds`
  4. ConversationMemory: the last turns of each session; a follow-up ("and on Mac?") is rewritten into a complete
     question, by the condenser passed in, before it's searched
  5. Trace: a span per stage (condense, cache, retrieve, answer) with its time, chunk IDs, tokens and cost
  6. stats(): what the engine is really running with, read from its parts

    engine.ask("My VPN keeps timing out", session="s1")  ->  EngineAnswer(answer=GroundedAnswer(...), trace=Trace(...))
"""
import asyncio
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

from answering import Answerer, GroundedAnswer
from retriever import KBRetriever
from utils import short_hash, simplify

# The defaults: kb_settings.toml's [engine] can change each one
QUESTION_TIMEOUT_SECONDS = 60.0
BREAKER_FAILURES = 3
BREAKER_RESET_SECONDS = 30.0
CACHE_TTL_SECONDS = 86_400.0          # a day
SEMANTIC_THRESHOLD = 0.95             # a question this close in meaning to a cached one gets its answer
MEMORY_TURNS = 5

# A short follow-up that leans on what came before: "and on Mac?", "what about it", "also for Teams?"
FOLLOW_UP = re.compile(r"^(and|also|what about|how about|same|but)\b|\b(it|that|this|they|them|those)\b",
                       re.IGNORECASE)


class EngineError(RuntimeError):
    """The engine couldn't answer; the message says why."""


class CircuitOpenError(EngineError):
    """A part kept failing, so calls to it stopped for a while: this one failed at once. retry_after: the seconds
    until one call is let through again."""

    def __init__(self, message: str, *, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class DeadlineError(EngineError):
    """The question took longer than the engine allows."""


# -------------------------------------------------
# CircuitBreaker - Stop Calling a Part That Keeps Failing
# -------------------------------------------------

class CircuitBreaker:
    """
    Closed: calls go through. After `failures` failures in a row: open, and every call fails at once for
    `reset_seconds`. Then half-open: one call goes through; it closes the breaker if it works, opens it again if not.
    """

    def __init__(self, name: str, *, failures: int = BREAKER_FAILURES, reset_seconds: float = BREAKER_RESET_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.failures = failures
        self.reset_seconds = reset_seconds
        self.clock = clock
        self.state = "closed"
        self.failed_in_a_row = 0
        self.opened_at = 0.0
        self._lock = threading.Lock()       # a server's questions run in several threads at once

    def call(self, function: Callable, *args, **kwargs):
        with self.guard():
            return function(*args, **kwargs)

    @contextmanager
    def guard(self) -> Iterator[None]:
        """The `with` block is one call through the breaker: it fails at once while the breaker is open, and how it
        ends counts. A streamed call is guarded whole this way."""
        with self._lock:
            if self.state == "open":
                waited = self.clock() - self.opened_at
                if waited < self.reset_seconds:
                    left = self.reset_seconds - waited
                    raise CircuitOpenError(f"The {self.name} failed {self.failures} times in a row: calls to it "
                                           f"stopped for {self.reset_seconds:.0f} s ({left:.0f} s left)",
                                           retry_after=left)
                self.state = "half-open"
        try:
            yield
        except Exception:
            with self._lock:
                self.failed_in_a_row += 1
                if self.state == "half-open" or self.failed_in_a_row >= self.failures:
                    self.state, self.opened_at = "open", self.clock()
            raise
        with self._lock:
            self.state, self.failed_in_a_row = "closed", 0


# -------------------------------------------------
# Trace - A Span per Stage
# -------------------------------------------------

@dataclass
class Span:
    name: str
    seconds: float
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    """One question's way through the engine: a span per stage, in order."""
    question: str
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    spans: list[Span] = field(default_factory=list)

    @contextmanager
    def span(self, name: str) -> Iterator[dict[str, Any]]:
        """Time a stage; its fields are whatever the `with` block puts in the dict it's given. A stage that fails is
        recorded too, with its error."""
        fields: dict[str, Any] = {}
        started = time.perf_counter()
        try:
            yield fields
        except Exception as err:
            fields["error"] = f"{type(err).__name__}: {err}"
            raise
        finally:
            self.spans.append(Span(name, time.perf_counter() - started, fields))

    @property
    def seconds(self) -> float:
        return sum(span.seconds for span in self.spans)


# -------------------------------------------------
# AnswerCache - Answers Already Given
# -------------------------------------------------

class AnswerCache:
    """
    Answers in SQLite, each kept under a scope (the prompt's version, the model and the knowledge base's version) and
    its question: found exactly, or by meaning (a question vector at least `threshold` alike), for `ttl_seconds`. A
    new prompt, model or knowledge base is a new scope, so a stale answer is never served.
    """

    def __init__(self, path: str | Path, *, ttl_seconds: float = CACHE_TTL_SECONDS,
                 threshold: float = SEMANTIC_THRESHOLD, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self.threshold = threshold
        self.clock = clock

    def get(self, question: str, vector: list[float] | None, *, scope: str) -> tuple[dict, str] | None:
        """(the answer, "exact" or "meaning") when a fresh answer in this scope fits; None if not."""
        if not self.path.exists():
            return None
        fresh_after = self.clock() - self.ttl_seconds
        with self._connection() as db:
            row = db.execute("SELECT answer FROM answers WHERE key = ? AND created_at > ?",
                             (self._key(question, scope), fresh_after)).fetchone()
            if row:
                return json.loads(row[0]), "exact"
            if vector is None:
                return None
            best, best_answer = self.threshold, None
            for stored, answer in db.execute("SELECT vector, answer FROM answers WHERE scope = ? AND created_at > ? "
                                             "AND vector IS NOT NULL", (scope, fresh_after)):
                likeness = _cosine(vector, json.loads(stored))
                if likeness >= best:
                    best, best_answer = likeness, answer
        return (json.loads(best_answer), "meaning") if best_answer else None

    def put(self, question: str, vector: list[float] | None, answer: dict, *, scope: str) -> None:
        with self._connection() as db, db:
            db.execute("INSERT OR REPLACE INTO answers VALUES (?, ?, ?, ?, ?, ?)",
                       (self._key(question, scope), scope, question, json.dumps(vector) if vector else None,
                        json.dumps(answer), self.clock()))

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._connection() as db:
            return db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]

    @staticmethod
    def _key(question: str, scope: str) -> str:
        return short_hash(f"{scope}\x1f{simplify(question)}")

    def _connection(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path)
            db.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, scope TEXT NOT NULL, question TEXT "
                       "NOT NULL, vector TEXT, answer TEXT NOT NULL, created_at REAL NOT NULL)")
            return closing(db)
        except (sqlite3.Error, OSError) as err:
            raise EngineError(f"The answer cache can't be used ({err}): {self.path.resolve()}. Delete it.") from None


# -------------------------------------------------
# ConversationMemory - Each Session's Last Turns
# -------------------------------------------------

class ConversationMemory:
    """The last `turns` questions and answers of each session, in this process."""

    def __init__(self, *, turns: int = MEMORY_TURNS):
        self.turns = turns
        self._sessions: dict[str, deque] = {}

    def history(self, session: str) -> list[tuple[str, str]]:
        return list(self._sessions.get(session, ()))

    def add(self, session: str, question: str, answer: str) -> None:
        self._sessions.setdefault(session, deque(maxlen=self.turns)).append((question, answer))

    def __len__(self) -> int:
        return len(self._sessions)


def condense_by_rule(history: list[tuple[str, str]], question: str) -> str:
    """The stand-in condenser: a short follow-up that leans on what came before ("and on Mac?") is joined to the last
    question; anything else is asked as it is."""
    if history and len(question.split()) <= 6 and FOLLOW_UP.search(question):
        return f"{history[-1][0].rstrip('?.! ')}, {question}"
    return question


def condense_with(chat, prompt: str) -> Callable[[list[tuple[str, str]], str], str]:
    """A condenser that asks a chat model (with the prompt from prompts/condense-v1.txt) to rewrite a follow-up into a
    complete question."""
    def condense(history: list[tuple[str, str]], question: str) -> str:
        turns = "\n".join(f"Q: {asked}\nA: {answered}" for asked, answered in history)
        reply = chat.invoke([SystemMessage(prompt), HumanMessage(f"Conversation so far:\n{turns}\n\nFollow-up: "
                                                                 f"{question}")])
        return str(getattr(reply, "content", reply)).strip() or question
    return condense


# -------------------------------------------------
# RAGEngine Class - The Core, Guarded and Traced
# -------------------------------------------------

@dataclass
class EngineAnswer:
    question: str                  # as asked
    asked: str                     # as searched: the follow-up rewritten into a complete question
    answer: GroundedAnswer
    trace: Trace
    cached: str = ""               # "exact" or "meaning" when it came from the cache
    cost_usd: float = 0.0


class RAGEngine:
    """
    The retriever and the answerer as one dependable service.

    Step 1: Configure: every part is passed in (wiring.make_engine() builds them from the settings); nothing is called
    Step 2: ask() / aask() answer a question, within the deadline, from the cache when they can; stream() /
            astream() give the answer as it's written; stats() says what's in use
    """

    def __init__(self, *, retriever: KBRetriever, answerer: Answerer, store, model_name: str, kb_version: str,
                 cache: AnswerCache | None = None, memory: ConversationMemory | None = None,
                 condenser: Callable[[list[tuple[str, str]], str], str] | None = None,
                 question_timeout_seconds: float = QUESTION_TIMEOUT_SECONDS,
                 store_breaker: CircuitBreaker | None = None, model_breaker: CircuitBreaker | None = None,
                 prices_per_million: tuple[float, float] = (0.0, 0.0)):
        """
        Args:
            retriever, answerer: Advanced 06's and 07's, built
            store: the KBVectorStore the retriever searches (for stats())
            model_name: "<provider>/<model>" of the chat model: part of the cache's scope
            kb_version: a hash of the knowledge base's articles: part of the cache's scope
            cache, memory, condenser: the answer cache, the conversation memory, and what rewrites a follow-up
            question_timeout_seconds: the most one question may take
            store_breaker, model_breaker: guard retrieval (the store and the embedding model) and answering
            prices_per_million: the chat model's price in dollars per million input and output tokens
        """
        self.retriever = retriever
        self.answerer = answerer
        self.store = store
        self.model_name = model_name
        self.kb_version = kb_version
        self.cache = cache
        self.memory = memory
        self.condenser = condenser
        self.question_timeout_seconds = question_timeout_seconds
        self.store_breaker = store_breaker or CircuitBreaker("vector store")
        self.model_breaker = model_breaker or CircuitBreaker("chat model")
        self.prices_per_million = prices_per_million

    @property
    def scope(self) -> str:
        """What a cached answer depends on: the prompt, the model, the knowledge base and how it's searched."""
        retrieval = f"{self.retriever.mode}-{self.retriever.k}-{self.retriever.min_score}"
        return f"{self.answerer.prompt.version}|{self.model_name}|{self.kb_version}|{retrieval}"

    def ask(self, question: str, *, session: str | None = None) -> EngineAnswer:
        """The answer, within the deadline.

        Raises:
            DeadlineError: it took longer than question_timeout_seconds
            CircuitOpenError: the store or the model kept failing, so it wasn't even called
            EngineError (and the parts' own errors): it couldn't be answered
        """
        # The steps run in a thread of their own: past the deadline the caller stops waiting (a thread can't be
        # stopped, so it finishes on its own)
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(self._answer, question, session).result(timeout=self.question_timeout_seconds)
        except TimeoutError:
            raise DeadlineError(f"The question took longer than {self.question_timeout_seconds:g} s") from None
        finally:
            pool.shutdown(wait=False)

    async def aask(self, question: str, *, session: str | None = None) -> EngineAnswer:
        """ask(), for code that's already async. The steps run in a worker thread, so an event loop isn't blocked;
        past the deadline the caller gets a DeadlineError at once (the thread finishes on its own)."""
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._answer, question, session),
                                          self.question_timeout_seconds)
        except TimeoutError:
            raise DeadlineError(f"The question took longer than {self.question_timeout_seconds:g} s") from None

    def stream(self, question: str, *, session: str | None = None) -> Iterator[tuple[str, Any]]:
        """ask(), as the answer is written: ("delta", text) for each new piece of it, then ("answer", the
        EngineAnswer), whose text is the one to keep (the checks may have changed it). A cached answer comes in one
        piece. It has no deadline of its own: astream() has."""
        return self._steps(question, session, streaming=True)

    async def astream(self, question: str, *, session: str | None = None) -> AsyncIterator[tuple[str, Any]]:
        """stream(), for code that's already async: each piece is waited for in a worker thread, so an event loop
        isn't blocked, and all of them within the question's deadline (past it: a DeadlineError, at once)."""
        steps = self._steps(question, session, streaming=True)
        deadline = time.monotonic() + self.question_timeout_seconds
        while True:
            try:
                event = await asyncio.wait_for(asyncio.to_thread(next, steps, None), deadline - time.monotonic())
            except TimeoutError:
                raise DeadlineError(f"The question took longer than {self.question_timeout_seconds:g} s") from None
            if event is None:
                return
            yield event

    def _answer(self, question: str, session: str | None) -> EngineAnswer:
        return dict(self._steps(question, session, streaming=False))["answer"]

    def _steps(self, question: str, session: str | None, *, streaming: bool) -> Iterator[tuple[str, Any]]:
        """Every stage, in order: ("delta", text) while the answer is written (streaming only), then ("answer", the
        EngineAnswer)."""
        trace = Trace(question)
        history = self.memory.history(session) if self.memory and session else []

        # Step 2a: A follow-up becomes a complete question
        with trace.span("condense") as fields:
            asked = self.condenser(history, question) if history and self.condenser else question
            fields.update(history_turns=len(history), rewritten=asked != question, question=asked)

        # Step 2b: An answer already given, for the same prompt, model and knowledge base
        vector, found = None, None
        with trace.span("cache") as fields:
            if self.cache is not None:
                if self.retriever.mode != "sparse":
                    vector, _ = self.store_breaker.call(self.retriever.question_vector, asked)
                found = self.cache.get(asked, vector, scope=self.scope)
            fields["hit"] = found[1] if found else False

        if found:
            grounded = _restore(found[0], asked)
            cached = found[1]
            if streaming:
                yield "delta", grounded.answer
        else:
            cached = ""
            # Step 2c: Retrieve, then answer, each behind its breaker
            with trace.span("retrieve") as fields:
                result = self.store_breaker.call(self.retriever.search, asked)
                fields.update(candidates=result.candidates, no_match=result.no_match, filters=result.filters,
                              chunk_ids=[doc.metadata.get("chunk_id") for doc in result.docs])
            with trace.span("answer") as fields:
                if streaming:
                    with self.model_breaker.guard():
                        for kind, value in self.answerer.stream(asked, result.docs, no_match=result.no_match):
                            if kind == "delta":
                                yield kind, value
                            else:
                                grounded = value
                else:
                    grounded = self.model_breaker.call(self.answerer.answer, asked, result.docs,
                                                       no_match=result.no_match)
                fields.update(status=grounded.status, calls=grounded.calls, context_tokens=grounded.context_tokens,
                              **{f"usage_{name}": count for name, count in grounded.usage.items()})
            if self.cache is not None:
                self.cache.put(asked, vector, _saved(grounded), scope=self.scope)

        if self.memory is not None and session:
            self.memory.add(session, question, grounded.answer)
        cost = 0.0 if cached else sum(grounded.usage.get(name, 0) * price / 1_000_000 for name, price in
                                      zip(("input_tokens", "output_tokens"), self.prices_per_million, strict=True))
        yield "answer", EngineAnswer(question, asked, grounded, trace, cached, round(cost, 6))

    def stats(self) -> dict[str, Any]:
        """What the engine is running with, read from its parts, never from a default."""
        collection = self.store.current()
        return {
            "embedding_model": self.retriever.model_name, "chat_model": self.model_name,
            "collection": f"{self.store.alias} -> {collection}" if collection else "none yet",
            "points": self.store.client.count(collection, exact=True).count if collection else 0,
            "retrieval": f"{self.retriever.mode}, k = {self.retriever.k}, min_score = {self.retriever.min_score}",
            "prompt_version": self.answerer.prompt.version, "kb_version": self.kb_version,
            "cached_answers": self.cache.count() if self.cache is not None else "no cache",
            "breakers": f"vector store {self.store_breaker.state}, chat model {self.model_breaker.state}",
            "sessions": len(self.memory) if self.memory is not None else "no memory",
        }


def _saved(grounded: GroundedAnswer) -> dict:
    """A GroundedAnswer as JSON-ready data, its sources as text and metadata."""
    data = asdict(grounded)
    data["sources"] = [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in grounded.sources]
    return data


def _restore(data: dict, question: str) -> GroundedAnswer:
    """A cached answer, for the question as it was asked this time; served from the cache, it took no call."""
    sources = [Document(page_content=source["page_content"], metadata=source["metadata"])
               for source in data.pop("sources")]
    restored = GroundedAnswer(**data)
    restored.question, restored.sources, restored.calls = question, sources, 0
    return restored


def _cosine(first: list[float], second: list[float]) -> float:
    dot = sum(a * b for a, b in zip(first, second, strict=True))
    size = math.sqrt(sum(a * a for a in first)) * math.sqrt(sum(b * b for b in second))
    return dot / size if size else 0.0
