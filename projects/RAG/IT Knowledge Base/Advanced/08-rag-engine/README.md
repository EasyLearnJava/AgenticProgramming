# 08 · RAG Engine (Advanced)

Make the retriever and the answerer one dependable core, the one a service will call: every part passed in, every
setting in one place (and overridable from the environment), a deadline on every question, a circuit breaker in front
of the store and the model, repeated questions answered from a cache, every stage traced with its time, tokens and
cost, and follow-up questions understood. Advanced 07's pipeline comes first, unchanged; its questions are now asked
of the engine. Built with **LangChain**, **Qdrant**, **SQLite** (the answer cache) and the Python standard library.

> **Needs:** Python 3.11 or newer and a Gemini API key; or no key, with the stand-in models.
> **Production version of:** [Basic · 08 · RAG Engine](../../Basic/08-rag-engine/README.md),
> built on [Advanced · 07](../07-grounded-answer/README.md).

---

## 🎯 What This Project Does

- **One settings object**: `kb_settings.toml`, checked at start-up, and now any setting from the environment too:
  `KB__ENGINE__QUESTION_TIMEOUT_SECONDS=20` sets `[engine] question_timeout_seconds`; a bad value names the variable
- **Parts passed in**: `RAGEngine` gets the retriever, the answerer, the store, the cache, the memory and the
  condenser as objects (`wiring.make_engine()` builds them), so each can be swapped or replaced in a test
- **A deadline on every question**: past `question_timeout_seconds`, the caller gets a clear error at once
- **Circuit breakers**: after 3 failures in a row, calls to the store (or to the model) stop for 30 seconds and fail
  at once with why; then one call is let through to try again
- **An answer cache**: a repeated question, or one alike in meaning, is answered with no call, but only for the same
  prompt version, model, knowledge base and retrieval settings, and only for a day
- **A trace per question**: a span per stage (condense, cache, retrieve, answer) with its time, chunk IDs, tokens and
  cost
