# 03 · Chunking (Advanced)

Cut the IT knowledge base's articles into chunks for search: along each article's sections first, so a chunk never
mixes the end of the problem with the start of the fix, then by size, counted in tokens, the unit the embedding
model counts. Every chunk starts with its article's title and its section, has an ID that stays the same on every
run, and points to its parent: the whole section, kept for answering. Advanced 02's loading comes first, unchanged:
only the articles added or changed since the last run are cut. Built with **LangChain** (a `TextSplitter` subclass),
**Pydantic** and the Python standard library.

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads local files.
> **Production version of:** [Basic · 03 · Chunking](../../Basic/03-chunking/README.md),
> built on [Advanced · 02](../02-documents-and-metadata/README.md).

---

## 🎯 What This Project Does

- **Cuts along the article's structure**: Problem, Resolution and Notes are each cut on their own; no chunk crosses
  from one into another
- **Sizes chunks in tokens**: at most 128 each, the header included, packed from whole sentences (a numbered step
  such as "1. Verify..." is one sentence), with a hard ceiling of 512, a quarter of `gemini-embedding-001`'s
  2,048-token limit
- **Writes a header on every chunk**: the article's title and the section, so "Restart the service" still says
  which service
- **Gives every chunk an identity**: `chunk_id` (from its article, its section and a hash of its text), `section`,
  `position`, `token_count` and `parent_id`, on top of its article's labels and provenance
- **Keeps each section whole as a parent**: small chunks to search, the whole section to answer from
- **Checks every chunk**: a paragraph repeated in the article is removed, a fragment at a section's end is merged
  into the chunk before it, a run with no spaces (a log line, a fingerprint) is cut to fit; each one reported
