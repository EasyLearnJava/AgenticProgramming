# 03 · Chunking (Advanced)

> **Status:** 📝 Planned: this README is the plan; there's no code yet.
> **Production version of:** [Basic · 03 · Chunking](../../Basic/03-chunking/README.md)

The basic version cuts each article into chunks of at most 512 characters with `RecursiveCharacterTextSplitter`.
This version cuts where the article's meaning changes, sizes chunks the way the embedding model counts them, and
gives every chunk an identity: a stable ID, a link back to its article, and the section it came from.

---

## 🎯 What This Project Will Do

- **Cut along the article's structure**: a chunk never mixes the end of the problem with the start of the fix
- **Size chunks in tokens**, the unit the embedding model counts, with a hard ceiling below its limit
- **Give each chunk context**: its article's title at the top, its section, its position, and its parent's ID
- **Give each chunk a stable ID** made from its article and content, so re-chunking an unchanged article gives the
  same IDs
- **Check every chunk**: too small, too large, duplicated, or empty after cleaning, each reported

---

## 🗺️ Roadmap

| # | Concept | What it adds | Why it matters in production |
|---|---|---|---|
| 1 | **Structure-aware splitting** | Split on the article's sections (Problem, Resolution, Notes) first, and only then by size | A chunk that answers "how do I fix it" holds the whole fix, not half of it and half of the symptom |
| 2 | **Token-based sizing** | Chunk size and overlap counted in tokens, with the embedding model's limit as a ceiling | No chunk is silently cut off by the model; costs can be predicted |
| 3 | **Contextual headers** | The title (and section) written at the top of each chunk's text | A chunk like "Restart the service" still says which service, which helps search |
| 4 | **Chunk metadata** | `chunk_id`, `doc_id`, `section`, `position`, `token_count` | Every chunk leads back to its article and place, for citations and debugging |
| 5 | **Parent-child retrieval** | Small chunks for searching, linked to the whole section or article for answering | Precise search, with enough context for a full answer |
| 6 | **Semantic chunking (optional)** | Breakpoints where the meaning shifts, found with embeddings, compared against the structural split | Long free-text articles without clear sections still split well |
| 7 | **Quality checks** | Tiny fragments merged, oversize chunks split again, duplicate chunks removed, all reported | No near-empty or repeated chunks in the index |

---

## 🏗️ Planned Architecture

```text
Document ──→ split by section ──→ size in tokens ──→ add title/section header ──→ chunk_id + metadata
                                         │                                              │
                                         ↓                                              ↓
                              too small → merge / too big → split again        quality checks ──→ report
                                                                                        │
                                                                                        ↓
                                                                        chunks (children) + their parents
```

---

## ✅ Done When

- Articles with clear sections, a very long fix, a one-line note and a duplicated paragraph, each in a test file
- Tests that no chunk crosses a section boundary, none exceeds the token ceiling, and IDs are stable across runs
- A report of chunks merged, split again or removed, and why

---

## 📚 Next Steps

**[04 · Embeddings (Advanced)](../04-embeddings/README.md)**: batching, retries, a cache, and cost tracking for
turning chunks into vectors.
