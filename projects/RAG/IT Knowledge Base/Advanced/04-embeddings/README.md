# 04 · Embeddings (Advanced)

Turn the chunks into vectors with Gemini (`gemini-embedding-001`, 768 numbers each), treating the embedding service as
what it is in production: a remote API that has limits, fails now and then, costs money, and must never receive data
it shouldn't. Chunks go through a sensitive-data gate, then a cache, so an unchanged chunk is never embedded twice;
the rest go in batches, a few at once, each call timed out and retried as it should be; and every run reports its
calls, tokens and time. Advanced 03's loading and chunking come first, unchanged. Built with **LangChain**
(`langchain-google-genai`), **SQLite** (the cache) and the Python standard library (`asyncio`).

> **Needs:** Python 3.11 or newer and a Gemini API key; or no key at all, with the stand-in model (below).
> **Production version of:** [Basic · 04 · Embeddings](../../Basic/04-embeddings/README.md),
> built on [Advanced · 03](../03-chunking/README.md).

---

## 🎯 What This Project Does

- **Sends nothing sensitive**: Advanced 01's redaction runs on every chunk before it's sent, and the report counts
  what it caught
- **Never embeds the same text twice**: a cache on disk (`data/embedding_cache.sqlite3`) keeps each vector under the
  hash of its text, the model and the size; a second run makes no call
- **Never mixes two models' vectors**: each vector is kept under `<provider>/<model>` and its size, and each chunk's
  metadata records the model, the size and when its vector was made
- **Sends batches under the API's limits**: at most 100 texts and about 20,000 tokens a call, two calls at a time
- **Retries what can be retried**: a rate limit (429), a server error (5xx) or a timeout is tried again after a wait
  that doubles each time, with jitter, up to 4 tries; anything else, a bad key say, or a quota used up for the
  day, stops the run at once with why
- **Checks what comes back**: one vector per text, 768 numbers each, all real numbers, or the run stops
- **Tracks cost and speed**: calls, retries, tokens sent and time, in the output and the log
- **Lets you choose the model in a settings file**: Gemini, or a stand-in that needs no key and makes no call
- **Saves the manifest only after the vectors are made**: a failed run is run again in full, and the vectors made
  before the failure are already cached, so it costs little

**Try it:** run `python pipeline.py` twice with `--full`: the second run takes all 39 vectors from the cache and makes
no call.

---

## 🏗️ Architecture

```text
pipeline.py
   ├─ load_settings(), then make_embedder()   kb_settings.toml's [embeddings]; the key read first (Gemini only)
   ├─ KBLoader → Manifest.compare → KBTextSplitter       Advanced 03: the chunks of the articles passed on
   │
   ├─ ChunkEmbedder.embed(chunks)
   │     1. the gate         redact() on every chunk's text                  → report.redacted
   │     2. the cache        hash of the text + "<provider>/<model>" + size  → hits reused, never sent
   │     3. batches          ≤ 100 texts, ≤ 20,000 tokens each
   │     4. send             ≤ 2 calls waiting at once (asyncio)
   │          each try: cut off after 30 s
   │          429 / 5xx / timeout → wait (1 s, 2 s, 4 s ... ≤ 30 s, with jitter) and try again, ≤ 4 tries
   │          the day's quota, 400, 403 ... → EmbeddingError: the run stops, with why
   │     5. check            one vector per text, 768 real numbers each
   │     6. cache            each batch's vectors kept as soon as they come
   │     7. label            embedding_model, embedding_dimensions, embedded_at on each chunk
   │
   └─ Manifest.write()      only now, once every step has succeeded
```

### The Pipeline in This Project

1. **Settings and key** → `kb_settings.toml`; with Gemini, `GOOGLE_API_KEY` is read first, so a missing key stops the
   run before anything is read
