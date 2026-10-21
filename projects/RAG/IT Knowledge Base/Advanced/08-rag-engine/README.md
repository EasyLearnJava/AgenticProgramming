# 08 · RAG Engine (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 08 · RAG Engine](../../Basic/08-rag-engine/README.md)

The basic version puts every step in one class: build once, then answer each question with its sources. This
version makes that class the dependable core of a service: every setting in one place, every outside call bounded
by a timeout, repeated questions answered from a cache, every stage traced, and follow-up questions understood.

---

## 🎯 What This Project Will Do

- **Take one settings object**: models, collection, chunk sizes, `k`, timeouts and paths, read from the environment
  and checked at start-up
- **Bound every outside call**: timeouts, retries and a circuit breaker for the model and the vector store
- **Answer repeated questions from a cache**, exact and by meaning
- **Trace every stage**: how long retrieval, the prompt and the model took, with tokens and cost
- **Follow a conversation**: a follow-up like "and on Mac?" is understood using the previous turns

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **One settings object** | A Pydantic settings class: every value with a default, read from the environment, validated at start-up | Configuration changes need no code change, and a bad value fails at start-up, not mid-request |
| 2 | **Dependency injection** | The models, store and settings passed in to the constructor, with stand-ins for tests | Each part can be tested and swapped on its own |
| 3 | **Timeouts and retries** | A timeout on every model and store call, retries with backoff where safe | One slow call can't hang a request forever |
| 4 | **Circuit breaker** | After repeated failures, calls stop for a while and a clear error is returned at once | A down service doesn't pile up waiting requests |
| 5 | **Answer cache** | Exact-match and semantic caches, keyed with the prompt and model versions, with an expiry time | Popular questions are answered fast and at no cost; a model change doesn't serve stale answers |
| 6 | **Tracing** | A trace per question with a span per stage (OpenTelemetry or LangSmith): timings, token counts, chunk IDs | When an answer is slow or wrong, the trace shows which stage did it |
| 7 | **Conversation memory** | Recent turns kept per session; a follow-up is rewritten into a complete question before retrieval | Follow-up questions find the right articles |
| 8 | **Async all the way** | Async calls through the whole chain | One server handles many questions at once |
| 9 | **Honest stats** | `stats()` reports the models and collection actually in use, not the defaults | The status shown is the status the engine is really running with |

---

## 🏗️ Planned Architecture

```text
Settings (env) ──→ RAGEngine(settings, models, store)
                         │
question + session ──→ cache? ──hit──→ answer
                         │ miss
                         ↓
               condense with history ──→ retrieve (timeout, breaker) ──→ answer (timeout, retries) ──→ cache
                         │                          │                              │
                         └──────────────── trace: spans, timings, tokens, cost ────┘
```

---

## ✅ Done When

- Tests with stand-ins for a slow model, a failing store, a cache hit and a follow-up question
- A trace for one question showing every stage with its time and tokens
- Start-up fails with a clear message for each invalid setting

---

## 📚 Next Steps

**[09 · API (Advanced)](../09-api/README.md)**: authentication, rate limits, request IDs, readiness checks and
streaming.
