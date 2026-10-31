# 05 · Vector Store (Advanced)

Store the chunks' vectors in Qdrant so that writing them again is always safe, filtering on a label stays fast, and
the whole index can be rebuilt while the app keeps answering. Each chunk's point ID comes from its `chunk_id`, so a
re-run updates points instead of adding copies; a changed article's old chunks and a removed article's points are
deleted; every load is checked; and a rebuild fills a new collection behind an alias, moving the alias only when the
new collection passes its checks. Advanced 04's loading, chunking and embedding come first, unchanged. Built with
**Qdrant** (`qdrant-client`, on disk in this process: no server needed) and **LangChain**.

> **Needs:** Python 3.11 or newer and a Gemini API key; or no key, with the stand-in model (Advanced 04).
> **Production version of:** [Basic · 05 · Vector Store](../../Basic/05-vector-store/README.md),
> built on [Advanced · 04](../04-embeddings/README.md).

---

## 🎯 What This Project Does

- **Writes idempotently**: a point's ID is a UUID 5 of its `chunk_id`, so writing a chunk again updates its point;
  two runs never make two points for one chunk
- **Deletes what's gone**: a changed article's chunks that aren't among its new ones (written first, deleted after,
  so the article is never missing), and every point of the articles the manifest lists as removed
- **Keeps the store on disk** (`data/qdrant`), so a run that passes nothing on still leaves every point there; or
  `":memory:"`, or a Qdrant server's URL
- **Stores two vectors per point**: the dense one (the embedding) and a sparse one (the chunk's words, weighed by how
  rare each is), ready for Advanced 06's hybrid search
- **Indexes the labels** searches filter on: `doc_id`, `system`, `category`, `priority`, `tags`, `visibility`, `team`
- **Checks every load**: each article written holds exactly its chunks' points, and the vectors are the right size
  and distance; points of an article no longer in the knowledge base are reported (`--rebuild` clears them)
- **Rebuilds without downtime**: `--rebuild` fills `it_kb_v2` while `it_kb_v1` answers, checks it, then moves the alias
  `it_kb` in one step; a failed check deletes the new collection and leaves the live one untouched
- **Rolls back in one step**: `--rollback` moves the alias back to the collection before
- **Refuses to mix models**: vectors of another size than the collection's stop the run, before anything is written

**Try it:** run `python pipeline.py`, then `--data-path data/sample_it_kb_next.csv`, then `--rebuild`, then
`--rollback`, and read each run's "Vector store" lines.

---

## 🏗️ Architecture

```text
pipeline.py
   ├─ settings, the store (make_store), then the embedder and its key
   ├─ KBLoader → Manifest.compare → KBTextSplitter → ChunkEmbedder      Advanced 04: chunks and vectors
   │
   ├─ KBVectorStore.write(chunks, vectors, removed=..., current=...)    (or rebuild())
   │     ensure()              the alias it_kb → it_kb_v1, made on the first load:
   │                             dense vector (768, cosine) + sparse vector (IDF), a payload index per label
   │     the size check        the collection's vectors the model's size, or nothing is written
   │     upsert                point ID = UUID 5 of chunk_id; payload = {"page_content", "metadata"}
   │     delete                each changed article's old chunks; every point of the removed articles
   │     check                 each article written holds exactly its chunks; the vectors' size and distance
   │     orphans               points of articles no longer in the knowledge base: reported
   │
   │  rebuild():  it_kb_v2 made and filled ─→ checks ─┬─ pass: alias it_kb → it_kb_v2 (v1 kept for rollback)
   │                                                  └─ fail: it_kb_v2 deleted; it_kb still → it_kb_v1
   │
   └─ Manifest.write()           only now, once every step has succeeded
```

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- **A Gemini API key**, or `provider = "fake"` in `kb_settings.toml`'s `[embeddings]` (Advanced 04)
- **No Qdrant server**: Qdrant runs in this process and keeps its data in `data/qdrant`. To use a server instead, set
  `location` to its URL, and `QDRANT_API_KEY` in `.env` if it has one

---

## 🚀 Quick Start

Steps 1 to 4 are Advanced 04's: go to `projects/RAG/IT Knowledge Base/Advanced/05-vector-store`, make and activate
a venv, `pip install -r requirements-dev.txt`, and copy `.env.example` to `.env` with your key in it.

### Step 5: Run It

```bash
python pipeline.py
```

