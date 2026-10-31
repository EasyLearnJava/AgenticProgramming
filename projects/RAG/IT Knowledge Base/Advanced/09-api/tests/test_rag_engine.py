"""
Tests for rag_engine.py, with stand-ins: the circuit breaker opens after failures in a row, fails fast, and lets one
call through after a while; the answer cache finds a question exactly and by meaning, only in its scope and while
it's fresh; the memory keeps each session's last turns and a follow-up is rewritten; the engine answers, traces each
stage, serves a repeat from the cache with no call, stops a slow model at the deadline, stops calling a failing
store, prices the tokens, and reports what it really runs with; and the answer streams in pieces, a cached one in
one piece, a stream that breaks off counts against the model's breaker, and astream() keeps the deadline.
"""
import time

import pytest
from fakes import KeywordEmbeddings
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.runnables import RunnableGenerator, RunnableLambda
from support import keyword_retriever, keyword_store

from answering import PROMPT_FILE, Answer, Answerer, extractive_stand_in, load_prompt, streaming_stand_in
from rag_engine import (
    AnswerCache,
    CircuitBreaker,
    CircuitOpenError,
    ConversationMemory,
    DeadlineError,
    EngineError,
    RAGEngine,
    Trace,
    condense_by_rule,
    condense_with,
)

PROMPT = load_prompt(PROMPT_FILE)


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def citing_first(delay: float = 0.0):
    """A stand-in model that cites the first chunk it's given, after `delay` seconds, and counts its calls."""
    calls = []

    def reply(messages):
        calls.append(messages)
        time.sleep(delay)
        chunk_id = str(messages[-1].content).split('<chunk id="', 1)[1].split('"', 1)[0]
        parsed = Answer(answer="Open UDP ports 500 and 4500.", cited_chunk_ids=[chunk_id], enough_context=True)
        usage = {"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050}
        return {"raw": AIMessage(content="{}", usage_metadata=usage), "parsed": parsed, "parsing_error": None}

    return RunnableLambda(reply), calls


def engine(tmp_path, *, delay: float = 0.0, kb_version: str = "v1", **options) -> tuple[RAGEngine, list]:
    model, calls = citing_first(delay)
    options.setdefault("cache", AnswerCache(tmp_path / "answers.sqlite3", clock=Clock()))
    options.setdefault("memory", ConversationMemory())
    made = RAGEngine(retriever=keyword_retriever(), answerer=Answerer(model, prompt=PROMPT), store=keyword_store(),
                     model_name="fake/scripted", kb_version=kb_version, condenser=condense_by_rule, **options)
    return made, calls


# -------------------------------------------------
# The Circuit Breaker
# -------------------------------------------------

def failing():
    raise ConnectionError("the store is down")


def test_the_breaker_opens_after_failures_in_a_row_and_then_fails_fast():
    clock = Clock()
    breaker = CircuitBreaker("vector store", failures=3, reset_seconds=30, clock=clock)
    for _ in range(3):
        with pytest.raises(ConnectionError):
            breaker.call(failing)
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError, match=r"The vector store failed 3 times in a row: .*30 s \(30 s left\)"):
        breaker.call(lambda: "never called")


def test_after_a_while_one_call_goes_through_and_its_result_decides():
    clock = Clock()
    breaker = CircuitBreaker("chat model", failures=1, reset_seconds=30, clock=clock)
    with pytest.raises(ConnectionError):
        breaker.call(failing)
    clock.now += 31
    with pytest.raises(ConnectionError):
        breaker.call(failing)                                       # half-open, and it failed: open again
    assert breaker.state == "open"
    clock.now += 31
    assert breaker.call(lambda: "fine") == "fine" and breaker.state == "closed"


def test_a_success_resets_the_count():
    breaker = CircuitBreaker("store", failures=2)
    with pytest.raises(ConnectionError):
        breaker.call(failing)
    breaker.call(lambda: None)
    with pytest.raises(ConnectionError):
        breaker.call(failing)
    assert breaker.state == "closed"


