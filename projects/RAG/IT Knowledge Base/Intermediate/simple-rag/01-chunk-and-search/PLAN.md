# Simple RAG: the plan, step by step (final, 2026-11-22)

Step 1 (`chunk_and_search.ipynb`) is done: a knowledge base of 17 IT articles, chunked (by `##` heading, then 150
characters) into 19 chunks, embedded with MiniLM, stored in Chroma, and searched by meaning. 3 of its 5 test
questions get the wrong article first, and its last cell lists 8 downsides.

The series has two goals: learn every technique in the original list of 20, and learn chunking strategies side by
side (where to use each one, why, its advantage and its cost). **RAGAS is the yardstick for every step from 02 on:**
a technique counts as an improvement only when its RAGAS scores say so.

## Decisions (2026-11-22)

- **RAGAS scores every step** from step 02 on.
- **Chunking is its own phase** (steps 04 to 14). Semantic Chunking, Parent-Child and Contextual Retrieval moved into
  it from their original groups; all 20 techniques are still in the plan.
- **Shared data folder:** `simple-rag/shared/` holds the knowledge base, the golden test set and `scores.csv`. It is
  the one exception to "one notebook file per step", so every step reads the same frozen data.
- **Answers:** `gemini-3.5-flash-lite`.
- **Judge:** `gemini-3.5-flash-lite`. Tested 2026-11-22 with a RAGAS-style "is this chunk useful?" judgment: it works
  through function calling (instructor's default mode for Gemini, which RAGAS uses) and through JSON schema output,
  and gave the right verdict with a sound reason both times. The catch: it grades its own answers.
- **Limits** (from AI Studio's rate limit page): flash-lite 500 requests a day, about 15 a minute, about 250K input
  tokens a minute. Gemma 4 26B about 14,400 a day, 30 a minute, about 16K input tokens a minute.

## Rules for every step

- **One notebook:** `simple-rag/NN-name/name.ipynb`, reading its data from `simple-rag/shared/`, run once so its
  outputs are saved, then committed.
- **Frozen data:** the knowledge base and golden test set are built and checked in step 02 and never change after,
  so every step's scores compare.
- **Every notebook ends the same way:** its RAGAS scores next to the earlier steps' (one row added to
  `shared/scores.csv`), and a "Downsides" cell that leads to the next step. Chunking notebooks also end with
  "Where to use it, why, advantage, cost".
- **Embeddings stay local** (MiniLM). Gemini writes the answers and judges them.

## The RAGAS scorecard

| Tier | Metrics | Needs | Gemini calls per question |
|---|---|---|---|
| Free | `IDBasedContextRecall` at top 1 and top 3 | The evidence IDs found in the retrieved chunks, and the expected ones | 0 |
| Retrieval | `ContextPrecision`, `ContextRecall` | Question, retrieved chunks, reference answer (no generated answer) | 4 (3 + 1) |
| Answer (from step 03) | `Faithfulness`, `AnswerRelevancy` with `strictness=1` (MiniLM embeddings) | Plus the generated answer | 4 (1 answer + 2 + 1) |
| Targeted (one step each) | `NoiseSensitivity`, `FactualCorrectness`, `AnswerAccuracy`, `ContextEntityRecall`, `AgentGoalAccuracy`, `ToolCallAccuracy`, `MultiModalFaithfulness`, `MultiModalRelevance` | Depends on the metric | Varies; run only on that step's target questions |

**Evidence IDs make the free scores fair to every chunking strategy.** Each golden question stores its evidence: the
exact sentence or sentences that answer it, each with an ID. A retrieved chunk "hits" an evidence ID when it contains
that whole sentence. A strategy that cuts the sentence in half misses it, which is exactly the failure the free score
should show. Step 13 rewrites the text, so there a chunk hits when it comes from the evidence's section.

How a step is judged:

- **Free scores are deterministic** (same retrieval, same result), so they decide the retrieval steps. The Gemini
  scores confirm them and catch regressions.
- **Judge noise** is measured in steps 02 and 03 by running the Gemini scores twice. A change counts only if its
  target score rises by more than that noise and no core score drops by more than it. With 37 text questions, one
  question is already 0.027 overall.
- **Sweeps** (for example 6 chunk sizes) use only the free scores; the Gemini scores run on the best one or two.
- **Unanswerable questions** have no evidence, so they count only in the answer scores (RAGAS returns no value for
  them in retrieval recall). **Image questions** are reported separately until step 29.

**Budget on flash-lite (500 a day, about 15 a minute):** a retrieval-only run is about 140 calls (about 10 minutes); a
full run is about 290 calls (about 20 minutes). That allows one full run plus one retrieval run a day. RAGAS's disk
cache makes rerunning unchanged questions free. Whole series (estimate): about 7,000 calls, about 14 days of the limit.

Verified against RAGAS 0.4.4 (its source and a pip dry run):

- The free ID-based context precision is not rank-aware (hits / retrieved), so the plan uses ID-based recall at top 1
  and top 3 instead.
- RAGAS's text-matching metrics would count the wrong room as correct: the Room Everest and Room Denali chunks are
  0.909 similar (Levenshtein) against a 0.5 threshold. The free scores use evidence IDs for this reason.
- A plain `pip install ragas` picks instructor 1.3.2, which has no `from_genai`, so Gemini as judge fails. Install
  `ragas==0.4.4 "instructor>=1.11"` (resolves to instructor 1.17.0, which has it).
- Gemini connects through the `google-genai` client: `llm_factory(model, provider="google", client=...)`, which uses
  instructor's function calling mode.

## The steps

### Phase 1: Foundation

| Step | Notebook | What it does |
|---|---|---|
| 01 | `chunk-and-search` | Done. Markdown headers plus a recursive split, MiniLM, Chroma, top 3 |
| 02 | `ragas-setup` | Build `shared/` (documents, drawn images, golden set), run the data checks below, install RAGAS, score step 01's search, run the Gemini scores twice to measure judge noise |
| 03 | `naive-rag` | flash-lite writes answers; first full scorecard, run twice for noise; the baseline every later step must beat |

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
| 12 | `contextual-chunking` | Add the document and heading to each chunk for free, then compare with Gemini-written context per chunk (Contextual Retrieval) | Chunks that lose their subject, like the YubiKey replacement chunk |
| 13 | `proposition-chunking` | Gemini rewrites each document into standalone facts (one call per document) | Dense, fact-heavy documents |
| 14 | `chunking-scorecard` | Every strategy on every document type in one RAGAS table, the full scorecard for the top 3, and a decision guide (document type, best strategy, why). From here on the base pipeline chunks each document type with its winner | |

### Phase 3: Retrieval and context

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 15 | `hybrid-search` | BM25 keywords plus vectors (`rank_bm25`) | ID recall at top 1 on exact codes and IDs |
| 16 | `reranking` | The ms-marco cross-encoder (already downloaded) rereads the top 10 and keeps 3 | `ContextPrecision` on word-overlap questions |
| 17 | `metadata-filtering` | Drop everything marked `status: retired` | `FactualCorrectness` on retired facts |
| 18 | `context-compression` | Keep only the sentences that answer the question | `NoiseSensitivity`, `Faithfulness` |

### Phase 4: Query transformation

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 19 | `query-rewriting` | Gemini rewrites vague questions | `ContextRecall` on vague questions |
| 20 | `multi-query` | Search 3 rewordings and merge the results | `ContextRecall` on unusually worded questions |
| 21 | `hyde` | Search with a made-up answer instead of the question | `ContextRecall` on short questions |
| 22 | `query-decomposition` | Split two-part questions | `ContextRecall` on two-part questions |
| 23 | `query-routing` | Send each question to the IT or HR source | `ContextPrecision` on HR questions |

### Phase 5: Architectures

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 24 | `corrective-rag` | Grade the chunks; say "I don't know" when all are weak | `AnswerAccuracy` on unanswerable and partly answerable questions |
| 25 | `self-rag` | Step 24, plus checking its own answer against the chunks | `Faithfulness` on partly answerable questions |
| 26 | `adaptive-rag` | Pick a strategy per question, using steps 23, 24 and 25 | The whole scorecard across all question types |
| 27 | `agentic-rag` | Gemini decides when and what to search, using tools | `AgentGoalAccuracy`, `ToolCallAccuracy`, plus the core scores |
| 28 | `graph-rag` | People, systems and teams in a graph | `ContextEntityRecall` on relationship questions |

### Phase 6: Multimodal and final

| Step | Notebook | What it does | RAGAS target |
|---|---|---|---|
| 29 | `multimodal-rag` | Search the images and tables in `shared/` | `MultiModalFaithfulness`, `MultiModalRelevance` |
| 30 | `final-scorecard` | Every step's RAGAS scores in one table; the best pipeline built from only the winners, scored again | All |

## The shared data (built and checked in step 02)

### Documents

All new topics: none of the old ones (VPN, MFA, password, printer, WiFi, Salesforce, Teams audio, attachment limit,
database timeout, slow laptop). Every piece carries metadata: `source` (IT or HR), document type, and `status`
(current or retired).

| ID | File | What it is | What it teaches | Questions |
|---|---|---|---|---|
| D1 | `it_articles.md` | Step 01's 17 short articles, unchanged | Word overlap, exact codes, the retired help desk number, chunks that lose their subject | Q01 to Q07, Q34, Q35 |
| D2 | `remote_work_policy.md` | A long policy with `##` and `###` headings; some sections longer than 1,182 characters | Facts past MiniLM's limit, dense paragraphs, a paragraph that never names its subject | Q08 to Q12, Q29, Q36, Q40 |
| D3 | `outage_transcript.txt` | A call transcript with timestamps and speakers, no headings, changing topics | Sentence and semantic chunking | Q13 to Q15 |
| D4 | `software_catalog.html` | An HTML intranet page with h1, h2 and h3 sections and lists | HTML structure chunking | Q16, Q17 |
| D5 | `laptop_models.md` | A Markdown table of laptop models (RAM, price, status), with retired rows | Table chunking, retired rows, exact model names | Q18 to Q20 |
| D6 | `cleanup_script.ps1` | A PowerShell script with functions and comments | Code chunking | Q21, Q22 |
| D7 | `tickets.json` | Ticket records (ID, room, issue, status, resolution) | One record per chunk, exact IDs | Q23, Q24 |
| D8 | `faq.md` | Question and answer pairs | One pair per chunk | Q25, Q26 |
| D9 | `hr_policies.md` | Leave, approvals and expenses, with a retired expense tool | The second source, for routing | Q27 to Q29 |
| D10 | `teams_and_escalation.md` | Teams, the systems they own, leads, on-call by week, the escalation chain | Graph relationships, multi-step lookups | Q30, Q31 |
| D11 | `images/` | A floor plan, an error screenshot and a ticket volume chart, drawn in step 02 | Image retrieval | Q37 to Q39 |

### Golden test set (40 questions)

Each question gets, in step 02: a hand-written reference answer, its evidence (the exact sentences, with IDs), its
tags, and whether it can be answered.

| ID | Question | Document | Tags |
|---|---|---|---|
| Q01 | My new laptop asks for a key | D1 | overlap |
| Q02 | What does Outlook error 0x800CCC0F mean? | D1 | exact, overlap |
| Q03 | Help desk number? | D1 | retired, short |
| Q04 | Denali display code? | D1 | exact, short |
| Q05 | How long until a replacement YubiKey arrives? | D1 | lost_subject |
| Q06 | If I can't fix a server alert within an hour, what should I do? | D1 | lost_subject, overlap |
| Q07 | It froze again, what now? | D1 | vague, overlap |
| Q08 | How much is the home office equipment allowance? | D2 | long, dense |
| Q09 | How many days a year can I work from another country? | D2 | long, dense, needs_context |
| Q10 | Can I read work mail on my own phone? | D2 | structure, wording |
| Q11 | Can I get money for my chair? | D2 | vague, wording |
| Q12 | Do I need approval to work abroad, and how much is the equipment allowance? | D2 | twopart, long |
| Q13 | What caused the November 3 outage? | D3 | transcript, needs_context |
| Q14 | Who renewed the expired certificate during the outage call? | D3 | transcript, relationship |
| Q15 | What follow-up actions were agreed after the outage? | D3 | transcript, dense |
| Q16 | Which design tool is approved for the marketing team? | D4 | structure, overlap |
| Q17 | Visio access? | D4 | structure, short |
| Q18 | How much RAM does the standard developer laptop have? | D5 | table |
| Q19 | Is the Latitude 5440 still offered? | D5 | table, retired, exact |
| Q20 | Which current laptop model is the cheapest? | D5 | table, needs_context |
| Q21 | The cleanup thing on my laptop: how many days of old files does it keep? | D6 | code, vague |
| Q22 | Which folder does the cleanup script never delete from? | D6 | code |
| Q23 | What was the resolution of ticket INC-20417? | D7 | json, exact |
| Q24 | Which open tickets mention Room Denali? | D7 | json, needs_context, overlap |
| Q25 | Can I install my own browser add-ons? | D8 | faq, wording |
| Q26 | How do I get a second monitor? | D8 | faq, overlap |
| Q27 | How many days of parental leave do I get? | D9 | hr |
| Q28 | How do I claim travel expenses? | D9 | hr, retired |
| Q29 | Who approves my leave, and what is the home office equipment allowance? | D9 and D2 | hr, twopart, multistep |
| Q30 | Who is on call in week 48 for the team that owns the mail servers? | D10 | relationship, multistep |
| Q31 | Who do I escalate to when the Messaging team lead is out? | D10 | relationship, multistep |
| Q32 | What is the Room Fuji display code? | none | unanswerable, exact |
| Q33 | How do I book a flight in the travel portal? | none | unanswerable |
| Q34 | What does a parking permit cost per month? | D1 | unanswerable, partial |
| Q35 | What's the Denali display code, and which projector is in that room? | D1 | partial, twopart |
| Q36 | How often can I claim the equipment allowance? | D2 | lost_subject, long |
| Q37 | On the floor plan, which room is next to the server room? | D11 | image |
| Q38 | What error code is shown in the error screenshot? | D11 | image, exact |
| Q39 | In which month did ticket volume peak? | D11 | image |
| Q40 | Does the equipment allowance cover a standing desk? | D2 | partial |

### Coverage (checked 2026-11-22)

Questions aimed at each step. Every step has at least 3; "all" means the 37 text questions.

| Step | Questions | Step | Questions | Step | Questions |
|---|---|---|---|---|---|
| 02, 03 | all (37) | 10 semantic | 7 | 20 multi-query | 3 |
| 04 fixed-size | 7 | 11 parent-child | 7 | 21 hyde | 3 |
| 05 recursive | 7 | 12 contextual | 3 | 22 decomposition | 3 |
| 06 token | 4 | 13 proposition | 3 | 23 routing | 3 |
| 07 sentence | 3 | 14 scorecard | all (37) | 24 corrective | 5 |
| 08 structure | 3 | 15 hybrid | 6 | 25 self-rag | 3 |
| 09 document-type | 9 | 16 reranking | 7 | 26 adaptive | all (37) |
| 17 metadata | 3 | 18 compression | 7 | 27 agentic | 3 |
| 19 rewriting | 3 | 28 graph | 3 | 29 multimodal | 6 |

Also checked against step 01's knowledge base: every D1 fact the questions rely on appears exactly once; the
chunks holding the answers to Q05 and Q06 do not name their subject ("A replacement token arrives in 2 working
days..." and "If you cannot fix it within an hour..."); "Fuji", "flight", "cost", "projector" and "standing desk"
appear nowhere; no question uses an old topic.

### Checks step 02 runs on the finished files

1. Every evidence sentence appears exactly once in the knowledge base.
2. The evidence for each `long` question starts after character 1,182 of its section.
3. The chunks holding the `lost_subject` answers (Q05, Q06, Q36) do not name their subject.
4. The near twins stay near: Room Everest and Room Denali at least 0.9 similar.
5. The facts the unanswerable and partial questions ask for are absent.
6. No old topic appears in any new document.
7. The transcript has no headings, and every format (Markdown, HTML, table, code, JSON, FAQ, transcript, images) is
   present.
8. Every step keeps at least 3 target questions.

## Models and packages

- **Answers and judge:** `gemini-3.5-flash-lite`. Requests are paced to stay under about 15 a minute.
- **Not on the free tier** (429, limit 0): `gemini-4-neon`, `gemini-3.1-pro-preview`.
- **The key:** `GOOGLE_API_KEY`, set with `setx`; notebooks read it with `os.environ` and it never goes in a file.
- **Packages:** `ragas==0.4.4` with `"instructor>=1.11"` at step 02 (upgrades langchain-core 1.6.6 to 1.8.4, so step
  01 is run once again after), `beautifulsoup4` at step 08 (HTML splitting fails without it), `rank_bm25` at step 15.
  Sentence and semantic chunking are written in plain Python with MiniLM: no NLTK, spaCy or `langchain_experimental`.
- **Kernel:** `simple-rag (Python 3.13)`, the venv at `%USERPROFILE%\venvs\simple-rag`. The system Python fails to load
  the model with a `RecursionError`.
- **RAGAS cache:** RAGAS's disk cache sits outside the repo.

## Optional upgrades

- **A judge that isn't the answer model:** re-test `gemma-4-26b-a4b-it` in step 02 (on 2026-11-22 it returned 504
  "deadline exceeded" and 503 "high demand"). If it passes twice, it becomes the judge: no self-grading, and about
  14,400 requests a day instead of sharing flash-lite's 500.
- **`gemini-3.5-flash`** works on the key, but its daily limit wasn't checked.

## Things to know

- **MiniLM reads only its first 256 tokens,** about 1,182 characters of this IT text. A fact added after that point
  does not change the embedding at all (tested), so anything longer in a chunk is invisible to search. Step 06 shows it.
- **Step 03 may hide retrieval mistakes:** Gemini sees all 3 chunks, so for "My new laptop asks for a key" it may still
  answer from BitLocker, the second chunk. That is why retrieval and answers are scored separately.

## Left out on purpose

- **Late chunking:** it needs a long-context embedding model; MiniLM stops at 256 tokens, so it cannot show the idea.
- **RAGAS-generated test sets as the main yardstick:** a hand-written golden set is cheaper on the free tier and every
  reference answer is known to be right. Step 30 can optionally check the wins on generated questions.
