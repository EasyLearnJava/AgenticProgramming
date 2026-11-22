# Simple RAG: the plan, step by step

Step 1 (`chunk_and_search.ipynb`) is done: a knowledge base of 17 IT articles, chunked (by `##` heading, then 150
characters) into 19 chunks, embedded with MiniLM, stored in Chroma, and searched by meaning. 3 of its 5 test
questions get the wrong article first, and its last cell lists 8 downsides.

The series has two goals: learn every technique in the original list of 20, and learn chunking strategies side by
side (where to use each one, why, its advantage and its cost). **RAGAS is the yardstick for every step from 02 on:**
a technique counts as an improvement only when its RAGAS scores say so.

## Decisions made (2026-11-22)

- RAGAS scores every step, from step 02 on.
- Chunking is its own phase (steps 04 to 14). Semantic Chunking, Parent-Child and Contextual Retrieval moved into it
  from their original groups; all 20 techniques are still in the plan.
- **Shared data folder:** `simple-rag/shared/` holds the knowledge base files, the golden test set and `scores.csv`.
  It is the one exception to "one notebook file per step", so every step reads the same frozen data.
- Still open: the judge model, picked from the daily limits on AI Studio's rate limit page (see "Still open").

## Rules for every step

- **One notebook:** `simple-rag/NN-name/name.ipynb`, reading its data from `simple-rag/shared/`, run once so its
  outputs are saved, then committed.
- **Frozen data:** the knowledge base and golden test set are frozen in step 02, so every step's scores compare.
- **Every notebook ends the same way:** its RAGAS scores next to the earlier steps' (one row added to
  `shared/scores.csv`), and a "Downsides" cell that leads to the next step. Chunking notebooks also end with
  "Where to use it, why, advantage, cost".
- **Embeddings stay local** (MiniLM). Gemini writes answers and judges them.

## The RAGAS scorecard

| Tier | Metrics | Needs | Gemini calls per question |
|---|---|---|---|
| Free | `IDBasedContextRecall` at top 1 and top 3, with section titles as the IDs | The retrieved and expected section IDs | 0 |
| Retrieval | `ContextPrecision`, `ContextRecall` | Question, retrieved chunks, reference answer (no generated answer) | 4 (3 + 1) |
| Answer (from step 03) | `Faithfulness`, `AnswerRelevancy` (MiniLM embeddings) | Plus the generated answer | about 6 more (2 + 3, plus the answer itself) |
| Targeted (one step each) | `NoiseSensitivity`, `FactualCorrectness`, `AnswerAccuracy`, `ContextEntityRecall`, `AgentGoalAccuracy`, `ToolCallAccuracy`, `MultiModalFaithfulness`, `MultiModalRelevance` | Depends on the metric | Varies |

How a step is judged:

- **Sweeps** (for example 6 chunk sizes) use only the free scores; the Gemini scores run on the best one or two.
- **A change counts** only if its target metric rises by more than the judge noise measured in step 02, and no core
  metric drops by more than that noise. With about 20 questions, one question is already 0.05.
- **Answer metrics** run only in steps that change the answer.

Verified against RAGAS 0.4.4 (its source and a pip dry run):

- The free ID-based context precision is not rank-aware (hits / retrieved), so the plan uses ID-based recall at top 1
  and top 3 instead.
- RAGAS's text-matching metrics would count the wrong room as correct: the Room Everest and Room Denali chunks are
  0.909 similar (Levenshtein) against a 0.5 threshold. The free scores use IDs for this reason.
- A plain `pip install ragas` picks instructor 1.3.2, which has no `from_genai`, so Gemini as judge fails. Install
  `ragas==0.4.4 "instructor>=1.11"` (resolves to instructor 1.17.0, which has it).
- Gemini connects through the `google-genai` client: `llm_factory(model, provider="google", client=...)`.

## The steps

### Phase 1: Foundation

| Step | Notebook | What it does |
|---|---|---|
| 01 | `chunk-and-search` | Done. Markdown headers plus a recursive split, MiniLM, Chroma, top 3 |
| 02 | `ragas-setup` | Freeze the knowledge base and golden set in `shared/`, install RAGAS, score step 01's search, run the Gemini scores twice to measure judge noise |
| 03 | `naive-rag` | gemini-3.5-flash-lite writes answers; first full scorecard; the baseline every later step must beat |

### Phase 2: Chunking strategies

Each notebook: what the strategy is, where to use it, why, its advantage, its cost, and its RAGAS scores against
the strategies before it.

| Step | Notebook | What it does | Best for |
|---|---|---|---|
| 04 | `fixed-size-chunking` | Cut every N characters; sweep 3 sizes with and without overlap | A quick baseline on plain text |
| 05 | `recursive-chunking` | Cut at paragraphs, then lines, then spaces | The general default for mixed text |
| 06 | `token-chunking` | Cut by MiniLM's own tokens so no chunk passes its 256-token limit | When the embedding model's limit is tight |
| 07 | `sentence-chunking` | Groups of sentences with one sentence of overlap; never cuts a sentence | Prose and transcripts |
| 08 | `structure-chunking` | Markdown and HTML headings, with the heading path kept as metadata | Documents with headings |
| 09 | `document-type-chunking` | Code at function and block boundaries, JSON one record per chunk, tables one row with its header, FAQ one question and answer per chunk | Formats with their own natural units |
| 10 | `semantic-chunking` | Cut where neighbouring sentences stop being similar (MiniLM, written in plain Python) | Long text that changes topic without headings |
| 11 | `parent-child-chunking` | Search small chunks, give the LLM the whole parent section; plus the sentence-window variant | Precise matching with full context for the answer |
| 12 | `contextual-chunking` | Add the document and heading to each chunk for free, then compare with Gemini-written context per chunk (Contextual Retrieval) | Chunks that lose their subject, like C5 without "YubiKey" |
| 13 | `proposition-chunking` | Gemini rewrites each document into standalone facts (one call per document) | Dense, fact-heavy documents |
| 14 | `chunking-scorecard` | Every strategy on every document type in one RAGAS table, the full scorecard for the top 3, and a decision guide (document type, best strategy, why). From here on the base pipeline chunks each document type with its winner | |