# -------------------------------------------------
# The Trace, the Cache and the Memory
# -------------------------------------------------

def test_a_span_records_its_time_its_fields_and_an_error():
    trace = Trace("vpn?")
    with trace.span("retrieve") as fields:
        fields["candidates"] = 3
    with pytest.raises(ValueError), trace.span("answer"):
        raise ValueError("bad")
    assert [(span.name, span.fields) for span in trace.spans] == [("retrieve", {"candidates": 3}),
                                                                  ("answer", {"error": "ValueError: bad"})]
    assert trace.seconds >= 0 and len(trace.trace_id) == 16


def test_the_cache_finds_a_question_exactly_or_by_meaning_in_its_scope_while_fresh(tmp_path):
    clock = Clock()
    cache = AnswerCache(tmp_path / "answers.sqlite3", ttl_seconds=60, threshold=0.95, clock=clock)
    cache.put("My VPN keeps timing out", [1.0, 0.0], {"answer": "Open the ports."}, scope="v1")
    assert cache.get("my  vpn keeps timing out", None, scope="v1") == ({"answer": "Open the ports."}, "exact")
    assert cache.get("VPN drops all the time", [0.99, 0.05], scope="v1") == ({"answer": "Open the ports."}, "meaning")
    assert cache.get("VPN drops all the time", [0.5, 0.5], scope="v1") is None           # not alike enough
    assert cache.get("My VPN keeps timing out", None, scope="v2") is None                # another scope
    clock.now += 61
    assert cache.get("My VPN keeps timing out", None, scope="v1") is None                # too old
    assert cache.count() == 1


def test_a_broken_cache_file_says_to_delete_it(tmp_path):
    path = tmp_path / "answers.sqlite3"
    path.write_text("not a database", encoding="utf-8")
    for use in (lambda cache: cache.get("q", None, scope="s"), lambda cache: cache.count()):
        with pytest.raises(EngineError, match="The answer cache can't be used .*Delete it"):
            use(AnswerCache(path))


def test_the_memory_keeps_each_sessions_last_turns():
    memory = ConversationMemory(turns=2)
    for number in range(3):
        memory.add("a", f"q{number}", f"a{number}")
    memory.add("b", "q", "a")
    assert (memory.history("a"), memory.history("b"), memory.history("c"), len(memory)) == (
        [("q1", "a1"), ("q2", "a2")], [("q", "a")], [], 2)


@pytest.mark.parametrize("history, question, asked", [
    ([("My VPN keeps timing out?", "...")], "and on Mac?", "My VPN keeps timing out, and on Mac?"),
    ([("My VPN keeps timing out", "...")], "what about Teams audio", "My VPN keeps timing out, what about Teams audio"),
    ([("My VPN keeps timing out", "...")], "How do I reset my Active Directory password?",
     "How do I reset my Active Directory password?"),
    ([], "and on Mac?", "and on Mac?"),
], ids=["follow-up", "what about", "a complete question", "no history"])
def test_the_rule_rewrites_only_a_follow_up(history, question, asked):
    assert condense_by_rule(history, question) == asked


def test_a_model_condenser_gets_the_conversation_and_gives_back_a_question():
    seen = []
    chat = RunnableLambda(lambda messages: seen.append(messages) or AIMessage(content=" How do I fix VPN timeouts on a "
                                                                                      "Mac? "))
    condense = condense_with(chat, "Rewrite the follow-up.")
    assert condense([("VPN times out", "Open the ports.")], "and on Mac?") == "How do I fix VPN timeouts on a Mac?"
    assert "Q: VPN times out\nA: Open the ports.\n\nFollow-up: and on Mac?" in seen[0][-1].content


# -------------------------------------------------
# The Engine
# -------------------------------------------------

