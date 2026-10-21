# 12 · Tuning (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 12 · Tuning](../../Basic/12-tuning/README.md)

The basic version scores the search on 10 test questions for three chunk sizes and three values of `k`. This version
turns that into the quality system the whole app runs on: a larger labeled set, measures for both retrieval and
answers, every experiment recorded, a gate that stops a change that makes answers worse, and a comparison that shows
what retrieval adds over the model on its own.

---

## 🎯 What This Project Will Do

- **Grow the test set**: questions with their expected articles and key facts, including hard and off-topic ones
- **Measure retrieval and answers** separately, so a drop can be traced to the step that caused it
- **Record every experiment**: its settings, its scores, its cost and its time
- **Gate every change in CI**: a change that lowers quality below the agreed line doesn't get merged
- **Compare against the model alone**: the same questions with and without retrieval
- **Learn from real use**: feedback from the API feeds new test questions

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **A labeled evaluation set** | 50 to 200 questions, each with its expected articles and the facts a good answer contains; paraphrases, typos, multi-article and off-topic questions included | Ten easy questions say little about real users |
| 2 | **Retrieval measures** | Recall@k, MRR and nDCG for each setting | Shows whether the right chunks are being found |
| 3 | **Answer measures** | Faithfulness, answer relevance and context precision (RAGAS-style), scored by an LLM judge and checked against people's ratings on a sample | Shows whether the answers are right and supported, not just the search |
| 4 | **Experiment grid** | Chunk size, overlap, `k`, hybrid weights, re-ranker on or off, and the prompt version, run as a grid | The best combination is found by measuring, with its cost and time next to its score |
| 5 | **Experiment tracking** | Every run stored with its settings, scores, cost and time, and compared in a table or chart | Results can be compared months later, and nothing is lost between runs |
| 6 | **Quality gate in CI** | The evaluation run on every change to the pipeline; the build fails if a score drops below its threshold | A regression is caught before users see it |
| 7 | **Model alone vs RAG** | The same questions answered by the model without retrieval, and with it, scored the same way | Shows, in numbers, what retrieval adds and where it still falls short |
| 8 | **Feedback loop** | Thumbs-down answers from the API reviewed and turned into new labeled questions | The test set grows with the questions real users ask |

---

## 🏗️ Planned Architecture

```text
labeled questions ──→ for each setting in the grid ──→ retrieve ──→ retrieval scores ──┐
       ↑                                                  │                             ├──→ experiment record ──→ compare
       │                                                  └──→ answer ──→ answer scores ┘           │
       │                                                                                            ↓
feedback (👎) ──→ review ──→ new questions                                     CI gate: below threshold → fail the build

model alone ──→ answer ──→ the same answer scores  (the baseline every setting is compared with)
```

---

## ✅ Done When

- An evaluation set of at least 50 labeled questions, versioned with the code
- One command that runs the grid and writes a table of retrieval scores, answer scores, cost and time per setting
- A CI job that fails when a score drops below its threshold, shown working on a deliberately worse setting
- A report comparing the model alone with RAG on the same questions

---

## 📚 Next Steps

This is the last project. Start again from [01 · Read the Knowledge Base (Advanced)](../01-read-the-knowledge-base/README.md),
which is built, and work through the plans in the [roadmap](../README.md).