### Phase 3: Retrieval and context

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 15 | `hybrid-search` | BM25 keywords plus vectors (`rank_bm25`) | ID recall at top 1 on exact codes (0x800CCC0F, 4471) |
| 16 | `reranking` | The ms-marco cross-encoder (already downloaded) rereads the top 10 and keeps 3 | `ContextPrecision` on word-overlap questions |
| 17 | `metadata-filtering` | Drop articles marked `status: retired` | `FactualCorrectness` on retired facts (555-0199, not 555-0100) |
| 18 | `context-compression` | Keep only the sentences that answer the question | `NoiseSensitivity`, `Faithfulness` |

### Phase 4: Query transformation

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 19 | `query-rewriting` | Gemini rewrites vague questions | `ContextRecall` on vague questions |
| 20 | `multi-query` | Search 3 rewordings and merge the results | `ContextRecall` overall |
| 21 | `hyde` | Search with a made-up answer instead of the question | `ContextRecall` on short questions |
| 22 | `query-decomposition` | Split two-part questions | `ContextRecall` on two-part questions |
| 23 | `query-routing` | Send each question to the IT or HR source | `ContextPrecision` on HR questions |

### Phase 5: Architectures

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 24 | `corrective-rag` | Grade the chunks; say "I don't know" when all are weak | `AnswerAccuracy` on unanswerable questions |
| 25 | `self-rag` | Step 24, plus checking its own answer against the chunks | `Faithfulness` |
| 26 | `adaptive-rag` | Pick a strategy per question, using steps 23, 24 and 25 | The whole scorecard across all question types |
| 27 | `agentic-rag` | Gemini decides when and what to search, using tools | `AgentGoalAccuracy`, `ToolCallAccuracy`, plus the core scores |
| 28 | `graph-rag` | People, systems and teams in a graph | `ContextEntityRecall` on relationship questions |

### Phase 6: Multimodal and final

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 29 | `multimodal-rag` | Search images and tables; images drawn inside the notebook | `MultiModalFaithfulness`, `MultiModalRelevance` |
| 30 | `final-scorecard` | Every step's RAGAS scores in one table; the best pipeline built from only the winners, scored again | All |

## The shared data (built in step 02)

- **Knowledge base:** step 01's 17 articles, plus a long policy document with sections, an unstructured incident
  transcript, an HTML intranet page, a Markdown table, a PowerShell script, JSON ticket records, an FAQ, HR policies
  (for routing) and team and escalation links (for GraphRAG). Each piece is tagged with metadata such as `status` and
  `source`.
- **Golden test set:** about 20 questions, each with a hand-written reference answer, the section it must come from,
  and a type: word overlap, exact code, retired fact, fact at the end of a long section, transcript, table, code,
  JSON, FAQ, vague, two-part, HR, relationship, unanswerable.
- **`scores.csv`:** one row per step, so step 30 compares every step without running them again.

## Models and packages

- **Answers:** `gemini-3.5-flash-lite`. **Judge:** `gemini-3.5-flash` or `gemma-4-26b-a4b-it` (both checked working on
  the key), whichever has enough requests per day. The judge makes about 9 of every 10 calls, so its limit sets the
  pace. Not on the free tier (429, limit 0): `gemini-4-neon`, `gemini-3.1-pro-preview`.
- **The key:** `GOOGLE_API_KEY`, set with `setx`; notebooks read it with `os.environ` and it never goes in a file.
- **Packages:** `ragas==0.4.4` with `"instructor>=1.11"` at step 02 (upgrades langchain-core 1.6.6 to 1.8.4, so step
  01 is run once again after), `beautifulsoup4` at step 08 (HTML splitting fails without it), `rank_bm25` at step 15.
  Sentence and semantic chunking are written in plain Python with MiniLM: no NLTK, spaCy or `langchain_experimental`.
- **Kernel:** `simple-rag (Python 3.13)`, the venv at `%USERPROFILE%\venvs\simple-rag`. The system Python fails to load
  the model with a `RecursionError`.
- **RAGAS cache:** RAGAS's disk cache sits outside the repo, so rerunning unchanged questions costs no calls.

## Things to know

- **MiniLM reads only its first 256 tokens,** about 1,182 characters of this IT text. A fact added after that point
  does not change the embedding at all (tested), so anything longer in a chunk is invisible to search. Step 06 shows it.
- **Step 03 may hide retrieval mistakes:** Gemini sees all 3 chunks, so for "My new laptop asks for a key" it may still
  answer from BitLocker, the second chunk. That is why retrieval and answers are scored separately.
- **Cost (estimate):** about 5,000 Gemini calls over the series, mostly judge calls.

## Left out on purpose

- **Late chunking:** it needs a long-context embedding model; MiniLM stops at 256 tokens, so it cannot show the idea.
- **RAGAS-generated test sets as the main yardstick:** a hand-written golden set is cheaper on the free tier and every
  reference answer is known to be right. Step 30 can optionally check the wins on generated questions.

## Still open

- **The judge model:** read the requests per day for `gemini-3.5-flash`, `gemini-3.5-flash-lite` and
  `gemma-4-26b-a4b-it` on https://aistudio.google.com/rate-limit (Dashboard, then Rate Limit), for the project that
  owns the key.