After the chunks and vectors (Advanced 04), the output says where the points went. These runs are with the stand-in
model (`provider = "fake"`); with Gemini, only the model's name and the vectors' numbers differ:

```text
Vector store: it_kb -> it_kb_v1, Qdrant on disk, in data/qdrant
  39 points written: 39 added, 0 updated; 0 deleted (0 old chunks of changed articles, 0 of removed articles); 39 points in all
  Checks: passed
```

Run it again: nothing changed, so nothing is written, and the 39 points are still there.

```text
  0 points written: 0 added, 0 updated; 0 deleted (0 old chunks of changed articles, 0 of removed articles); 39 points in all
```

Read the next export: VPN's fix was edited (its new chunk added, its old one deleted), the laptop article's priority
changed (its 4 points updated with the new label), the printer article is gone (its 4 points deleted), and a new
article came (3 points added):

```bash
python pipeline.py --data-path data/sample_it_kb_next.csv
```

```text
  10 points written: 4 added, 6 updated; 5 deleted (1 old chunk of changed articles, 4 of removed articles); 38 points in all
  Checks: passed
```

Rebuild everything into a new collection, then go back:

```bash
python pipeline.py --rebuild --data-path data/sample_it_kb_next.csv
python pipeline.py --rollback
```

```text
Vector store: it_kb -> it_kb_v2 (rebuilt; it_kb_v1 kept for rollback), Qdrant on disk, in data/qdrant
  38 points written: 38 added, 0 updated; 0 deleted (0 old chunks of changed articles, 0 of removed articles); 38 points in all
  Checks: passed

The alias it_kb now points at it_kb_v1. Its points may be older than the manifest: run with --full next, to write every article into it.
```

The log (stderr) adds a line per load: `INFO Stored: 4 added, 6 updated, 5 deleted; 38 points in it_kb_v1`.

---

## 📁 Project Structure

```text
05-vector-store/
├── pipeline.py                   # main(): settings, store, key, load, compare, chunk, embed, store, manifest, print
├── vector_store.py               # KBVectorStore, StoreReport, point_id(), sparse_vector(), make_client(); defaults
├── embedding.py, config.py       # Advanced/04's (config.py now also reads QDRANT_API_KEY, for a server)
├── chunking.py, knowledge_base_loader.py, article.py, settings.py, manifest.py, sensitive_data.py, utils.py
├── kb_settings.toml              # ..., [embeddings], and now [vectorstore]
├── .env.example                  # GOOGLE_API_KEY, and QDRANT_API_KEY for a server
├── data/
│   ├── the data files of Advanced/04
│   └── manifest.json, embedding_cache.sqlite3, qdrant/   # written by each run (not in git)
├── tests/
│   ├── test_vector_store.py      # on Qdrant in memory: writes, deletes, filters, sparse, checks, rebuild, rollback
│   ├── test_pipeline.py          # the steps as the script runs them: the next export, rebuild, rollback, sizes
│   └── the tests of Advanced/04, and fakes.py, conftest.py
├── requirements.txt              # Advanced/04's, + qdrant-client
└── requirements-dev.txt, pytest.ini, .gitignore (+ data/qdrant/)
```

---

## 🔧 Configuration

### `[vectorstore]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `location` | `"data/qdrant"` | a folder (from the settings file's folder), `":memory:"`, or a server's `http(s)://` URL |
| `alias` | `"it_kb"` | the name searches use; the collections behind it are `it_kb_v1`, `it_kb_v2`, ... |
| `hnsw_m` | 16 | HNSW's links per point (a server uses it; Qdrant in a process ignores it) |
| `hnsw_ef_construct` | 100 | how hard HNSW looks while it builds (the same) |

A server's API key is `QDRANT_API_KEY` in `.env` or the environment, never a setting: a key in `kb_settings.toml`
stops the run.

### Command-Line Options

Advanced 04's, plus (only one of `--full`, `--rebuild` and `--rollback` at a time):

| Option | What it does |
|---|---|
| `--rebuild` | every article, into a new collection; the alias moves to it only if it passes its checks |
| `--rollback` | the alias back to the collection before; nothing else is done |

---

## 🧪 Testing

```bash
python -m pytest        # 226 passed  (add -v for one line per test)
```

- **The collection**: made behind the alias on the first load, with both vectors; a payload index per label; the
  payload in LangChain's layout, read back by LangChain's `QdrantVectorStore`