- **Runs the steps as a pipeline**: `pipeline.py` loads (Advanced 02's checks), compares with the last run, cuts
  the articles passed on, and saves the manifest only when every step has succeeded

**Try it:** `python pipeline.py --data-path data/sample_it_kb_chunking.csv --full`, one article for each chunking
case, and read the chunk checks at the end.

---

## 🏗️ Architecture

```text
pipeline.py
   │
   ├─ load_settings()           kb_settings.toml: columns, spellings, and now [chunking]: the sizes in tokens
   ├─ KBLoader.load()           Advanced 02: rows checked, redacted, spelled one way, schema, IDs, provenance
   ├─ Manifest.compare()        Advanced 02: only the articles added or changed are passed on
   │
   ├─ KBTextSplitter.split_documents(passed on)          ← a LangChain TextSplitter
   │     for each article:
   │       _sections()          "Title: …", "Problem: …", "Resolution: …", "Notes: …" → title + sections
   │       for each section:
   │         repeated paragraphs removed                 → report.removed
   │         the whole section kept                      → splitter.parents[parent_id]
   │         _pack()            whole sentences into chunks of ≤ 128 tokens (header included), overlap ≤ 16
   │           ├─ a run with no spaces cut to fit       → report.cut
   │           └─ a last fragment < 8 tokens merged     → report.merged
   │         each chunk: header + body, chunk_id, section, position, token_count, parent_id
   │
   └─ Manifest.write()          saved last, once every step has succeeded
```

### The Pipeline in This Project

1. **Settings** → `kb_settings.toml`, checked, now with the chunk sizes
2. **Load and compare** → Advanced 02, unchanged: the Documents passed on are the added and changed articles
3. **Find the sections** → the title goes into every header; Problem, Resolution and Notes are each cut alone
4. **Remove repeats** → a paragraph already earlier in the article
5. **Pack** → whole sentences into chunks up to the size, a little overlap when sentences are short
6. **Check** → a fragment merged, a run with no spaces cut, a chunk the same as one before it removed
7. **Save the manifest** → only now, so a run that fails while cutting is run again in full
8. **Print** → the articles passed on, each chunk, the first two in full, the data checks, the chunk checks, the changes

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: once the packages are installed, it runs without a network

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Advanced/03-chunking"   # from the repo root; quotes for the spaces
```

### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: langchain-core, langchain-text-splitters, pydantic and pytest
```

### Step 4: Run It

```bash
python pipeline.py
```

The first run passes on all 10 articles and cuts them into 39 chunks (the log, on stderr, says so too):

```text
Documents passed on to the next step: 10
  kb-4c38012d03ec9cc2  VPN Connection Timeout
  ...

Chunks: 39 from 10 articles, 25 to 127 tokens each (ceiling 512); 30 parent sections kept whole
  kb-4c38012d03ec9cc2:problem:92c1daea   37 tokens  Problem: Users experience timeout errors when attempting ...
  kb-4c38012d03ec9cc2:resolution:9e9b2077  103 tokens  Resolution: 1. Verify internet connection stability. 2. C...
  kb-4c38012d03ec9cc2:notes:eea72f42   39 tokens  Notes: Common issue during peak hours especially for user...
  ...

Chunk 1 of 39
Text (page_content):
VPN Connection Timeout
Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Its own metadata (and its article's labels and provenance, as in Advanced/02):
  chunk_id: kb-4c38012d03ec9cc2:problem:92c1daea
  doc_id: kb-4c38012d03ec9cc2
  section: problem
  position: 0
  token_count: 37
  parent_id: kb-4c38012d03ec9cc2:problem
```

and ends with the checks and the changes:

```text
Data checks: 10 rows read, 10 kept (4 blank lines ignored)
Nothing skipped, removed, normalized, redacted or flagged.

Chunk checks: 10 articles cut into 39 chunks
Nothing merged, cut again or removed.

Changes: no earlier run to compare with, so all 10 articles are new
```

Run it again and nothing is cut: nothing changed. Read the next export, `data/sample_it_kb_next.csv`, and only its 3
added or changed articles are cut, into 10 chunks.

### The Chunking File: Each Check at Work

```bash
python pipeline.py --data-path data/sample_it_kb_chunking.csv --full
```

Six articles: one with clear sections, one with a 14-step fix, one with a one-line note, one with repeated
paragraphs, one whose note holds a 1,280-character fingerprint with no spaces, and one whose last step would be a
fragment:

```text
Chunk checks: 6 articles cut into 22 chunks

Removed: repeated in the article (2)
  kb-535f693c2bede3c1 resolution (Disk Space Low): a paragraph already in resolution: "Delete the files in C:\Windows\Temp and empty t..."
  kb-535f693c2bede3c1 notes (Disk Space Low): a paragraph already in resolution: "Move the user's Downloads folder to OneDrive an..."

Merged: a fragment joined to the chunk before it (1)
  kb-7f11fa328f9c5921 resolution (Phone Enrolment Fails): a 4-token piece merged into the chunk before it

Cut again: a piece with no spaces, too big for a chunk (1)
  kb-aa0ca0c1f475dcd2 notes (Certificate Error on Intranet): a 320-token piece with no spaces cut into 3 pieces
```

The 14-step fix becomes four chunks that start at steps 1, 5, 9 and 13: no step is cut in two. The one-line note is a
chunk of its own, `Printer Offline After Move` / `Notes: After moves.`: its header gives it the context it lacks.

---

## 📁 Project Structure

```text
03-chunking/
├── pipeline.py                   # main(): the steps in order, the manifest saved last, then the output
├── chunking.py                   # KBTextSplitter (TextSplitter), ChunkReport; the sizes' defaults
├── knowledge_base_loader.py      # KBLoader, as in Advanced/02 (its entry point is pipeline.py now)
├── article.py                    # the schema, the spellings, doc_id(): Advanced/02's
├── settings.py                   # KBSettings, and now ChunkingSettings: kb_settings.toml, checked
├── manifest.py                   # what changed since the last run: Advanced/02's
├── sensitive_data.py             # redact(): Advanced/01's
├── utils.py                      # helpers: hashes, simplify(), spelling_key(), count_tokens(), the print_* functions
├── kb_settings.toml              # the export's columns and spellings, and [chunking]: the sizes in tokens
├── data/
│   ├── sample_it_kb.csv          # the 10 articles: 39 chunks
│   ├── sample_it_kb_chunking.csv # one article for each chunking case
│   ├── sample_it_kb_reordered.csv, sample_it_kb_next.csv, sample_it_kb_labels.csv, sample_it_kb_messy.csv
│   └── manifest.json             # written by each run (not in git)
├── tests/
│   ├── test_chunking.py          # sections, the ceiling, headers, IDs, parents, each chunking case
│   ├── test_pipeline.py          # the steps run as the script runs them, run after run
│   ├── test_knowledge_base_loader.py, test_article.py, test_settings.py, test_manifest.py
│   ├── test_sensitive_data.py, test_utils.py
├── requirements.txt              # langchain-core, langchain-text-splitters, pydantic
├── requirements-dev.txt          # + pytest
├── pytest.ini
└── .gitignore                    # data/manifest.json
```

---

## 🔧 Configuration

### Command-Line Options

| Option | Default | What it does |
|---|---|---|
| `--data-path` | `data/sample_it_kb.csv` | the CSV file to read |
| `--settings` | `kb_settings.toml` | the export's columns, the spellings, the chunk sizes |
| `--manifest-path` | `data/manifest.json` | the last run's articles; this run's are saved there |
| `--full` | off | cut every article, not only the ones added or changed |
| `--log-level` | `INFO` | `DEBUG` adds one line per row and per issue |

### `[chunking]` in `kb_settings.toml`

| Setting | Default | What it is |
|---|---|---|
| `chunk_size` | 128 | a chunk's size in tokens, its header included |
| `chunk_overlap` | 16 | the last sentences of a chunk, up to this many tokens, start the next one |
| `min_tokens` | 8 | a smaller last piece of a section is merged into the chunk before it |
| `max_tokens` | 512 | the ceiling no chunk passes |

A setting left out keeps its default from `chunking.py`. Sizes that can't work (an overlap as big as a chunk, a
ceiling below a chunk and a fragment) stop the run with one line naming them.

### The Splitter's Constructor