def test_a_question_is_answered_and_each_stage_traced(tmp_path):
    made, calls = engine(tmp_path)
    asked = made.ask("My VPN keeps timing out")
    assert (asked.answer.status, asked.cached, len(calls)) == ("answered", "", 1)
    assert [span.name for span in asked.trace.spans] == ["condense", "cache", "retrieve", "answer"]
    retrieve = asked.trace.spans[2].fields
    assert retrieve["filters"] == {"system": "VPN"} and len(retrieve["chunk_ids"]) == 2


def test_a_repeated_question_comes_from_the_cache_with_no_call(tmp_path):
    made, calls = engine(tmp_path)
    made.ask("My VPN keeps timing out")
    again = made.ask("my vpn  keeps timing out")
    assert (again.cached, again.answer.calls, len(calls), again.cost_usd) == ("exact", 0, 1, 0.0)
    assert [span.name for span in again.trace.spans] == ["condense", "cache"]
    assert again.answer.question == "my vpn  keeps timing out" and again.answer.sources


def test_a_question_alike_in_meaning_comes_from_the_cache(tmp_path):
    made, calls = engine(tmp_path)
    made.ask("VPN timeout")
    alike = made.ask("timeout of the VPN")                  # the same keywords: the same vector to the stand-in
    assert (alike.cached, len(calls)) == ("meaning", 1)


def test_a_new_knowledge_base_isnt_answered_from_the_old_cache(tmp_path):
    cache = AnswerCache(tmp_path / "answers.sqlite3", clock=Clock())
    first, calls = engine(tmp_path, cache=cache, kb_version="v1")
    first.ask("My VPN keeps timing out")
    second, calls = engine(tmp_path, cache=cache, kb_version="v2")
    assert second.ask("My VPN keeps timing out").cached == "" and len(calls) == 1


def test_a_follow_up_is_rewritten_with_the_sessions_history(tmp_path):
    made, _ = engine(tmp_path)
    made.ask("My VPN keeps timing out", session="s1")
    follow_up = made.ask("and on Mac?", session="s1")
    alone = made.ask("and on Mac?", session="s2")
    assert follow_up.asked == "My VPN keeps timing out, and on Mac?" and follow_up.trace.spans[0].fields["rewritten"]
    assert alone.asked == "and on Mac?"


def test_a_slow_model_is_stopped_at_the_deadline(tmp_path):
    made, _ = engine(tmp_path, delay=1.0, question_timeout_seconds=0.2, cache=None)
    started = time.perf_counter()
    with pytest.raises(DeadlineError, match="longer than 0.2 s"):
        made.ask("My VPN keeps timing out")
    assert time.perf_counter() - started < 0.9                # the caller didn't wait for the model


def test_async_code_gets_the_same_deadline(tmp_path):
    import asyncio
    made, _ = engine(tmp_path, delay=1.0, question_timeout_seconds=0.2, cache=None)

    async def ask_and_time():
        started = time.perf_counter()
        with pytest.raises(DeadlineError):
            await made.aask("My VPN keeps timing out")
        return time.perf_counter() - started

    assert asyncio.run(ask_and_time()) < 0.9


def test_a_store_that_keeps_failing_isnt_called_again_for_a_while(tmp_path):
    made, _ = engine(tmp_path, cache=None, store_breaker=CircuitBreaker("vector store", failures=2,
                                                                       reset_seconds=60))
    made.retriever = keyword_retriever(embeddings=BrokenEmbeddings())
    for _ in range(2):
        with pytest.raises(ConnectionError):
            made.ask("My VPN keeps timing out")
    with pytest.raises(CircuitOpenError, match="The vector store failed 2 times in a row"):
        made.ask("My VPN keeps timing out")
    assert made.stats()["breakers"] == "vector store open, chat model closed"


class BrokenEmbeddings(KeywordEmbeddings):
    def embed_query(self, text):
        raise ConnectionError("the embedding service is down")


def test_the_tokens_are_priced(tmp_path):
    made, _ = engine(tmp_path, prices_per_million=(0.10, 0.40))
    assert made.ask("My VPN keeps timing out").cost_usd == pytest.approx(1000 * 0.10 / 1e6 + 50 * 0.40 / 1e6)