- **Writes and deletes**: the same chunks twice keep one point each; a point ID from its chunk_id; a changed article
  loses its old chunks' points; a removed article loses all of them; a wrong vector size writes nothing; a collection
  of another size stops the write and says to rebuild
- **Searching**: a filter finds only its label's points; the sparse vector finds an exact word (`0x80070005`)
- **Checks**: an article missing a point is found; orphans are reported, not deleted
- **Rebuild and rollback**: a new collection, then the alias; a broken rebuild (a point dropped on the way) leaves the
  live collection and the alias untouched; a third rebuild deletes the oldest; rollback goes back, and says when it
  can't
- **The pipeline**, with the stand-in model and Qdrant on disk in a temporary folder: run twice, the next export's
  counts, rebuild then rollback, options that can't be combined, a model of another size

No key and no network: Qdrant runs in the test's process.

---

## 🎓 Key Concepts Demonstrated

### 1. Idempotent Writes: The Same Input, the Same Store

```python
models.PointStruct(id=point_id(chunk.metadata["chunk_id"]), ...)     # vector_store.py, _write_to()
```

`uuid5(namespace, chunk_id)` gives the same ID every time, so `upsert` overwrites instead of adding. A run that fails
halfway can simply be run again.

### 2. Write First, Delete After

A changed article's new chunks are written before its old ones are deleted, so a search never finds the article
missing; the old ones are found with a filter: this article's points, but not the ones just written.

### 3. Only the Manifest Deletes an Article

Points of an article missing from this run might belong to a row that only failed a check today. So the store deletes
an article's points only when the manifest lists it as removed, or on a rebuild; anything else is reported as an
orphan.

### 4. Blue-Green Rebuilds Behind an Alias

Searches use the alias `it_kb`, never a collection's own name. A rebuild fills `it_kb_v2` while `it_kb_v1` answers,
checks it, then moves the alias in one operation; the old collection stays, so a rollback is one step too. A new
embedding model means a rebuild: the vectors' size is checked on every write, so two models' vectors never mix.

### 5. Dense and Sparse, Side by Side

The dense vector finds chunks that mean the same thing; the sparse one finds chunks with the same rare words, such as
an error code. Each word's index is a CRC-32 of it, the same on every machine, and the collection weighs it by how
rare it is (IDF).

### 6. Index What You Filter On

A filter on an unindexed label makes a server look at every point. A payload index per label keeps filtered searches
fast as the collection grows. (Qdrant in a process keeps no indexes, and says so in the log; a filter still works.)

---

## 🛠️ Troubleshooting

**Issue**: `ERROR it_kb_v1 holds vectors of 768 numbers, but the embedding model makes 256: nothing written. Run with --rebuild ...`
**Fix**: The embedding model or its size changed. `python pipeline.py --rebuild` makes a new collection at the new size.

**Issue**: `WARNING 1 article not in the knowledge base still has points: run with --rebuild to clear them`
**Fix**: An earlier run failed after writing, or ran with `--full`, which doesn't read the manifest. `--rebuild`
writes a clean collection.

**Issue**: `ERROR The checks on it_kb_v1 failed: article kb-... holds 2 points, not its 3 chunks`
**Fix**: A write didn't land. The manifest wasn't saved, so the next run writes the same articles again.

**Issue**: `ERROR Qdrant's folder <this folder>/data/qdrant is open in another process (...). Close that one, or use a Qdrant server`
**Fix**: Another run, or a Python session, has the store open. Qdrant in a process allows one client at a time; close
the other one, or use a Qdrant server.

**Issue**: `ERROR There's no collection before it_kb_v1 to go back to`
**Fix**: Nothing was rebuilt yet, so there's nothing to roll back to.

---

## 📚 Next Steps

**[06 · Retriever (Advanced)](../06-retriever/README.md)**: hybrid search over the dense and sparse vectors, filters,
re-ranking, and retrieval measured on a labeled set.

### Ideas to Try

- Run Qdrant in Docker (`docker run -p 6333:6333 qdrant/qdrant`), set `location = "http://localhost:6333"`, and run
  `--rebuild`: the payload indexes are kept there.
- After `--rebuild`, run `--rollback`, then `--full`: every article is written into the old collection again.
- Snapshots and restore (`client.create_snapshot()`) need a server: try them with the Docker one.
