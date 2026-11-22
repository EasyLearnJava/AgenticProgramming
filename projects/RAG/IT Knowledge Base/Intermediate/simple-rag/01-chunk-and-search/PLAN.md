# Simple RAG: the plan, step by step

Step 1 (`chunk_and_search.ipynb`) is done: a knowledge base of 17 IT articles, chunked (by `##` heading, then 150
characters) into 19 chunks, embedded with MiniLM, stored in Chroma, and searched by meaning. 3 of its 5 test
questions get the wrong article first, and its last cell lists 8 downsides. Every step below fixes one of them.

## Rules for every step

- **One file:** `simple-rag/NN-name/name.ipynb` and nothing else, built like step 1, run once so its outputs are
  saved, then committed.
- **The same knowledge base and test questions.** Articles or questions are added only when a step needs them, and
  the notebook says what it added.
- **Every notebook ends the same way:** the RIGHT/WRONG results and a "Downsides" cell that leads to the next step.
- **Embeddings stay local** (MiniLM: free, unlimited). Gemini is used only where a step needs an LLM.
- **Base plus one technique.** Steps 2 to 5 stack up into a strong base. From step 6 on, each notebook is that base
  plus one technique, with a before/after on the same questions. Steps 15 to 17 are the exception: each one builds
  on the one before.

## The steps

### Group 1: Retrieval basics (builds the base)

| Step | Notebook | What it adds | Fixes downside | Gemini? |
|---|---|---|---|---|
| 02 | `naive-rag` | Gemini writes an answer from the 3 chunks | 8: no answer | Yes, 1 call per question |
| 03 | `semantic-chunking` | Cut where the meaning changes, not at 150 characters | 7: character chunking | No |
| 04 | `hybrid-search` | BM25 keyword search plus vectors, merged | 3: 0x800CCC0F vs. 0x800CCC0E | No (new package `rank_bm25`) |
| 05 | `reranking` | A cross-encoder rereads the top 10 and keeps the best 3 | 1, 4: laptop key, close calls | No (model already downloaded) |

### Group 2: Query transformation (each changes the question before searching)

| Step | Notebook | What it adds | New kind of test question | Gemini? |
|---|---|---|---|---|
| 06 | `query-rewriting` | Rewrites vague questions | "it still doesn't work, what now?" | Yes |
| 07 | `multi-query` | Searches 3 rewordings and merges the results | Questions with unusual wording | Yes |
| 08 | `hyde` | Searches with a made-up answer instead of the question | Short questions | Yes |
| 09 | `query-decomposition` | Splits two-part questions | "What's the Denali code and when is the change freeze?" | Yes |
| 10 | `query-routing` | Picks the right source | Needs a 2nd source, e.g. a small HR policy set | Optional (embeddings can route) |

### Group 3: Context optimization

| Step | Notebook | What it adds | Fixes downside | Gemini? |
|---|---|---|---|---|
| 11 | `parent-child` | Search small chunks, return the whole article | 6: C5 without "YubiKey" | No |
| 12 | `metadata-filtering` | Mark articles `status: retired` and filter them out | 2: retired help desk number | No |
| 13 | `contextual-retrieval` | Gemini writes a line of article context onto each chunk | 6, another way | Yes, 1 call per chunk (19), saved to reuse |
| 14 | `context-compression` | Keep only the sentences that answer the question | Long chunks with noise | Optional (embeddings can filter) |

### Group 4: Advanced architectures

| Step | Notebook | What it adds | Fixes | Gemini? |
|---|---|---|---|---|
| 15 | `corrective-rag` | Grades the chunks; if all are weak, says "I don't know" | 5: always 3 results | Yes |
| 16 | `self-rag` | Step 15, plus checking its own answer against the chunks | Made-up answers | Yes |
| 17 | `adaptive-rag` | Picks a strategy per question, using steps 10, 15 and 16 | Mixed question types | Yes |
| 18 | `agentic-rag` | Gemini decides when and what to search, using tools | Multi-step questions | Yes, several calls |
| 19 | `graph-rag` | Entities and links (person, system, team) in a graph | "Who do I escalate to, and how?" | Yes (new package `networkx`) |

### Group 5: Multimodal and evaluation

| Step | Notebook | What it adds | Gemini? |
|---|---|---|---|
| 20 | `multimodal-rag` | Search images (screenshots) and tables | Optional (CLIP model, about 600 MB, runs locally) |
| 21 | `rag-evaluation` | Hit rate and MRR for retrieval; Gemini-judged faithfulness and relevance of answers, compared across steps | Yes, a judge call per answer |

## Gemini: which steps need it

| Gemini needed? | Steps | Count |
|---|---|---|
| Yes | 02, 06, 07, 08, 09, 13, 15, 16, 17, 18, 19, 21 | 12 |
| Optional (a free local option exists) | 10, 14, 20 | 3 |
| No | 03, 04, 05, 11, 12 | 5 |

The retrieval steps (03, 04, 05, 11, 12) could also call Gemini for an answer after step 2, but they won't: their
improvement shows in which chunks come back, so they stay free and fast.

Rough calls per run with 5 test questions (estimates until each notebook is built): steps 02, 06, 07, 08: 5 to 10;
steps 09, 15, 16: 15 to 25; steps 13 and 19: about 20 the first time, then saved and reused; steps 17, 18, 21:
20 to 30, with pauses between calls for the free tier.

## Things to know

- **The Gemini key** is set as the `GOOGLE_API_KEY` environment variable (with `setx`, in a Command Prompt), and
  checked working with `gemini-3.5-flash-lite`. Notebooks read it with `os.environ["GOOGLE_API_KEY"]`; the key never
  goes in a notebook.
- **Step 2 may hide retrieval mistakes.** Gemini sees all 3 chunks, so for "My new laptop asks for a key" it will
  probably still answer from BitLocker, the second chunk. From step 2 on, the check judges the answer as well as the
  top chunk.
- **The knowledge base grows** at step 3 (long articles), 10 (a second source), 12 (a status field), 19 (named people
  and teams) and 20 (images and tables).
- **Kernel:** every notebook runs on the `simple-rag (Python 3.13)` kernel (the venv at
  `%USERPROFILE%\venvs\simple-rag`). The system Python fails to load the model with a `RecursionError`.

## Still open

- **When evaluation comes:** at step 21 as listed, or right after step 5, so every later step is measured properly
  instead of only by its RIGHT/WRONG count.