```python
KBTextSplitter(*, chunk_size=128, chunk_overlap=16, min_tokens=8, max_tokens=512, length_function=count_tokens,
               sections=("Problem", "Resolution", "Notes"))
```

`length_function` counts tokens and is passed in as a part: Advanced 04 can pass the embedding model's own count.

---

## 🧪 Testing

```bash
python -m pytest        # 152 passed  (add -v for one line per test)
```

- **The chunks**: no chunk crosses a section; none passes the ceiling, and each records its count; every one starts
  with its title and section; IDs unique, the same on every run and in the re-sorted file; each section kept whole as
  its chunks' parent; text with no section labels is one section; sizes that can't work fail when configured
- **The chunking cases**: clear sections, the 14-step fix cut between whole steps, the one-line note, the repeated
  paragraphs, the run with no spaces, the merged fragment, a repeating run whose cut pieces repeat
- **The pipeline**, as its own process: run twice, the next export, the chunking file's checks, `--full`, a row
  skipped after a good run, the messy file with no sensitive value shown, any folder, bad files, a broken manifest
- **Advanced 02's tests**: the loader, the schema, the settings (now with `[chunking]`), the manifest, the helpers
  (now with `count_tokens()`)

No key and no network: the tests read local files and run the script.

---

## 📊 Understanding the Output

| A chunk's metadata | What it is |
|---|---|
| `chunk_id` | `<doc_id>:<section>:<8 hex digits of its text's hash>`: the same text, the same ID, on every run |
| `section` | `problem`, `resolution` or `notes` |
| `position` | its place among its article's chunks, from 0 |
| `token_count` | its size in tokens, header included (`count_tokens()`'s estimate) |
| `parent_id` | `<doc_id>:<section>`: the whole section, in `splitter.parents` |
| the rest | its article's: `doc_id`, the labels, the provenance (Advanced 02) |

---

## 🎓 Key Concepts Demonstrated

### 1. Structure First, Size Second

An article already says where its meaning changes: the problem, the fix, the notes. Cutting there first means a
search for "how do I fix it" finds a chunk that is all fix. Size only decides where to cut *inside* a section, and
then only between whole sentences.

### 2. Count What the Model Counts

A model reads tokens, not characters, and stops at a limit. `count_tokens()` estimates them, erring high (a token per
4 letters of each word, one per punctuation mark), and the ceiling is a quarter of the model's limit: a chunk can't be
cut off without anyone knowing. The counter is a part passed in, so the real one can replace it.

### 3. A Header Gives a Chunk Its Context

"Resolution: 1. Re-add the printer with its new IP address." matches many questions; with "Printer Offline After
Move" above it, it matches the right one. The header costs a few tokens per chunk and is counted in its size.

### 4. An ID From the Content

`chunk_id` comes from the article's ID, the section and the chunk's text. Unchanged text gets the same ID on every
run, so the next steps can tell which vectors to keep, replace or delete. The position isn't part of it: an edit
early in an article doesn't change the IDs of the chunks after it.

### 5. Small to Search, Whole to Answer

A small chunk matches a question precisely, but the answer may need the whole fix. Each chunk's `parent_id` names its
section, kept whole in `splitter.parents`, for the answering step to fetch.

### 6. Extend the Framework Where It's Meant to Be Extended

`KBTextSplitter` is a LangChain `TextSplitter`: it writes `split_text()` and `create_documents()`, and inherits
`split_documents()`, so any LangChain code that splits Documents can use it.

### 7. Save Progress Only When the Whole Run Worked

The manifest says which articles were handled. Saved before the chunking, a failure there would leave articles
recorded as done but never cut; saved last, a failed run is simply run again.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR Settings file has a bad setting (chunking: the sizes must keep chunk_overlap and min_tokens below chunk_size, ...)`
**Fix**: The sizes in `[chunking]` can't work together; the message says which rule they break.

**Issue**: A chunk is bigger than `chunk_size`
**Fix**: A fragment at the end of a section was merged into it (the chunk checks list each one). It's still under
`max_tokens`.

**Issue**: `Cut again: a piece with no spaces, too big for a chunk`
**Fix**: A section holds a long run with no spaces, such as a log line, a fingerprint or a key. It's cut to fit, but
the pieces mean little: consider shortening it in the knowledge base. (A real key would be redacted first.)

**Issue**: `Chunks: 0 from 0 articles`
**Fix**: Nothing changed since the last run. Run with `--full` to cut every article.

---

## 📚 Next Steps

**[04 · Embeddings (Advanced)](../04-embeddings/README.md)**: batching, retries, a cache so unchanged chunks are
never embedded twice, and cost tracking for turning chunks into vectors.

### Ideas to Try

- Set `chunk_size = 64` in `kb_settings.toml` and run `python pipeline.py --full`: more, smaller chunks.
- Add a paragraph to a copy of an article's notes that repeats its problem, and read the chunk checks.
- Compare the chunks' `token_count` with `len(text) / 4`, a common rule of thumb for English.
- Semantic chunking, cutting where the meaning shifts, needs embeddings: try it after Advanced 04.
