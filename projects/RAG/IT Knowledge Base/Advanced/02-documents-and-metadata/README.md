# 02 · Documents and Metadata (Advanced)

Read the IT knowledge base into LangChain `Document`s whose labels are reliable enough to filter, cite and update
by. Each article's text (what gets searched) is kept apart from its labels (what gets filtered on); each article is
checked against a schema; each label value has one spelling; each article gets an ID that survives re-sorting the
file and a record of where it came from; and a re-run passes on only the articles that changed. Everything Advanced
01 checks is still checked: rows, sensitive data, duplicates. Built with **LangChain**, **Pydantic** and the Python
standard library (`csv`, `tomllib`, `hashlib`, `json`).

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads local files.
> **Production version of:** [Basic · 02 · Documents and Metadata](../../Basic/02-documents-and-metadata/README.md),
> built on [Advanced · 01](../01-read-the-knowledge-base/README.md).

---

## 🎯 What This Project Does

- **Splits text from labels**: each `Document`'s `page_content` holds the title, problem, resolution and notes;
  its `metadata` holds the title, system, category, priority, tags, visibility and team
- **Checks every article against a schema** (`article.py`, a Pydantic model): the required fields, the most
  characters each may have, a priority from four values, a visibility from three; an article that breaks a rule is
  skipped, and the report names the field and why
- **Types the labels**: `priority` is one of `Low`, `Medium`, `High`, `Critical`; `tags` is a list (split on `;`,
  in lower case, each once); an empty value is `None`, not an empty label
- **Gives each label value one spelling**: `Wi-Fi`, `wifi` and `WiFi` all become `WiFi`, from tables in
  `kb_settings.toml`; each change is reported, and a system or category the tables don't know is flagged
- **Reads its column mapping from a settings file**: a new export with renamed columns needs a change to
  `kb_settings.toml`, not to the code
- **Gives each article a stable ID**: the export's own `id` when it has one, else a hash of the title and system,
  so re-sorting the file never changes an ID
- **Records provenance** in every `Document`: the file, its SHA-256 checksum, when it was loaded, and by which version
  of the loader
- **Passes on only what changed**: a manifest of the last run's articles (`data/manifest.json`) says which ones
  were added, changed (and in which fields) or removed; a row skipped this run is never taken for a removed article
- **Never drops or changes anything silently**: a report lists every row skipped, removed, normalized, redacted or
  flagged, and every article added, changed or removed, and why

**Try it:** run `python knowledge_base_loader.py` twice: the first run passes on all 10 articles, the second none.
Then `python knowledge_base_loader.py --data-path data/sample_it_kb_next.csv`, the next export: 1 article added,
2 changed, 1 removed.

---

## 🏗️ Architecture

```text
kb_settings.toml ──→ load_settings()      which column holds each field, text or label, one spelling per value
                           │                (checked at start: a typo stops the run, naming the setting)
data/*.csv ──────→ KBLoader(path, settings=...)
                           │ load()
                           ↓
               ┌──────────────────────────────┐
               │         lazy_load()          │
               │  ├─ the header and each row  │  as Advanced/01: fields, invisible characters, required values
               │  ├─ redact()                 │  sensitive data (sensitive_data.py)
               │  ├─ Spellings                │  one spelling per priority, system and category   → normalized
               │  ├─ Article (the schema)     │  required, lengths, allowed values, typed labels  → skipped
               │  ├─ duplicates               │  the same values, ignoring case and spacing       → removed
               │  ├─ doc_id()                 │  an ID from the export, or the title and system   → skipped if shared
               │  └─ _to_document()           │  text + labels + ID + provenance; each field's hash
               └──────────────┬───────────────┘
                              │ Documents, loader.report, loader.fingerprints
                              ↓
data/manifest.json ←→ Manifest.compare()     added · changed (which fields) · unchanged · removed · held
                              │
                              ↓
                  the Documents passed on: added and changed
```

### The Pipeline in This Project

1. **Read the settings** → `kb_settings.toml`, checked: every field name real, the required fields mapped
2. **Check the file and the header** → as Advanced 01; a column the settings don't name is logged and not read
3. **Check each row** → the right number of fields, no invisible characters, no blank required value
4. **Redact** → sensitive values replaced before anything else sees them
5. **One spelling** → each priority, system and category value changed to its one spelling, and reported
6. **The schema** → the article as a Pydantic `Article`; a value that breaks a rule skips the row, with why
7. **Duplicates and IDs** → a copy is removed; two different articles with one ID: the second is skipped
8. **The Document** → text, labels, ID and provenance; a hash of each field for the manifest
9. **Compare with the last run** → only added and changed articles are passed on; removed ones are listed
10. **Save the manifest and report** → the Documents passed on, the data checks, then the changes

