# 04 · Embeddings (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 04 · Embeddings](../../Basic/04-embeddings/README.md)

The basic version sends all the chunks to Gemini in one call and gets back 768 numbers for each. This version treats
the embedding service as what it is in production: a remote API that has limits, fails now and then, costs money,
and must never receive data it shouldn't.

---

## 🎯 What This Project Will Do

- **Send chunks in batches** that respect the API's limits, with bounded parallel calls
- **Retry what can be retried**: rate limits and server errors, with backoff and jitter; fail clearly on the rest
- **Never embed the same text twice**: a cache from content hash to vector
- **Track cost and speed**: calls, tokens, time and failures per run
- **Stop sensitive data at the door**: the Advanced/01 redaction runs on every chunk before it's sent

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Batching** | Chunks grouped by count and by total tokens, under the API's per-request limits | Thousands of chunks don't fail as one oversized request |
| 2 | **Retries with backoff** | Exponential backoff with jitter for 429 and 5xx errors, a timeout on every call, and a clear error on anything else | A busy API slows the run down instead of breaking it |
| 3 | **Bounded concurrency** | Several batches at once, up to a set limit, with async calls | Faster runs without tripping the rate limit |
| 4 | **Embedding cache** | Content hash → vector, stored on disk, with the model name and dimensions in the key | Re-running ingestion costs nothing for unchanged chunks |
| 5 | **Model versioning** | The model name, dimensions and date stored with every vector; a mismatch stops the run | Vectors from two different models are never mixed in one index |
| 6 | **Cost and latency tracking** | Per-run totals of calls, tokens, time and errors, in the log and a summary line | A change that doubles the cost is noticed in the first run |
| 7 | **Sensitive-data gate** | The redaction from Advanced/01 applied to every chunk, with a count of what was removed | Nothing personal, financial or secret is sent to an outside service |
| 8 | **Provider abstraction** | The embedding model chosen by configuration behind one interface, with a stand-in for tests | Switching provider, or testing without a key, needs no code change |

---

## 🏗️ Planned Architecture

```text
chunks ──→ redact ──→ cache lookup ──┬──→ hit: reuse the vector
                                     └──→ miss ──→ batch ──→ embed (retry · backoff · timeout) ──→ store in cache
                                                                    │
                                                                    ↓
                                                    metrics: calls, tokens, time, errors ──→ log + summary
```

---

## ✅ Done When

- A fake embedding service that can be told to rate-limit, time out or fail, so every path is tested without a key
- Tests that a second run makes zero calls, that a 429 is retried and a 400 isn't, and that no redacted value is sent
- A summary line per run: chunks embedded, taken from the cache, retried and failed, with tokens and time

---

## 📚 Next Steps

**[05 · Vector Store (Advanced)](../05-vector-store/README.md)**: idempotent upserts, filters, and re-indexing
without downtime.