2. **Load, compare, chunk** → Advanced 03, unchanged
3. **Gate** → each chunk's text redacted again before it leaves the machine
4. **Cache** → each text already embedded, by this model at this size, is taken from the cache
5. **Embed** → the rest in batches, with timeouts, retries and backoff, a few at once
6. **Check, cache, label** → every vector checked, kept, and its chunk labelled with the model
7. **Save the manifest and print** → the chunks, the vectors and where they came from, then the checks

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key** (free tier works): make one in the Google Cloud console under APIs & Services > Credentials.
  The free tier allows 100 embedded texts a minute and 1,000 a day; each chunk counts once, and a cached one not at all
- **Or no key**: set `provider = "fake"` in `kb_settings.toml`'s `[embeddings]` to run every step with a stand-in
  model whose vectors mean nothing

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Advanced/04-embeddings"   # from the repo root; quotes for the spaces
```

### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: LangChain, Gemini's client, pydantic, python-dotenv, pytest
```

### Step 4: Give It Your Key

```bash
cp .env.example .env                 # Windows: copy .env.example .env
```

Open `.env` and put your key after `GOOGLE_API_KEY=`. `.env` is in `.gitignore`: it never goes into git. (Or set
`GOOGLE_API_KEY` in the environment; or skip this step and use the stand-in model.)

### Step 5: Run It

```bash
python pipeline.py
```

After the chunks (as in Advanced 03), the output says how the vectors were made. This is a run with the stand-in model
(`provider = "fake"`); with Gemini, the model's name is `google/gemini-embedding-001`, the numbers in the vectors
differ, and the log's time is longer:

```text
Vectors: 39, each 768 numbers, by fake/gemini-embedding-001
  0 from the cache, 39 made by the model in 1 call (0 retries, 0 failed), about 2,271 tokens sent
  the first vector begins [-1.1828, 1.094, 0.0665, -0.441]
Sensitive-data gate: nothing to redact before sending
```

The log (stderr) has the time:

```text
INFO Cut 10 articles into 39 chunks
INFO Embedded 39 chunks: 0 from the cache, 39 by the model in 1 call (0 retries), about 2271 tokens, 1.1 s
INFO Manifest saved: manifest.json (10 articles)
```

Run it again with `--full`, which passes on every article: every vector comes from the cache.

```text
Vectors: 39, each 768 numbers, by fake/gemini-embedding-001
  39 from the cache, 0 made by the model in 0 calls (0 retries, 0 failed), about 0 tokens sent
```