---

## 📋 Prerequisites

- **Python 3.11 or newer** (for `tomllib`, in the standard library since 3.11)
- Nothing else: once the packages are installed, it runs without a network

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/Advanced/02-documents-and-metadata"   # from the repo root; quotes for the spaces
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
pip install -r requirements-dev.txt  # once: langchain-core, pydantic and pytest, into .venv/
```

### Step 4: Run It

```bash
python knowledge_base_loader.py
```

The first run has no manifest to compare with, so all 10 articles are passed on. The output starts with each one's
ID and title, then every `Document` in full (yours differ in `loaded_at`):

```text
Documents passed on to the next step: 10
  kb-4c38012d03ec9cc2  VPN Connection Timeout
  kb-805b23ae07210f0f  MFA Setup Failure
  ...

Document 1 of 10
Text (page_content):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. ...

Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Labels and where it came from (metadata):
  doc_id: kb-4c38012d03ec9cc2
  title: VPN Connection Timeout
  system: VPN
  category: Remote Access
  priority: High
  tags: ['vpn', 'timeout', 'remote', 'connection']
  visibility: None
  team: None
  source: sample_it_kb.csv
  source_sha256: 35d43128c44a47f9848ff0976b5768de6479e33e005c169d297b37c1a973ffdf
  loaded_at: 2026-10-31T00:39:40+00:00
  loader_version: advanced-02
  row: 0
  content_hash: bd589c60dc1d1284
```

It ends with the data checks and the changes:

```text
Data checks: 10 rows read, 10 kept (4 blank lines ignored)
Nothing skipped, removed, normalized, redacted or flagged.

Changes: no earlier run to compare with, so all 10 articles are new
```

Run it again: nothing changed, so nothing is passed on.

```text
Documents passed on to the next step: 0
...
Changes since the last run: 0 added, 0 changed, 0 removed, 10 unchanged
```

Now read the next export, `data/sample_it_kb_next.csv`, where one fix was edited, one priority raised, one article
dropped and one added:

```bash
python knowledge_base_loader.py --data-path data/sample_it_kb_next.csv
```

```text
Documents passed on to the next step: 3
  kb-4c38012d03ec9cc2  VPN Connection Timeout
  kb-3f603bf5a89d27bf  Laptop Performance Degradation
  kb-69aaacbea17bb80f  Keyboard Not Responding
...
Changes since the last run: 1 added, 2 changed, 1 removed, 7 unchanged

Added: passed on (1)
  kb-69aaacbea17bb80f  Keyboard Not Responding

Changed: passed on (2)
  kb-4c38012d03ec9cc2  VPN Connection Timeout  (resolution changed)
  kb-3f603bf5a89d27bf  Laptop Performance Degradation  (priority changed)

Removed: not in this file, listed for deletion (1)
  kb-742c2b300287e249  Printer Not Found
```

`data/sample_it_kb_reordered.csv` holds the 10 sample articles in another order: read after the sample, it passes on
nothing, since every ID is the same. `--full` passes on every article, whatever changed.

### The Labels File: The Schema and the Spellings at Work

`data/sample_it_kb_labels.csv` has a label or schema problem in most of its 11 rows:

```bash
python knowledge_base_loader.py --data-path data/sample_it_kb_labels.csv --full
```

```text
Data checks: 11 rows read, 6 kept

Skipped, not read: each can't be trusted as it is (5)
  row 5 (line 7): doesn't fit the schema: priority: Input should be 'Low', 'Medium', 'High' or 'Critical' (given "Urgent")
  row 6 (line 8): doesn't fit the schema: visibility: Input should be 'public', 'internal' or 'restricted' (given "secret")
  row 7 (line 9): doesn't fit the schema: title: String should have at most 200 characters
  row 8 (line 10): no value for resolution
  row 9 (line 11): the same ID as row 0 (kb-4c38012d03ec9cc2), with different content: the same title and system: give one a different title, or the file an id column

Normalized, kept: a label changed to its one spelling (6)
  row 1 (line 3): priority: "high" made "High"
  row 1 (line 3): system: "Wi-Fi" made "WiFi"
  row 2 (line 4): system: "wifi" made "WiFi"
  row 2 (line 4): category: "Networking" made "Network"
  row 3 (line 5): priority: "P1" made "Critical"
  row 10 (line 12): system: "Teams" made "Microsoft Teams"

Flagged, kept: a person should look at these (1)
  row 4 (line 6): system "Kiosk" has no spelling in kb_settings.toml: kept as written
