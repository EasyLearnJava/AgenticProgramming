# Advanced · Roadmap

The same 12 projects as `Basic/`, done again production grade. Each Basic project shows how a step of a RAG app works
when everything goes right; its Advanced version handles what goes wrong in real use, and proves it with tests and a
report: bad data, sensitive data, failing services, slow or costly calls, wrong answers, attacks, and the day-to-day
running of the app.

> **Status:** 01 to 07 are built. 08 to 12 are planned: each folder holds a README with its plan, and no code yet.

---

## 🗺️ The Projects

| Project | Status | What the Advanced version adds |
|---|---|---|
| [01 · Read the Knowledge Base](01-read-the-knowledge-base/README.md) | ✅ Built | Every row checked; sensitive data (PII, PCI, secrets) redacted; duplicates removed; a report of every row skipped, removed, redacted or flagged |
| [02 · Documents and Metadata](02-documents-and-metadata/README.md) | ✅ Built | A validated schema for each article, typed and normalized labels, stable IDs, provenance, and loading only what changed |
| [03 · Chunking](03-chunking/README.md) | ✅ Built | Chunks cut along the article's sections, sized in tokens, with stable IDs, parent links and quality checks |
| [04 · Embeddings](04-embeddings/README.md) | ✅ Built | Batching, retries with backoff, a cache so unchanged chunks are never embedded twice, cost and latency tracking, and a sensitive-data gate before anything leaves the machine |
| [05 · Vector Store](05-vector-store/README.md) | ✅ Built | Idempotent upserts and deletes, payload indexes for filters, dense + sparse vectors, consistency checks, and re-indexing without downtime |
| [06 · Retriever](06-retriever/README.md) | ✅ Built | Hybrid search, metadata filters, re-ranking, a "no good match" threshold, query rewriting, and retrieval measured on a labeled set |
| [07 · Grounded Answer](07-grounded-answer/README.md) | ✅ Built | Structured answers with checked citations, saying "I don't know" when the context doesn't cover it, prompt-injection defenses, and a token budget |
| [08 · RAG Engine](08-rag-engine/README.md) | 📝 Planned | One settings object, timeouts and retries for every call, a cache for repeated questions, tracing of every stage, and conversation memory |
| [09 · API](09-api/README.md) | 📝 Planned | Authentication, rate limits, request IDs, structured errors and logs, readiness checks, streaming answers, and a feedback endpoint |
| [10 · Chat Page](10-chat-page/README.md) | 📝 Planned | Streaming replies, clickable sources, safe rendering of model output, accessibility, and loading, empty and error states |
| [11 · Qdrant in Docker](11-qdrant-in-docker/README.md) | 📝 Planned | The app in its own container, health checks, secured and backed-up Qdrant, secrets kept out of images, and a CI pipeline |
| [12 · Tuning](12-tuning/README.md) | 📝 Planned | An evaluation suite for retrieval and answers, experiment tracking, a quality gate in CI, and the model alone compared with RAG |

---

## 🧭 The Themes

Each Advanced project picks up the themes that matter at its step:

| Theme | What it means | Where it shows up |
|---|---|---|
| **Data quality** | Check what comes in; never drop or change anything silently | 01, 02, 03 |
| **Security and privacy** | Find sensitive data early; keep secrets out of code, logs and prompts; defend against injected instructions | 01, 04, 07, 09, 11 |
| **Reliability** | Timeouts, retries, idempotent writes, clear failures | 04, 05, 08, 09 |
| **Retrieval quality** | Find the right chunks, measure it, and know when nothing matches | 03, 06, 12 |
| **Answer quality** | Answers grounded in the sources, with checked citations | 07, 12 |
| **Observability** | Logs, traces and metrics for every stage, with cost and latency | 04, 08, 09 |
| **Operations** | Containers, configuration, backups, CI and deployment | 05, 11 |
| **Evaluation** | A labeled set and numbers to compare changes against | 06, 12 |

---

## 🧱 Design Rules

Every class in the Advanced projects follows these rules:

| Rule | What it means | Why |
|---|---|---|
| **Configure, then work** | A constructor only stores its settings and parts; reading files, calling services and loading models happen in `load()` or `build()` | Making an object costs nothing and can't fail halfway |
| **Each class gets only what it uses** | The loader gets the path, the splitter the sizes, the store its client and collection; only the engine, which wires the parts together, gets them all | Each part can be reused with other sources and tested on its own |
| **Parts are passed in as objects** | Models, clients and splitters are passed in, not the strings used to build them | Tests pass stand-ins; a provider can be swapped without changing the class |
| **Secrets are never constructor parameters** | Keys come from the environment as secret values, and are never stored on an object as plain text | A key can't leak through a printed object, a log line or a traceback |
| **Settings by name, each default in one place** | Settings are passed by name only (`*`); each default is defined once, and reports read it rather than repeat it | No value lands in the wrong setting, and what's reported is what runs |
| **Extend the framework where it's meant to be extended** | Subclass LangChain's `BaseLoader`, `TextSplitter` and `BaseRetriever` | The parts plug into any LangChain chain and keep its methods |
| **Variants by composition, not copies** | A baseline and an optimized engine are one class with different settings or parts | A fix is made once, and the two can't drift apart |

---

## 🚦 Suggested Order

1. **01 → 02 → 03**: get the data right first; every later step depends on it.
2. **04 → 05**: make ingestion safe to re-run, and cheap.
3. **12's evaluation suite, early**: with it, every change to 06 and 07 can be measured instead of guessed.
4. **06 → 07 → 08**: better retrieval, safer answers, a sturdier engine.
5. **09 → 10 → 11**: the API, the page and the deployment.

Each Advanced project follows Advanced/01's pattern: a data file or test setup with one case for each problem it
handles, tests for each case, and a report or log line for everything it skips, changes or flags.
