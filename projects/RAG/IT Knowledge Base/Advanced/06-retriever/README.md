# 06 · Retriever (Advanced)

Find the chunks that answer a question more often, know when nothing in the knowledge base does, and prove it with
numbers. The retriever searches two ways, by meaning (the dense vector) and by exact words (the sparse vector), and
fuses the lists; reads label filters from the question ("VPN problems with High priority"); can re-rank the
candidates; keeps the results varied; says "no match" below a threshold tuned on a labeled set; and caches question
vectors. `evaluation.py` measures every variant on 52 labeled questions. Advanced 05's pipeline comes first,
unchanged. Built with **LangChain** (a `BaseRetriever` subclass) and **Qdrant**.

> **Needs:** Python 3.11 or newer and a Gemini API key; or no key, with the stand-in model (Advanced 04), whose dense
> numbers mean nothing.
> **Production version of:** [Basic · 06 · Retriever](../../Basic/06-retriever/README.md),
> built on [Advanced · 05](../05-vector-store/README.md).

---

## 🎯 What This Project Does

- **Hybrid search**: a dense search and a sparse one, 20 candidates each, merged by reciprocal rank fusion (RRF): a
  question with an error code finds its article even when meaning alone misses it
- **Filters from the question**: a system named in it ("Wi-Fi", "Active Directory", any spelling in
  `kb_settings.toml`) and a priority next to the word "priority"; or filters the caller passes
- **"No match"**: when even the best candidate's similarity is below `min_score`, no chunks, rather than the
  least-bad ones
- **Re-ranking**: by a cross-encoder model (optional: it needs `sentence-transformers`), or by shared rare words (no
  model), or not at all
- **Variety**: at most 2 chunks from one article, picked by maximal marginal relevance (MMR)
- **A question cache**: a repeated question's vector comes from the cache, with no call
- **A rewriting hook**: a function that turns a question into others (multi-query); each is searched, all are
  fused. Writing them takes a chat model, which comes in Advanced 07, so here it's only a hook, tested with a stand-in
- **Measured, not guessed**: `evaluation.py` gives Recall@5, MRR and nDCG@5 for dense, sparse, hybrid and hybrid with
  re-ranking side by side, counts the no-match decisions, and prints the threshold that gets the most right

**Try it:** `python pipeline.py --question "VPN problems with High priority"`, then `python evaluation.py`.

---

## 🏗️ Architecture

```text
question ──→ clean_question()          spaces made single, "???" made "?"
         ──→ read_filters()            system = VPN, priority = High   (or the caller's filters)
         ──→ for the question, and each rewrite (if a rewriter is passed in):
               dense search (its vector: from the question cache, or the model) ─┐   20 candidates each,
               sparse search (its words, weighed by IDF)                         ─┤   filtered on the labels
                                                                                  ↓
             fuse (RRF: 1 / (60 + rank) in each list) ──→ best similarity < min_score? ──→ "no match"
                                                                  │ no
                                                                  ↓
                                         re-rank (if a re-ranker is set) ──→ pick 5: MMR, ≤ 2 per article
                                                                  ↓
                                        the chunks, each with score_dense, score_sparse, score_fused, score_rerank
```

`wiring.py` is now the one place where settings become parts: `pipeline.py` and `evaluation.py` both build the
embedder, the store and the retriever there.

---

## 📋 Prerequisites

- **Python 3.11 or newer**, and a Gemini API key, as in Advanced 04 (or `provider = "fake"`)
- **Optional**: `pip install sentence-transformers` for the cross-encoder re-ranker (it brings PyTorch and downloads
  `cross-encoder/ms-marco-MiniLM-L-6-v2` the first time)

---

## 🚀 Quick Start

Steps 1 to 4 are Advanced 04's: go to `projects/RAG/IT Knowledge Base/Advanced/06-retriever`, make and activate a
venv, `pip install -r requirements-dev.txt`, and copy `.env.example` to `.env` with your key in it.

### Step 5: Run the Pipeline, With Questions

```bash
python pipeline.py --question "I get error 0x80070005 when I reset my password" \
                   --question "VPN problems with High priority" --question "vpn  wont connect from home???"
```

After the store (Advanced 05), each question's chunks. This run is with the stand-in model, so the dense scores are
noise; the sparse ones are real:

