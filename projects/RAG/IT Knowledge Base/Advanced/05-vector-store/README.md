# 05 · Vector Store (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 05 · Vector Store](../../Basic/05-vector-store/README.md)

The basic version stores one point per chunk in a Qdrant collection, in memory or in a local Docker server. This
version makes the store safe to write to again and again, fast to filter, and possible to rebuild while the app keeps
answering.

---

## 🎯 What This Project Will Do

- **Write idempotently**: re-running ingestion updates points in place, and removes points for deleted articles
- **Index the labels** that searches filter on, so a filter doesn't slow the search down
- **Store dense and sparse vectors** side by side, ready for hybrid search
- **Check consistency** after every load: points stored, chunks expected, vector sizes, and orphans
- **Rebuild without downtime**: a new collection is filled, checked, then switched in behind an alias

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Idempotent upserts** | Points written by stable chunk ID, so the same chunk always lands on the same point | Re-running ingestion never creates duplicates |
| 2 | **Deletes** | Points removed for chunks whose article was removed or changed, using the manifest from 02 | Old answers don't come back from articles that are gone |
| 3 | **Payload indexes** | Indexes on `system`, `category`, `priority`, `tags` and `doc_id` | Filtered searches stay fast as the collection grows |
| 4 | **Dense + sparse vectors** | A sparse (keyword) vector next to the dense one on each point | Exact terms like error codes are found even when meaning-based search misses them |
| 5 | **Collection aliases** | Build `it_kb_v2` while `it_kb` serves, check it, then move the alias | A full re-index, such as a new embedding model, with no downtime and an instant rollback |
| 6 | **Consistency checks** | Count, vector size, distance and payload checks after each load, in a report | A half-finished load is caught before anyone searches it |
| 7 | **Index tuning** | HNSW settings and quantization chosen and measured | Memory and speed fit the size of the collection |
| 8 | **Server hygiene** | API key, TLS, snapshots and restore tested | The store is secured, and can be recovered |

---

## 🏗️ Planned Architecture

```text
chunks + vectors ──→ upsert by chunk_id ──→ collection it_kb_v2 ──→ consistency checks ──┬──→ pass: move alias it_kb → v2
                         ↑                                                               └──→ fail: keep v1, report why
manifest from 02 ──→ delete removed chunk_ids
```

---

## ✅ Done When

- Tests on in-memory Qdrant: two runs give the same point count; a removed article's points are gone; a filter uses
  its index; an alias switch is atomic
- A deliberately broken load (wrong vector size, missing points) is caught by the checks and leaves the live
  collection untouched
- A report per load: points added, updated, deleted and checked

---

## 📚 Next Steps

**[06 · Retriever (Advanced)](../06-retriever/README.md)**: hybrid search, filters, re-ranking, and measured
retrieval quality.
