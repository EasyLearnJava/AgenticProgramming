# 06 · Retriever (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 06 · Retriever](../../Basic/06-retriever/README.md)

The basic version embeds the question and returns the 5 closest chunks. This version finds the right chunks more
often, knows when nothing in the knowledge base matches, and measures how well it does on a labeled set of
questions.

---

## 🎯 What This Project Will Do

- **Search two ways and combine them**: meaning (dense vectors) and exact words (sparse vectors), merged by rank
- **Filter by labels** such as system or priority, set by the caller or read from the question
- **Re-rank** the candidates with a model that reads the question and each chunk together
- **Say when nothing matches**: below a score threshold, return no chunks rather than the least-bad ones
- **Measure itself**: recall, rank and precision on a labeled question set, every time it changes

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Hybrid search** | Dense and sparse results merged with reciprocal rank fusion | Questions with error codes, product names or exact phrases are found as well as paraphrased ones |
| 2 | **Metadata filters** | Filters on system, category, priority and tags, passed in or extracted from the question (self-query) | "VPN problems with High priority" searches only those articles |
| 3 | **Re-ranking** | A cross-encoder (or a model call) re-orders the top 20 candidates; the best 5 are kept | The best chunk is first more often, so the answer is better |
| 4 | **Diversity (MMR)** | Near-identical chunks from one article are not all returned at once | The context covers more of what could answer the question |
| 5 | **No-match threshold** | A minimum score, tuned on the labeled set; below it, an explicit "no match" | Off-topic questions don't get answers built on unrelated articles |
| 6 | **Query rewriting** | Multi-query or HyDE for short, vague questions, and cleanup of typos and filler | "vpn wont work???" finds the VPN article |
| 7 | **Retrieval evaluation** | Recall@k, MRR and nDCG on a labeled set of questions and their articles | Every change is measured, not guessed |
| 8 | **Query cache** | Question embeddings cached for repeated questions | Common questions cost one embedding call, once |

---

## 🏗️ Planned Architecture

```text
question ──→ clean / rewrite ──→ filters? ──┬──→ dense search ──┐
                                            └──→ sparse search ─┴──→ fuse (RRF) ──→ re-rank top 20 ──→ MMR
                                                                                          │
                                                                    score ≥ threshold? ───┤
                                                                       yes ↓              ↓ no
                                                                   top 5 chunks      "no match"
```

---

## ✅ Done When

- A labeled set of at least 50 questions, each with the article that answers it, including off-topic ones that
  should match nothing
- Recall@5, MRR and nDCG reported for dense only, hybrid, and hybrid + re-ranking, side by side
- Tests for filters, the threshold, and that off-topic questions return "no match"

---

## 📚 Next Steps

**[07 · Grounded Answer (Advanced)](../07-grounded-answer/README.md)**: answers with checked citations, refusals,
and defenses against injected instructions.