```text
Retrieval: hybrid, the best 5 chunks, at most 2 from an article; no match below a similarity of -1.0
  Question: I get error 0x80070005 when I reset my password
    filters read from it: none
    5 chunks of 26 candidates:
      1. Password Reset Failed, resolution  (dense 0.001  sparse 6.354)
      2. Printer Not Found, resolution  (dense 0.007  sparse 1.984)
      3. VPN Connection Timeout, problem  (dense -0.003  sparse 2.773)
      4. Microsoft Teams Audio Issues, notes  (dense 0.067)
      5. Password Reset Failed, problem  (sparse 13.095)
  Question: VPN problems with High priority
    filters read from it: system = VPN, priority = High
    2 chunks of 3 candidates:
      1. VPN Connection Timeout, resolution  (dense 0.025  sparse 9.921)
      2. VPN Connection Timeout, notes  (dense 0.008  sparse 1.984)
  Question: vpn wont connect from home?
    filters read from it: system = VPN
    2 chunks of 3 candidates:
      1. VPN Connection Timeout, problem  (dense 0.086  sparse 9.236)
      2. VPN Connection Timeout, resolution  (dense 0.077  sparse 9.921)
```

The filtered questions search only the VPN article's 3 chunks, and return 2: at most 2 from one article.

### Step 6: Measure It

```bash
python evaluation.py
```

```text
Retrieval on 52 labeled questions (44 answered by an article, 8 off-topic), k = 5, by fake/gemini-embedding-001
  variant                       Recall@5    MRR  nDCG@5   no match: right  wrong
  dense                             0.80   0.70    0.70          0 of 8         0
  sparse                            1.00   0.94    0.92          2 of 8         0
  hybrid                            0.93   0.89    0.85          0 of 8         0
  hybrid + word-overlap             1.00   0.97    0.95          0 of 8         0
The no-match threshold that gets the most decisions right on this set: min_score = -0.0272 (dense similarity), 44 of 52 right
The stand-in model's vectors mean nothing: the dense and hybrid numbers, and the threshold, are noise here. The sparse numbers are real. Run with Gemini for the others.
```

The sparse search needs no model, so its row is real: on these 10 articles, exact words find the right article
among the 5 chunks for every answerable question, and first for most of them (MRR 0.94). The other rows, and the threshold, need Gemini's vectors: run it with
your key (52 question embeddings, cached after the first run), then put the printed `min_score` in `[retrieval]`.
The 2 off-topic questions sparse gets right share no word with any chunk; the rest need the threshold.

---

## 📁 Project Structure

```text
06-retriever/
├── pipeline.py                   # Advanced/05's steps, then each --question searched and printed
├── retriever.py                  # KBRetriever (BaseRetriever), clean_question(), read_filters(), the re-rankers
├── evaluation.py                 # the labeled set, Recall@k, MRR, nDCG, the variants, tune_threshold(); main()
├── wiring.py                     # the parts built from kb_settings.toml: embedder, store, re-ranker, retriever
├── vector_store.py, embedding.py, config.py, chunking.py, knowledge_base_loader.py, article.py, settings.py,
│   manifest.py, sensitive_data.py, utils.py
├── kb_settings.toml              # ..., [vectorstore], and now [retrieval]
├── data/
│   ├── eval_questions.csv        # 52 questions: 44 with the article that answers each, 8 off-topic
│   └── the data files of Advanced/05
├── tests/
│   ├── test_retriever.py         # cleaning, filters, hybrid, dense, sparse, no match, variety, re-ranking, cache
│   ├── test_evaluation.py        # the labeled set, the scores by hand, the threshold, the script's sparse numbers
│   ├── support.py                # shared: the sample's chunks, a stand-in settings file, a keyword retriever
│   ├── fakes.py                  # + KeywordEmbeddings: a stand-in whose vectors mean something
│   └── the tests of Advanced/05
└── requirements.txt, requirements-dev.txt, pytest.ini, .gitignore, .env.example
```

---

## 🔧 Configuration

### `[retrieval]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `mode` | `"hybrid"` | `"dense"`, `"sparse"` or `"hybrid"` |
| `k` | 5 | chunks returned |
| `candidates` | 20 | chunks each search finds, for fusing and re-ranking (at least `k`) |
| `rrf_k` | 60 | RRF's constant |
| `min_score` | -1.0 | below this dense similarity, "no match"; -1 never says it: tune it with `evaluation.py` |
| `max_per_article` | 2 | chunks from one article, at most |
| `mmr_lambda` | 0.7 | 1: by relevance only; lower: more variety |
| `read_filters` | `true` | filter on a system, or a priority, named in the question |
| `reranker` | `"none"` | `"none"`, `"word-overlap"` or `"cross-encoder"` |
| `cross_encoder_model` | `"cross-encoder/ms-marco-MiniLM-L-6-v2"` | the cross-encoder's model |

### Command-Line Options

