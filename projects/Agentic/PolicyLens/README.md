# PolicyLens

**Ask your policies. See the evidence.**

PolicyLens is a modular RAG application for the Week 2 Enterprise Policy Q&A assignment. It includes a local web interface, LangChain document processing, a LangGraph answer pipeline, hybrid retrieval, source citations, document uploads, and a runnable evaluation with 15 assignment questions, 6 first-review regressions and 30 locked challenge cases.

## Start on Windows

Double-click **`Start-PolicyLens.cmd`** in this folder, then open **http://127.0.0.1:8765**. Keep its terminal open while using the app; press Ctrl+C to stop it. Port 8765 avoids the common port 8000.

On a new machine, install Python 3.11–3.14 and preferably [uv](https://docs.astral.sh/uv/getting-started/installation/). The launcher uses uv when available and otherwise uses Python's venv + pip. The first dependency installation needs internet access. The bundled corpus and tokenizer allow extractive mode to run offline afterward.

Manual setup with uv:

```powershell
uv sync --frozen
Copy-Item .env.example .env  # Only if you do not already have .env
uv run python scripts/manage.py index
uv run python run.py
```

Alternative with standard Python:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe scripts/manage.py index
.venv\Scripts\python.exe run.py
```

Use `.venv\Scripts\python.exe run.py --port 8770` if 8765 is busy. Then open that port in your browser.

## Two explicit modes

| Mode | Embeddings | Answering | API key |
|---|---|---|---|
| `extractive` (default) | Deterministic 768-dimensional lexical hash vectors | Up to three verbatim source passages with citations | None |
| `openai` | Neural `text-embedding-3-small` by default | `gpt-4.1-mini` structured, cited claims | Required |

The preview is useful for learning the ingestion, retrieval, citations and evaluation flow. **It does not provide neural semantic retrieval or LLM-generated answers.** The full neural RAG path is implemented in OpenAI mode.

To enable generated answers, edit your local `.env`:

```dotenv
RAG_MODE=openai
OPENAI_API_KEY=your-key-here
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

Restart the server and click **Knowledge base → Rebuild index**. Changing the embedding provider/model or chunk settings invalidates the old index. The application will block questions until you rebuild, avoiding incompatible vector searches. An OpenAI key alone does not silently enable network calls: choose the mode explicitly.

OpenAI mode sends document text for embeddings, and questions plus retrieved passages for generation and a separate claim-support review, to OpenAI. A generated answer normally uses two model calls. Indexing, questions and evaluations incur your provider's normal usage charges. Keys stay in `.env`; they are not returned by the status API or included in reports. `.env` is ignored by Git.

## Explore the workspace

- **Ask a question:** Try a starter question, filter by one document, open numbered citations, and expand ranking scores or pipeline steps.
- **Knowledge base:** Read source documents, upload `.md`, UTF-8 `.txt` or text-based `.pdf`, and rebuild the index. Limits: 10 MB per file and 300 pages per PDF; scanned PDFs require OCR elsewhere.
- **Evaluation lab:** Run all 51 questions, inspect each failure, and download the report as Markdown or JSON.
- **How it works:** Follow the stages and the source files responsible for each one.
- **API documentation:** Visit http://127.0.0.1:8765/docs while the server is running.

## Project map

```text
PolicyLens/
├── Start-PolicyLens.cmd         # Windows launcher; checks dependencies and starts app
├── run.py                      # Local server entry point; optional --port
├── pyproject.toml              # Direct dependencies and test configuration
├── uv.lock                     # Exact reproducible dependency resolution
├── requirements.txt            # Pinned pip alternative exported from uv.lock
├── .env.example                # Documented settings; copy to .env
├── README.md                   # Start here
├── docs/
│   ├── ARCHITECTURE.md          # Module responsibilities and request flow
│   ├── PROJECT_BRIEF.md         # Assignment one-liner and completed framework
│   ├── REVIEW2_FIXES.md         # Round-two findings, changes and limits
│   ├── REVIEW_FIXES.md          # Findings, fixes, tests and remaining limitations
│   └── EVALUATION_GUIDE.md      # Metrics, manual review and baseline findings
├── src/policylens/
│   ├── api.py                  # HTTP validation and routes
│   ├── config.py               # Configuration and project-relative paths
│   ├── models.py               # Shared typed inputs, chunks, answers and citations
│   ├── uploads.py              # Stable revisions, history, remove/restore
│   ├── service.py              # Shared operations used by HTTP and CLI
│   ├── pipeline.py             # LangGraph retrieval/assessment/answer routing
│   ├── generation.py           # OpenAI generation, extraction and citation checks
│   ├── evaluation.py           # Scoring, background jobs and report generation
│   ├── text.py                 # Normalization and token helpers
│   ├── grounding.py            # Conservative scope and passage-body checks
│   ├── middleware.py           # Early bounded request-body handling
│   ├── diagnostics.py          # Local stack locations without request/secret text
│   ├── network.py              # Verified TLS and a mockable HTTP client factory
│   ├── ingestion/
│   │   ├── loaders.py          # Local document parsing and cleaning
│   │   └── chunking.py         # Heading-aware, token-limited chunks
│   └── retrieval/
│       ├── embeddings.py       # Lexical preview and OpenAI adapters
│       ├── store.py            # Transactional SQLite persistence
│       └── hybrid.py           # BM25, cosine search, RRF and reranking
├── web/
│   ├── index.html              # Accessible workspace markup
│   ├── styles.css              # Design tokens and responsive layouts
│   ├── favicon.svg             # Small vector brand asset
│   └── js/
│       ├── app.js              # Navigation and feature wiring
│       ├── api.js              # Fetch, timeouts and HTTP errors
│       ├── ui.js               # Safe rendering, dialogs and formatting
│       ├── ask.js              # Question and citation interactions
│       ├── knowledge.js        # Document uploads and indexing
│       ├── evaluation.js       # Evaluation progress and results
│       └── rendering.js        # Tested citation, duration and keyboard helpers
├── data/
│   ├── corpus/                 # Six real public handbook snapshots + sources.json
│   ├── tokenizer/              # Offline cl100k_base vocabulary
│   ├── uploads/                # Your documents (ignored by Git)
│   └── index/                  # Generated SQLite index (ignored by Git)
├── evaluation/                 # Original 15 + 6 regressions + 30 locked challenge cases
├── reports/
│   ├── BASELINE.md             # Observed first extractive evaluation
│   ├── REVIEW2_EVALUATION.md    # Current 51-case report with suite-level results
│   ├── REVIEW_EVALUATION.md     # Updated 21-case report with stricter evidence checks
│   └── runs/                   # Actual JSON + Markdown evaluation exports
├── scripts/
│   ├── fetch_corpus.py          # Manual public-source refresh with provenance
│   └── manage.py               # CLI: index, ask, status, evaluate
└── tests/                      # Focused grounding, ingestion, retrieval and API checks
```

## Commands

Run these from this folder:

```powershell
# Build/rebuild the vector + keyword index
uv run python scripts/manage.py index

# Ask through the same pipeline used by the browser
uv run python scripts/manage.py ask "What receipts are required for expenses?"

# Save an evaluation report under reports/runs/
uv run python scripts/manage.py evaluate

# Inspect configuration, freshness and index status
uv run python scripts/manage.py status

# Refresh the public snapshot, then rebuild
uv run python scripts/fetch_corpus.py
uv run python scripts/manage.py index

# Run the focused automated checks
uv run pytest -q
```

## How the RAG pipeline works

1. Load local documents into LangChain `Document` objects. Preserve PDF page numbers and source metadata.
2. Split on Markdown headings, then at 500 actual `cl100k_base` tokens with 75-token overlap inside long sections. Short headings may yield smaller chunks.
3. Embed each chunk and store text, numeric vectors and metadata in SQLite. Replace the index in a single transaction.
4. Retrieve BM25 and cosine candidates, join rankings with reciprocal rank fusion, then apply a transparent lexical reranker. Default: up to 16 candidates per channel, top 5 final chunks.
5. Shared stemmed topic features clarify vague questions. Preview assesses rarity-weighted local evidence and requested answer types; neural mode passes uncertain paraphrases to model checks.
6. Generate structured claims in OpenAI mode, or select verbatim passages in preview mode. Reject unknown citations, heading-only quotes and obvious contradictions; generated answers also require a separate model support/completeness review.

SQLite exact vector search keeps the small-corpus implementation readable. This is a local, single-user educational app, not an authenticated enterprise deployment. A larger corpus would benefit from an ANN vector database, ingestion jobs and a neural reranker.

## Review fixes and validation

See `docs/REVIEW2_FIXES.md` for the current review disposition and `docs/REVIEW_FIXES.md` for the earlier history. The release passes **61 Python tests and 8 frontend tests**:

```powershell
uv run pytest -q
# Optional UI development tests; not needed to start the app:
npm ci --ignore-scripts
npm test
```

The current extractive run uses six documents, 269 original-text chunks and 51 questions. The original 15 questions, six first-review regressions and 30 locked challenge cases are reported separately. The challenge file was fixed before this round's implementation and kept unchanged, but was used during development; it is not a blind held-out benchmark.

| Check | Observed |
|---|---:|
| Routing, all suites | 50 / 51 |
| Routing, challenge suite | 29 / 30 |
| Complete reference checks, all suites | 41 / 51 |
| Complete reference checks, challenge suite | 26 / 30 |
| Human faithfulness / semantic relevance | Not measured |

H05 remains a false refusal for the paraphrase “submitted late”; preview does not connect it reliably to the 90-day rule. Other reference-completeness gaps remain visible in `reports/REVIEW2_EVALUATION.md`. The 95% faithfulness, 90% relevance and 10-second request-latency targets remain unverified targets. OpenAI request schemas, refusal paths and semantic rejection are mocked in tests; live quality and latency require a configured key and separate measurement.

Quote integrity is an accepted-output invariant, not an answer-quality score. Generated claims receive an additional model support check, which can still err or share generation errors. Preview uses Snowball stems, rarity-weighted local overlap, section context and answer-type heuristics; it can still misread intent or refuse valid paraphrases. Unicode/CJK lexical fallback does not provide full multilingual semantic understanding.

Pipeline P95 excludes HTTP and session setup and is labeled accordingly. Repeated requests reuse cached vectors, profiles and unchanged-file hashes; file bytes are forcibly rechecked at least every 30 seconds, while changed file statistics trigger immediate verification. Rebuilds always parse and verify captured bytes. Source freshness is a separate seven-day manual-refresh target, not an automatic SLA.

## Uploaded document revisions

Uploading the same cleaned filename and extension replaces its active revision; previous bytes remain under `data/upload_history/`. Markdown and TXT are distinct identities even with identical content. **Remove** hides an upload from the next index; **Removed documents → Restore** recovers it. Rebuild after upload, replacement, removal or restore. Legacy content-hash filenames are migrated with the newest logical revision active and original files retained.

The server runs locally, verifies Host/Origin and request size, prevents framing, and keeps ambient LangSmith tracing disabled. `.env`, uploads, history and indexes are local runtime data. The six starter pages remain a dated subset of GitLab's handbook; linked documents are not fetched automatically.

## Sources and acknowledgements

Starter text is adapted from GitLab's public handbook, with navigation removed and headings preserved. Each file's canonical URL, fetch date, SHA-256 and owner are in `data/corpus/sources.json`. The original GitLab repository license is reproduced in `THIRD_PARTY_NOTICES.md`. GitLab owns the source of truth; this educational app is unaffiliated with GitLab.

Implementation references: [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api), [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), and [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