def test_the_stats_say_what_it_really_runs_with(tmp_path):
    made, _ = engine(tmp_path)
    made.ask("My VPN keeps timing out", session="s1")
    stats = made.stats()
    assert (stats["embedding_model"], stats["chat_model"], stats["collection"], stats["points"]) == (
        "fake/keywords", "fake/scripted", "it_kb -> it_kb_v1", 39)
    assert (stats["prompt_version"], stats["kb_version"], stats["cached_answers"], stats["sessions"]) == (
        "answer-v1", "v1", 1, 1)
    assert stats["retrieval"] == "hybrid, k = 5, min_score = -1.0"


# -------------------------------------------------
# Streaming
# -------------------------------------------------

def streaming_engine(tmp_path, *, streamer=None, **options) -> RAGEngine:
    """An engine whose answerer is the extractive stand-in, streamed a word at a time (or by `streamer`)."""
    answerer = Answerer(RunnableLambda(extractive_stand_in), prompt=PROMPT,
                        streamer=streamer or RunnableGenerator(streaming_stand_in))
    options.setdefault("cache", AnswerCache(tmp_path / "answers.sqlite3", clock=Clock()))
    return RAGEngine(retriever=keyword_retriever(), answerer=answerer, store=keyword_store(),
                     model_name="fake/stand-in", kb_version="v1", condenser=condense_by_rule, **options)


def test_the_answer_streams_in_pieces_then_the_engine_answer(tmp_path):
    events = list(streaming_engine(tmp_path).stream("My VPN keeps timing out"))
    deltas = [value for kind, value in events if kind == "delta"]
    kind, answered = events[-1]
    assert kind == "answer" and len(deltas) > 2 and "".join(deltas) == answered.answer.answer
    assert [span.name for span in answered.trace.spans] == ["condense", "cache", "retrieve", "answer"]


def test_a_cached_answer_streams_in_one_piece(tmp_path):
    made = streaming_engine(tmp_path)
    first = list(made.stream("My VPN keeps timing out"))
    again = list(made.stream("My VPN keeps timing out"))
    assert [kind for kind, _ in again] == ["delta", "answer"] and again[-1][1].cached == "exact"
    assert again[0][1] == first[-1][1].answer.answer


def test_a_stream_that_breaks_off_counts_against_the_models_breaker(tmp_path):
    def breaks_off(inputs):
        for _ in inputs:
            yield AIMessageChunk(content='{"answer": "Open')
            raise ConnectionError("the model went away")
    made = streaming_engine(tmp_path, streamer=RunnableGenerator(breaks_off),
                            model_breaker=CircuitBreaker("chat model", failures=1))
    with pytest.raises(ConnectionError):
        list(made.stream("My VPN keeps timing out"))
    with pytest.raises(CircuitOpenError):
        list(made.stream("My VPN keeps timing out"))


def test_astream_stops_a_slow_stream_at_the_deadline(tmp_path):
    import asyncio

    def slow(inputs):
        for _ in inputs:
            time.sleep(1.0)
            yield AIMessageChunk(content="{}")
    made = streaming_engine(tmp_path, streamer=RunnableGenerator(slow), question_timeout_seconds=0.2, cache=None)

    async def read_all() -> float:
        started = time.perf_counter()
        with pytest.raises(DeadlineError, match="longer than 0.2 s"):
            async for _ in made.astream("My VPN keeps timing out"):
                pass
        return time.perf_counter() - started

    assert asyncio.run(read_all()) < 0.9


def test_an_open_breaker_says_when_it_lets_a_call_through():
    clock = Clock()
    breaker = CircuitBreaker("vector store", failures=1, reset_seconds=30, clock=clock)
    with pytest.raises(ConnectionError):
        breaker.call(failing)
    clock.now += 10
    with pytest.raises(CircuitOpenError) as raised:
        breaker.call(lambda: None)
    assert raised.value.retry_after == pytest.approx(20)