`pipeline.py`: Advanced 05's, plus `--question "..."`, as many as you like (default: one about VPN).
`evaluation.py`: `--settings`, `--questions` (default `data/eval_questions.csv`), `--k`.

---

## 🧪 Testing

```bash
python -m pytest        # 261 passed  (add -v for one line per test)
```

- **The retriever**, on Qdrant in memory with a keyword stand-in model whose vectors mean something: the question
  cleaned; filters read (two systems named: none used; "high" without "priority": none; categories never); a filter
  keeping the search to its label; filters passed in; hybrid finding an error code dense misses; dense alone; sparse
  making no call; an off-topic question's "no match" below the threshold; no more chunks from one article than
  allowed; a re-ranker reordering; the word-overlap scores; the cross-encoder saying how to install it; a repeated
  question's vector from the cache; rewrites searched and fused; LangChain's `invoke()`
- **The evaluation**: the labeled set (every article answered); the scores worked out by hand; the threshold; a
  variant measured; the script after the pipeline, whose sparse row is checked to the number
- **Advanced 05's tests**, and the pipeline's retrieval step

No key and no network.

---

## 📊 Understanding the Output

| Score | What it measures |
|---|---|
| Recall@5 | the share of answerable questions whose article is among the 5 chunks |
| MRR | the mean of 1 / the rank of the article's first chunk (1: always first; 0.5: second) |
| nDCG@5 | each of the article's chunks counted by its rank, against the best order possible |
| no match: right | off-topic questions that got "no match" |
| no match: wrong | answerable questions that got "no match": each one a question the app would refuse |

| A chunk's scores | What it is |
|---|---|
| `score_dense` | its cosine similarity to the question (none if the dense search didn't find it) |
| `score_sparse` | its shared words with the question, weighed by IDF (none if the sparse search didn't) |
| `score_fused` | its RRF score: 1 / (60 + rank), summed over the lists it's in |
| `score_rerank` | the re-ranker's score, when one is set |

---

## 🎓 Key Concepts Demonstrated

### 1. Two Searches Miss Different Things

Meaning-based search finds "my wireless keeps dropping" for an article about WiFi disconnections; it can miss
`0x80070005`, which is a string, not a meaning. Word-based search is the opposite. RRF merges the two by rank, so
neither's scores need to be comparable.

### 2. Measure Every Change

```python
scores, best = evaluate(retriever, questions, name="hybrid", ids=ids, chunks_of=chunks_of, k=5)
```

A labeled set turns "this seems better" into a number. Each variant is the same `KBRetriever` with a different
setting, so the comparison is fair, and the threshold is chosen on data, not guessed.

### 3. Knowing When Not to Answer

An off-topic question still has a nearest chunk. A threshold on the best similarity turns "the least-bad chunk" into
an honest "no match", which Advanced 07 turns into "I don't know".

### 4. Filters From the Question, Carefully

"VPN problems with High priority" means a filter, not just words. Reading it from the question with the spellings
tables costs nothing, but a wrong filter hides the right article; so a system is used only when exactly one is named,
a priority only next to "priority", and never a category ("network" is too common a word).

### 5. Parts In, One Class

The re-ranker, the rewriter, the cache and the model are passed in; the dense-only, sparse-only and hybrid variants
are one class with a different `mode`. A fix is made once, and the variants can't drift apart.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR There's no collection to measure yet: run python pipeline.py first`
**Fix**: `evaluation.py` searches the store; run the pipeline once to fill it.

**Issue**: `ERROR The cross-encoder re-ranker needs sentence-transformers: pip install sentence-transformers, ...`
**Fix**: Install it, or set `reranker = "word-overlap"` or `"none"`.

**Issue**: Every off-topic question still gets chunks
**Fix**: `min_score` is -1 (never "no match"). Run `python evaluation.py` with Gemini and set `min_score` to the
threshold it prints.

**Issue**: A question returns fewer than 5 chunks
**Fix**: A filter read from it narrowed the search to one article, and at most `max_per_article` chunks come from
one article. Pass `filters={}` to `search()`, or set `read_filters = false`.

---

## 📚 Next Steps

**[07 · Grounded Answer (Advanced)](../07-grounded-answer/README.md)**: answers with checked citations, "I don't know"
when the context doesn't cover the question, and defenses against injected instructions.

### Ideas to Try

- Run `evaluation.py` with Gemini, then with `reranker = "word-overlap"`, then the cross-encoder: which helps most?
- Add 10 questions of your own to `data/eval_questions.csv`, some with typos, and measure again.
- Set `max_per_article = 1` and compare nDCG.