```

(Each skipped row is also shown under its line, with its fields, sensitive values redacted.) Advanced 01's messy
file, `data/sample_it_kb_messy.csv`, still gets all of 01's checks; two of its rows are now skipped, not flagged: a
second "VPN Connection Timeout" for the same system (one ID, two articles) and a priority of "Urgent".

---

## 📁 Project Structure

```text
02-documents-and-metadata/
├── knowledge_base_loader.py      # KBLoader (BaseLoader), the checks, the Document; main(): load, compare, save, print
├── article.py                    # Article (the schema), Priority, Spellings, doc_id(), describe()
├── settings.py                   # KBSettings and load_settings(): kb_settings.toml, checked
├── manifest.py                   # Manifest and Changes: what changed since the last run
├── sensitive_data.py             # redact(): PII, PCI and secrets, as in Advanced/01 (unchanged)
├── utils.py                      # helpers: hashes, simplify(), spelling_key(), the print_* functions
├── kb_settings.toml              # the export's columns, text and label fields, ID fields, spellings
├── data/
│   ├── sample_it_kb.csv          # the 10 articles
│   ├── sample_it_kb_reordered.csv   # the same 10, in another order: the same IDs
│   ├── sample_it_kb_next.csv     # the next export: 1 fix edited, 1 priority raised, 1 article gone, 1 new
│   ├── sample_it_kb_labels.csv   # one row for each label or schema problem
│   ├── sample_it_kb_messy.csv    # Advanced/01's file: a row problem in most rows
│   └── manifest.json             # written by each run (not in git): the last run's articles
├── tests/
│   ├── test_knowledge_base_loader.py   # the Documents, the checks, the IDs, the script run after run
│   ├── test_article.py           # the schema, the spellings, the IDs
│   ├── test_settings.py          # every way kb_settings.toml can be wrong
│   ├── test_manifest.py          # added, changed, removed, held; written whole or not at all
│   ├── test_sensitive_data.py    # Advanced/01's (unchanged)
│   └── test_utils.py             # the helpers
├── requirements.txt              # langchain-core, pydantic
├── requirements-dev.txt          # + pytest
├── pytest.ini                    # the tests import from this folder
└── .gitignore                    # data/manifest.json
```

---

## 🔧 Configuration

### Command-Line Options

| Option | Default | What it does |
|---|---|---|
| `--data-path` | `data/sample_it_kb.csv` | the CSV file to read |
| `--settings` | `kb_settings.toml` | what the file holds, and one spelling per label value |
| `--manifest-path` | `data/manifest.json` | the last run's articles; this run's are saved there |
| `--full` | off | pass on every article, not only the ones added or changed |
| `--log-level` | `INFO` | `DEBUG` adds one line per row and per issue |

### `kb_settings.toml`

| Setting | What it says |
|---|---|
| `text_fields` | the fields in the `Document`'s text, in order |
| `label_fields` | the fields in its metadata |
| `id_fields` | what an ID is made from when the export has no `id` column (`title` and `system`) |
| `[columns]` | each field, and the export's column that holds it; `title`, `problem` and `resolution` must be in the file |
| `[spellings.<label>]` | each right spelling, and the other spellings that mean it |

The file is checked when it's read: a field name an article doesn't have, a required field with no column, two
fields read from one column, or a spelling claimed by two values stops the run with one line naming the setting.

### The Loader's Constructor

```python
KBLoader(data_path, *, settings, encoding="utf-8", clock=utc_now)
```

`settings` is a `KBSettings` (from `load_settings()`), passed in as an object; the constructor reads nothing.
`clock` gives the time recorded as `loaded_at`: tests pass a stopped clock, so two loads give the same `Document`s.

---

## 🧪 Testing

```bash
python -m pytest        # 123 passed  (add -v for one line per test)
```

- **The Documents**: text and labels apart, typed labels, every metadata key, provenance, one ID per article, the
  same IDs in the re-sorted file, an export's own `id` used as the ID, a hash of each field
- **Advanced 01's checks**, on the messy file: every row kept, skipped or removed is accounted for; the reasons; the
  redactions; no sensitive value anywhere
- **The schema and spellings**, on the labels file: each skipped row's reason, each normalized label, the flag, the
  shared ID, a title used for two systems
- **The settings**: the project's file, and each way one can be wrong
- **The manifest**: first run, unchanged, added, changed (which fields), removed, held, `--full`, a broken manifest,
  a manifest that can't be written
- **The script**, as its own process: run twice, the next export, `--full`, a row skipped after a good run, the
  messy file's report with no sensitive value, any folder, and the errors' exit code 1

No key and no network: the tests read local files and run the script.

---

## 📊 Understanding the Output

| Metadata | What it is |
|---|---|
| `doc_id` | the article's ID: `kb-` and 16 hex digits of the SHA-256 of its title and system, or the export's `id` |
| `title` … `team` | the labels, typed: `priority` one of four values, `tags` a list, an empty value `None` |
| `source`, `source_sha256` | the file's name and checksum: the exact file the article came from |
| `loaded_at`, `loader_version` | when it was loaded (UTC), and by which version of this code |
| `row` | its place in the file (counting articles from 0): for finding it, never for identifying it |
| `content_hash` | a hash of all its fields: changes when any does |

The changes have five lists: **added** and **changed** articles are passed on; **unchanged** ones aren't;
**removed** ones (in the last run, not in this file) are listed so a later step can delete them; **held** ones were
skipped this run, so their last version stays and nothing is deleted.

---

## 🎓 Key Concepts Demonstrated

### 1. Check at the Door, With a Contract

```python
article = Article.model_validate(values)            # knowledge_base_loader.py, _check_row()
```

The schema is the data contract: what an article must have and what each value may be. A bad row is caught where it
comes in, with the field and the reason, not found weeks later as a strange answer. Pydantic does the checking and
writes the reasons; `describe()` puts them on one line.

### 2. Typed Labels Filter Exactly

`priority == "High"` matches every high-priority article only when every one says exactly `High`. An enum makes that
true; a list makes "tag is vpn" a membership test instead of a search inside `"vpn;timeout;remote"`.

### 3. One Spelling, From a Table, Reported

`Wi-Fi`, `wifi` and `WiFi` would be three systems to a filter. The tables in `kb_settings.toml` map each spelling to
one, ignoring case, spaces, hyphens and underscores, and every change is in the report. A value no table knows is
kept and flagged: guessing would hide a new system.

### 4. An ID That Means the Article, Not Its Row

The row number changes when a row is added above it; the hash of the title and system doesn't. Later steps use the ID
to update or delete an article's chunks and vectors instead of adding copies. Two different articles can't share an
ID, so the second is skipped, with the way to fix it: a different title, or an `id` column.

### 5. Provenance on Every Document

Each `Document` says which file it came from (and that file's checksum), when, and by which code. Any answer can then
be traced to the exact load that produced its sources.

### 6. Incremental Loading: Compare, Don't Reload

```python
changes = manifest.compare(docs, loader.fingerprints, held=loader.report.held)
```

Re-embedding 10,000 articles to change one is slow and costs money. The manifest keeps a hash of each field of each
article; the next run passes on only what's new or different, and says which fields changed. Two rules keep it safe:
a row skipped this run is **held**, never taken for a removed article (which a later step would delete), and the
manifest is written whole or not at all. In a full pipeline, the manifest would be saved only after the later steps
succeed; here, where loading is the whole run, it's saved at the end of the run.

### 7. Configure, Then Work; Parts Passed In

`KBLoader` gets its settings and its clock as objects, and reads nothing until `load()`. Tests pass their own
settings, a renamed column, or a stopped clock, with no change to the class.

---

## 🛠️ Troubleshooting

**Issue**: `ERROR Settings file has a bad setting (...)`
**Fix**: The message names the setting. A field name must be one of the `Article` fields; `title`, `problem` and
`resolution` need a column; a spelling can mean only one value.

**Issue**: `INFO Not read: column owner (kb_settings.toml gives it no field)`
**Fix**: The file has a column the settings don't map. If it should be read, add the field to `article.py`'s
`Article` and the column to `[columns]`.

**Issue**: An article is skipped with `the same ID as row 0 (...), with different content`
**Fix**: Two articles have the same title and system. Give one a different title, or give the export an `id`
column, which then becomes the ID.

**Issue**: `ERROR The manifest can't be read (...)`
**Fix**: `data/manifest.json` is broken or from another version of this code. Delete it, or run with `--full`:
every article is passed on, and a new manifest is saved.

**Issue**: `WARNING 1 skipped row had no ID to tell which article it was: an article listed as removed may be one`
**Fix**: A row was too broken to read its title and system (the wrong number of fields, say). If its article is
listed as removed, it may only be broken: fix the row before deleting anything.

**Issue**: An article you edited is listed as removed and added again
**Fix**: Its title or system changed, so its ID did. That's expected without an `id` column.

---

## 📚 Next Steps

**[03 · Chunking (Advanced)](../03-chunking/README.md)**: chunks cut along the article's sections, sized in tokens,
with stable IDs and parent links.

### Ideas to Try

- Add `Wifi 6` as a spelling of `WiFi` in `kb_settings.toml`, and read the labels file again.
- Rename the export's `title` column to `Summary` in a copy of the sample, change `[columns]`, and read it.
- Add an `id` column to a copy of the sample, read it, re-sort it, and read it again: the IDs are the column's.
- Edit one article's notes in a copy of the sample, run it, and read which field the changes name.