Read the next export, `data/sample_it_kb_next.csv`: 10 chunks are passed on, but only 4 are sent (VPN's edited fix
and the new article's 3 chunks); the laptop article's priority changed, not its text, so its 4 chunks are cached.

```text
Vectors: 10, each 768 numbers, by fake/gemini-embedding-001
  6 from the cache, 4 made by the model in 1 call (0 retries, 0 failed), about 222 tokens sent
```

When a call is rate limited, the log shows each retry:

```text
WARNING Embedding call failed (ClientError: 429 RESOURCE_EXHAUSTED. {...}), try 1 of 4: trying again in 0.7 s
```

---

## 📁 Project Structure

```text
04-embeddings/
├── pipeline.py                   # main(): settings and key, load, compare, chunk, embed, save the manifest, print
├── embedding.py                  # ChunkEmbedder, EmbeddingCache, make_embedding_model(), is_retryable(); defaults
├── config.py                     # load_api_key(): GOOGLE_API_KEY from the environment or .env, as a SecretStr
├── chunking.py                   # KBTextSplitter: Advanced/03's
├── knowledge_base_loader.py      # KBLoader: Advanced/02's
├── article.py, settings.py, manifest.py   # the schema; the settings (now with [embeddings]); what changed
├── sensitive_data.py             # redact(): Advanced/01's, which now leaves a [REDACTED:...] placeholder alone
├── utils.py                      # helpers: hashes, simplify(), count_tokens(), the print_* functions
├── kb_settings.toml              # the export's columns, spellings, [chunking], and [embeddings]
├── .env.example                  # copy to .env and put your key in it; .env never goes into git
├── data/
│   ├── sample_it_kb.csv and the other data files of Advanced/03
│   ├── manifest.json             # written by each run (not in git)
│   └── embedding_cache.sqlite3   # the vectors already made (not in git): delete it to embed every chunk again
├── tests/
│   ├── fakes.py                  # ScriptedEmbeddings: a stand-in service told to rate-limit, fail or be slow
│   ├── conftest.py               # no test can reach the network
│   ├── test_embedding.py         # the cache, batches, concurrency, retries, the gate, the checks, the model
│   ├── test_config.py            # the key
│   ├── test_pipeline.py          # the steps run as the script runs them, with the stand-in model
│   └── test_chunking.py, test_knowledge_base_loader.py, test_article.py, test_settings.py, test_manifest.py,
│       test_sensitive_data.py, test_utils.py
├── requirements.txt              # langchain-core, langchain-text-splitters, langchain-google-genai, google-genai,
│                                 #   pydantic, python-dotenv
├── requirements-dev.txt          # + pytest
├── pytest.ini
└── .gitignore                    # .env, data/manifest.json, data/embedding_cache.sqlite3
```

---

## 🔧 Configuration

### `[embeddings]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `provider` | `"google"` | `"google"` (Gemini, needs the key) or `"fake"` (a stand-in: no key, no call) |
| `model` | `"gemini-embedding-001"` | the model's name |
| `dimensions` | 768 | the size of every vector; a vector of another size stops the run |
| `batch_size` | 100 | the most texts in one call (Gemini takes up to 100) |
| `batch_tokens` | 20000 | the most estimated tokens in one call |
| `max_concurrency` | 2 | how many calls may be waiting at once |
| `max_attempts` | 4 | tries per call, the first included |
| `timeout_seconds` | 30 | each try is cut off after this long |
| `backoff_seconds` | 1 | the first wait before trying again; it doubles each time |
| `backoff_max_seconds` | 30 | the longest wait |
| `cache_path` | `"data/embedding_cache.sqlite3"` | from the settings file's folder |

A setting left out keeps its default from `embedding.py`. Command-line options are Advanced 03's.

### The Embedder's Constructor

```python
ChunkEmbedder(model, *, model_name, dimensions, cache=None, batch_size=100, batch_tokens=20_000, max_concurrency=2,
              max_attempts=4, timeout_seconds=30.0, backoff_seconds=1.0, backoff_max_seconds=30.0,
              length_function=count_tokens, sleep=asyncio.sleep, rng=None, clock=utc_now)
```

`model` is any LangChain `Embeddings`, passed in as an object; the key is never a parameter. Tests pass the stand-in
service, and a `sleep` that only records how long it would have waited.

---

## 🧪 Testing

```bash
python -m pytest        # 198 passed  (add -v for one line per test)
```

- **Vectors**: every chunk gets its vector in order, plain floats; each chunk records the model, size and date; the
  report counts chunks, calls and tokens
- **The cache**: a second run makes no call; only a changed chunk is sent again; two models never share a vector; a
  text twice is sent once; a broken cache file says to delete it
- **Batches and concurrency**: under the count and the tokens; never more calls waiting than the limit
- **Retries**: a rate limit, a server error and a timeout each retried after a wait; the wait doubles up to its
  longest, with jitter; a bad request fails at once; the day's quota isn't retried; retries end after the last try;
  vectors made before a failure are cached; which errors are worth another try, Google's inside LangChain's too
- **The gate and the checks**: nothing sensitive is sent and each value is counted; a wrong size, a wrong count or a
  value that isn't a number stops the run
- **The model and the key**: the stand-in needs no key; Gemini is built with a timeout and no retries of its own; the
  key is a secret that never prints, and a missing one says how to set it
- **The pipeline**, as its own process with the stand-in: run twice, `--full` from the cache, the next export, a
  missing key stopping the run before anything is read, bad files, a broken manifest
- **Advanced 03's tests**, and `redact()` finding nothing new in text it redacted already

No key and no network: `tests/conftest.py` makes any request a test tries to send fail at once.

---

## 📊 Understanding the Output

| A chunk's new metadata | What it is |
|---|---|
| `embedding_model` | `<provider>/<model>`: `google/gemini-embedding-001`, or `fake/...` for the stand-in |
| `embedding_dimensions` | the vector's size: 768 |
| `embedded_at` | when its vector was made (UTC): an earlier run's date for a cached one |

| The vectors' line | What it counts |
|---|---|
| from the cache | chunks whose text was embedded before, by this model at this size |
| made by the model | chunks whose vector was made this run (a text twice counts twice, but is sent once) |
| calls | tries, retries included; each one counts against the API's limits |
| tokens sent | estimated, retries included: what the run cost |

---

## 🎓 Key Concepts Demonstrated

### 1. The Cheapest Call Is the One You Don't Make

```python
known = self.cache.get(list(dict.fromkeys(hashes)))      # embedding.py, aembed()
```

A vector depends only on the text, the model and the size, so it's kept under those. Re-running the pipeline, or
re-cutting an article whose chunks didn't change, costs nothing. Changing the model can't reuse an old vector by
mistake: the model is part of the key.

### 2. Retry Only What Another Try Can Fix

A 429 or a 503 means "not now"; a 400 or a bad key means "not ever"; a quota used up for the day means "not today".
Only the first is retried, after a wait that doubles each time (exponential backoff) and is partly random (jitter), so
many clients that failed together don't all try again in the same instant. Gemini's own client is set to one try, so
these retries are the only ones, and each one is counted.

### 3. Bounded Concurrency

`asyncio.Semaphore(max_concurrency)` lets a few calls wait at once: faster than one by one, without the burst that a
rate limit punishes.

### 4. A Gate at the Edge of the Machine

The loader redacted sensitive data already, but chunks may come from elsewhere later. Checking again where data
leaves the machine is cheap insurance; `redact()` now leaves its own `[REDACTED:...]` placeholders alone, so a second
check finds nothing that was already handled.

### 5. Check What Comes Back

A vector of the wrong size, or a missing one, would be stored and searched without complaint and give wrong answers
for ever. One check per call stops the run instead.

### 6. Secrets Are Values, Not Parameters

`load_api_key()` returns a `SecretStr`: printed or logged, it shows `**********`. The key goes straight into the
model's client; no class stores it, so it can't leak through a printed object or a traceback.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR GOOGLE_API_KEY is not set. Copy .env.example to .env ...`
**Fix**: Put your key in `.env` (Step 4), or set `provider = "fake"` to run without one.

**Issue**: `ERROR Embedding failed after 1 try (ClientError: 400 INVALID_ARGUMENT. ... API key not valid ...)`
**Fix**: Gemini didn't accept the key. Copy it again from the Google Cloud console, with nothing before or after it.

**Issue**: `ERROR The embedding model's quota for today is used up (...). It comes back at midnight Pacific time`
**Fix**: The free tier's 1,000 embedded texts a day are spent. Wait for midnight Pacific time; the vectors made so far
are cached, so the next run sends only the rest.

**Issue**: `WARNING Embedding call failed (ClientError: 429 RESOURCE_EXHAUSTED ...), try 1 of 4: trying again in ...`
**Fix**: Nothing: the free tier allows 100 texts a minute, and the run waits and tries again. If it happens on every
run, lower `batch_size` or `max_concurrency`.

**Issue**: `ERROR The model gave back a vector of 3072 numbers, not 768`
**Fix**: The model's size and `dimensions` in `kb_settings.toml` disagree: set them to match.

**Issue**: `ERROR The embedding cache can't be used (...). Delete it, and the next run embeds every chunk again.`
**Fix**: `data/embedding_cache.sqlite3` is damaged: delete it.

---

## 📚 Next Steps

**[05 · Vector Store (Advanced)](../05-vector-store/README.md)**: idempotent upserts and deletes, filters, and
re-indexing without downtime.

### Ideas to Try

- Set `batch_size = 10` and run with `--full` after deleting the cache: 4 calls instead of 1.
- Set `max_attempts = 1` and see a rate limit stop the run instead of waiting.
- Look inside the cache: `sqlite3 data/embedding_cache.sqlite3 "SELECT model, dimensions, COUNT(*) FROM vectors GROUP BY 1, 2"`.
- Switch between `provider = "fake"` and `"google"`: each keeps its own vectors in the cache.