- **Follow-up questions**: each session's last 5 turns are kept, and "and on Mac?" is rewritten into a complete
  question (by Gemini with `prompts/condense-v1.txt`, or the stand-in's rule) before it's searched
- **Async callers too**: `aask()` runs the steps in a worker thread, so a server's event loop isn't blocked
- **Honest stats**: `stats()` reads the models, the collection behind the alias, its points, the prompt and the
  knowledge base's version from the parts in use, never from a default

**Try it:** `python pipeline.py --question "My VPN keeps timing out" --question "and on Mac?" --question "my vpn keeps
timing out"`: a question, a follow-up, and the first again, from the cache.

---

## 🏗️ Architecture

```text
question, session ──→ RAGEngine.ask()          within question_timeout_seconds, or DeadlineError
                            │
                            ├─ condense    the session's last turns + a follow-up → a complete question
                            ├─ cache       same prompt · model · knowledge base · retrieval?  exact, or alike in meaning
                            │                 └─ hit: the answer, no call ──────────────────────────────┐
                            ├─ retrieve    store breaker ──→ KBRetriever.search()        (Advanced 06)   │
                            ├─ answer      model breaker ──→ Answerer.answer()           (Advanced 07)   │
                            │                 └─ kept in the cache                                       │
                            └─ memory      the turn added to the session                                 │
                                                                                                         ↓
                                              EngineAnswer(answer, trace: a span per stage, cost) ←──────┘
```

---

## 📋 Prerequisites

- **Python 3.11 or newer**, and a Gemini API key, as in Advanced 04 (or the stand-ins)

---

## 🚀 Quick Start

Steps 1 to 4 are Advanced 04's: go to `projects/RAG/IT Knowledge Base/Advanced/08-rag-engine`, make and activate a
venv, `pip install -r requirements-dev.txt`, and copy `.env.example` to `.env` with your key in it.

### Step 5: Run It, With a Follow-up and a Repeat

```bash
python pipeline.py --question "My VPN keeps timing out when I work from home" --question "and on Mac?" \
                   --question "my vpn keeps timing out when I work from home"
```

The questions are asked in one session. With the stand-in models (the chat stand-in quotes the first chunk; the
condenser's rule joins a short follow-up to the question before it), the answers, then their traces, then the stats:

```text
Answers: by fake/gemini-3.5-flash-lite, with the prompt answer-v1; the context's budget 3,000 tokens
  Question: My VPN keeps timing out when I work from home
    Answer: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open.
    Sources: VPN Connection Timeout (resolution)
    1 call; context 142 tokens; checks: passed
  Question: My VPN keeps timing out when I work from home, and on Mac?
    Answer: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations
    Sources: VPN Connection Timeout (problem)
    1 call; context 140 tokens; checks: passed
  Question: my vpn keeps timing out when I work from home
    Answer: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open.
    Sources: VPN Connection Timeout (resolution)
    0 calls; context 142 tokens; checks: passed

Traces: a line per stage, with its time
  My VPN keeps timing out when I work from home: trace b6f8335b32ae436a, 23 ms
    condense     0.0 ms  history_turns 0, rewritten False
    cache        5.5 ms  hit False
    retrieve     8.0 ms  candidates 3, no_match False, filters {'system': 'VPN'}, chunk_ids 2
    answer       9.6 ms  status answered, calls 1, context_tokens 142, usage_input_tokens 0, usage_output_tokens 0
  and on Mac? (asked as: My VPN keeps timing out when I work from home, and on Mac?): trace 1dffc527cc05443a, 11 ms
    condense     0.0 ms  history_turns 1, rewritten True
    cache        6.7 ms  hit False
    retrieve     3.6 ms  candidates 3, no_match False, filters {'system': 'VPN'}, chunk_ids 2
    answer       0.5 ms  status answered, calls 1, context_tokens 140, usage_input_tokens 0, usage_output_tokens 0
  my vpn keeps timing out when I work from home: trace 30580ecc5eb34d56, 6 ms, from the cache (exact)
    condense     0.0 ms  history_turns 2, rewritten False
    cache        6.0 ms  hit exact

Engine: what it's running with
  embedding_model: fake/gemini-embedding-001
  chat_model: fake/gemini-3.5-flash-lite
  collection: it_kb -> it_kb_v1
  points: 39
  retrieval: hybrid, k = 5, min_score = -1.0
  prompt_version: answer-v1
  kb_version: 1041c66b6d4644e3
  cached_answers: 2
  breakers: vector store closed, chat model closed
  sessions: 1
```

The third question differs only in case, so it's answered from the cache, with no call. With Gemini, the traces add
the model's own token counts, and with `input_price_per_million` and `output_price_per_million` set, each answer's
cost. The cache lives in `data/answer_cache.sqlite3`, so a question answered in one run is answered from it in the
next, as long as the knowledge base hasn't changed.

---

## 📁 Project Structure

```text
08-rag-engine/
├── pipeline.py                   # Advanced/07's steps; the questions asked of the engine in one session
├── rag_engine.py                 # RAGEngine, CircuitBreaker, AnswerCache, ConversationMemory, Trace, condensers
├── prompts/condense-v1.txt       # rewrites a follow-up into a complete question
├── wiring.py                     # + make_engine()
├── settings.py                   # + EngineSettings, and settings from the environment (KB__...)
├── manifest.py                   # + version(): the knowledge base's version, for the cache's scope
├── answering.py, retriever.py, evaluation.py, vector_store.py, embedding.py, config.py, chunking.py,
│   knowledge_base_loader.py, article.py, sensitive_data.py, utils.py, prompts/answer-v1.txt
├── kb_settings.toml              # ..., [answer], and now [engine]
├── data/                         # Advanced/07's data files; answer_cache.sqlite3 written by each run (not in git)
└── tests/
    ├── test_rag_engine.py        # breakers, the trace, the cache, the memory, the condensers, the engine
    └── the tests of Advanced/07
```

---

## 🔧 Configuration

### `[engine]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `question_timeout_seconds` | 60 | the most one question may take |
| `breaker_failures` | 3 | failures in a row before calls to the store, or to the model, stop |
| `breaker_reset_seconds` | 30 | how long they stop |
| `cache` | `true` | answer a repeated question from the cache |
| `cache_path` | `"data/answer_cache.sqlite3"` | from the settings file's folder |
| `cache_ttl_seconds` | 86400 | an answer older than a day is asked again |
| `semantic_threshold` | 0.95 | a question this alike in meaning to a cached one gets its answer |
| `memory_turns` | 5 | turns of each conversation kept |
| `input_price_per_million`, `output_price_per_million` | 0 | the chat model's prices, for the cost in each trace |

`[answer]` adds `condense_prompt_file`. Every setting of every table can come from the environment:
`KB__<TABLE>__<SETTING>=<value>`, the value read as TOML (`20`, `true`, `"text"`) or else as text.

### The Engine's Constructor

```python
RAGEngine(*, retriever, answerer, store, model_name, kb_version, cache=None, memory=None, condenser=None,
          question_timeout_seconds=60.0, store_breaker=None, model_breaker=None, prices_per_million=(0.0, 0.0))
```

Two engines to compare, a baseline and a tuned one, are this class with two sets of parts.

---

## 🧪 Testing

```bash
python -m pytest        # 318 passed  (add -v for one line per test)
```

- **The circuit breaker**: opens after failures in a row and fails fast; after a while one call goes through and its
  result decides; a success resets the count
- **The trace, the cache, the memory**: a span's time, fields and error; the cache found exactly, by meaning, only in
  its scope and while fresh; a broken cache file; each session's last turns; the rule rewriting only a follow-up; a
  model condenser given the conversation
- **The engine**, with a keyword retriever and a scripted model: a question answered and each stage traced; a repeat
  from the cache with no call; one alike in meaning; a new knowledge base not served from the old cache; a follow-up
  rewritten with its session's history; a slow model stopped at the deadline, for sync and async callers; a failing
  store not called again for a while; the tokens priced; the stats read from the parts
- **The settings**: `[engine]`'s defaults; settings from the environment; a bad one named with its variable
- **The pipeline**: the answers, traces and stats; a follow-up and a repeat in one run

No key and no network.

---

## 🎓 Key Concepts Demonstrated

### 1. Bound Every Call

A question that hangs ties up a worker and a user. The deadline turns "forever" into a clear error; the model's and
the store's own timeouts and retries (Advanced 04 and 07) keep each call short.

### 2. Stop Calling What's Down

When the store is down, every question would wait for its timeout, and pile up. After a few failures in a row the
breaker opens: questions fail at once with why, and after a while one is let through to see if it's back.

### 3. Cache With the Right Key

An answer depends on the question, but also on the prompt, the model, the knowledge base and how it's searched. All
of them are in the cache's scope, so a new prompt or a changed article is never answered from an old answer; the
expiry catches anything else.

### 4. Trace Each Stage

When an answer is slow or wrong, the trace says which stage did it: the condensed question, the cache, the chunks
found, the model's tokens and the cost.

### 5. A Follow-up Is a Question About the Last One

"And on Mac?" finds nothing on its own. Rewritten with the conversation into a complete question, it finds the VPN
article.

### 6. Settings From the Environment

The same code runs on a laptop and on a server; only the environment differs. Every setting can be overridden there,
and is checked exactly as the file's are.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR The question took longer than 60 s`
**Fix**: The model or the store was slow. The trace of a run that worked shows each stage's time; raise
`question_timeout_seconds` only if the stages are slow for a reason.

**Issue**: `ERROR The vector store failed 3 times in a row: calls to it stopped for 30 s (...)`
**Fix**: The store (or the embedding model) kept failing; the error before this one says why. Fix that; the breaker
lets a call through after 30 s.

**Issue**: An answer seems stale
**Fix**: The cache answered it. A changed article changes the knowledge base's version, so the next answer is fresh;
otherwise delete `data/answer_cache.sqlite3` or set `cache = false`.

**Issue**: `ERROR Settings file has a bad setting (...; from the environment: KB__...)`
**Fix**: An environment variable set a bad value; the message names it.

---

## 📚 Next Steps

**[09 · API (Advanced)](../09-api/README.md)**: the engine behind an HTTP API: authentication, rate limits, request IDs,
readiness checks and streaming.

### Ideas to Try

- Run the same question twice in two runs: the second is answered from `data/answer_cache.sqlite3`.
- Set `KB__ENGINE__CACHE=false` in the environment and run again.
- With Gemini, ask a follow-up like "and if that doesn't work?" and read how the condenser rewrote it in the trace.
