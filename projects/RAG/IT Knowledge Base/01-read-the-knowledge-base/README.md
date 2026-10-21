# 01 · Read the Knowledge Base

Step 1 of the IT Knowledge Base RAG application: read the knowledge base, a CSV file of 10 IT support articles, into
LangChain `Document`s, the form every later step works with. Built with **LangChain** and the Python standard library
(`csv`, `logging`, `argparse`).

> **Series:** [IT Knowledge Base](../README.md), step 1 of 12
> **Needs:** Python only. No model, no API key, no Docker: this step only reads a file.

---

## 🎯 What This Step Does

- **Loads** `data/sample_it_kb.csv` into 10 LangChain `Document`s, one per article
- **Keeps every column** as text: each `Document`'s `page_content` has one `column: value` line per column
- **Records where each one came from** in its `metadata`: the file's name and the row number
- **Logs** what it's doing (on stderr) and **prints** every `Document` (on stdout)
- **Fails clearly**: a missing, empty or non-UTF-8 file stops it with one log line and exit code 1, not a traceback

**Try it:** `python read_kb.py`, and see the 10 articles the way LangChain holds them.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv                 10 rows × 8 columns
          │
          ↓
┌──────────────────────────┐
│   KBLoader(data_path)    │  ← configure: stores which file to read, and how; reads nothing
└────────────┬─────────────┘
             │ load()
             ↓
┌──────────────────────────┐
│       lazy_load()        │  ← checks the file, then reads it one row at a time
│  └─ _row_to_document()   │     row → Document(page_content, metadata)
└────────────┬─────────────┘
             │ 10 Documents
        ┌────┴─────┐
        ↓          ↓
┌────────────┐ ┌────────────┐
│  print()   │ │  logging   │
│   stdout   │ │   stderr   │  ← the Documents  /  what happened
└────────────┘ └────────────┘
```

### The Pipeline in This Step

1. **Configure** → `KBLoader(data_path)` stores the settings
2. **Check** → the file must exist and start with a header row (the column names)
3. **Read** → `csv.DictReader` gives each row as `{column: value}`
4. **Convert** → each row becomes a `Document`: its text, and where it came from
5. **Report** → the log says what was read; the output shows every `Document`

### Where This Step Fits in the RAG Pipeline

1. **Load** → the CSV file into `Document`s ← **this step** (and 02)
2. **Chunk** → cut them into smaller pieces (03)
3. **Embed** → turn each chunk into a vector with Gemini (04)
4. **Store** → keep the vectors in Qdrant (05)
5. **Query** → find the closest chunks to a question, and answer from them (06 to 08)

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: no API key, no Docker, no network once the package is installed

---

## 🚀 Quick Start

### Step 1: Go to This Folder

```bash
cd "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base"   # from the repo root; the quotes are for the spaces
```

### Step 2: Create and Activate a Virtual Environment

```bash
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
```

Creating the venv is once only; activate it again in every new terminal.

### Step 3: Install Dependencies

```bash
pip install -r requirements-dev.txt  # once: langchain-core and pytest, into .venv/
```

### Step 4: Run It

```bash
python read_kb.py
```

First the log says what it read, then the output shows how many documents there are, each one's row and title, and
then every document in full. The start and the end of what you'll see (your times will differ, and `<this folder>`
stands for the full path of this project's folder on your machine):

```text
2026-10-20 22:16:59,293 INFO Reading <this folder>/data/sample_it_kb.csv (utf-8): 8 columns (title, problem, resolution, system, category, notes, priority, tags)
2026-10-20 22:16:59,293 INFO Read 10 documents from sample_it_kb.csv
10 documents
row 0  title: VPN Connection Timeout
row 1  title: MFA Setup Failure
row 2  title: Laptop Performance Degradation
row 3  title: SaaS Access Permission Denied
row 4  title: WiFi Connectivity Issues Office
row 5  title: Password Reset Failed
row 6  title: Printer Not Found
row 7  title: Email Attachment Size Limit
row 8  title: Database Connection Timeout
row 9  title: Microsoft Teams Audio Issues

Document 1 of 10
Text (page_content):
title: VPN Connection Timeout
problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations
resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.
system: VPN
category: Remote Access
notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.
priority: High
tags: vpn;timeout;remote;connection

Where it came from (metadata):
{'source': 'sample_it_kb.csv', 'row': 0}

Document 2 of 10
Text (page_content):
title: MFA Setup Failure
...

Document 10 of 10
Text (page_content):
title: Microsoft Teams Audio Issues
...
tags: teams;audio;collaboration;windows

Where it came from (metadata):
{'source': 'sample_it_kb.csv', 'row': 9}
```

The `...` lines stand for the parts left out here: your terminal shows all 10 documents in full.

---

## 📁 Project Structure

```text
01-read-the-knowledge-base/
├── read_kb.py              # the whole step: KBLoader, print_documents() and main()
├── data/
│   └── sample_it_kb.csv    # the knowledge base: 10 IT support articles
├── tests/
│   └── test_read_kb.py     # 21 tests: the Documents, the loader, the log, the script
├── requirements.txt        # langchain-core, pinned to an exact version
├── requirements-dev.txt    # requirements.txt plus pytest, for the tests
├── pytest.ini              # lets the tests import read_kb, and finds them in tests/
└── README.md               # you are here
```

`read_kb.py` is laid out in sections, each with a banner comment:

| Section | What's in it |
|---|---|
| Configuration | `KB_FILE`, the path to the CSV file, and `LOG_FORMAT`, the shape of each log line |
| KBLoader Class | the loader: `__init__` (configure), `lazy_load()` (Steps 2a to 2d: check, open, convert, total) and `_row_to_document()` (one row) |
| Output | `print_documents()`: everything the script prints |
| Entry Point | `parse_args()` (the command-line options) and `main()` (Steps 3a to 3c: logging, load, print) |

---

## 🔧 Configuration

### Command-Line Options

| Option | Default | What it does |
|---|---|---|
| `--data-path` | `data/sample_it_kb.csv`, next to the script | The CSV file to read. Any file whose first line names the columns works. |
| `--log-level` | `INFO` | The least serious log messages to show: `DEBUG`, `INFO`, `WARNING` or `ERROR`. `DEBUG` adds one line per row. |

```bash
python read_kb.py --data-path data/sample_it_kb.csv   # the same as no option
python read_kb.py --log-level DEBUG                   # one more log line per row
python read_kb.py --help                              # every option, with its default
```

### The Loader's Constructor

```python
KBLoader(
    data_path: str | Path,     # required: the CSV file to read
    encoding: str = "utf-8",   # the file's text encoding
)
```

The constructor only stores these two settings; nothing is opened until `load()`. To read a different file or
encoding, you change the arguments, not the code:

```python
docs = KBLoader("data/sample_it_kb.csv").load()
docs = KBLoader("export.csv", encoding="utf-16").load()   # a file saved as UTF-16
```

---

## 🧪 Testing

```bash
python -m pytest                     # 21 passed     (add -v for one line per test)
```

The tests need no network. They read the sample file and a few small CSV files they write themselves, and they run
the script as its own process:

- **The Documents**: 10 of them, every column as a line in order, the metadata, the first one is the VPN article
- **The loader**: the constructor reads nothing; `load()` and `lazy_load()` agree; a missing, empty or non-UTF-8 file
  fails with a clear message; the encoding can be changed; any CSV with a header row can be read
- **The log**: the two INFO lines, the first with the file's full path; one DEBUG line per row; and a warning for a
  header with no rows
- **The script**: the options' defaults, exit code 1 with no traceback for a missing file, a relative path reported
  as the full path it was looked for at, the exact printed output, and the same output whichever folder it's
  started from

---

## 📊 Understanding the Output

The script writes to two places, kept apart on purpose:

| Stream | What goes there | Written by |
|---|---|---|
| **stdout** | The output: the 10 Documents | `print()` |
| **stderr** | The log: what the program did, and what went wrong | `logging`, as `time LEVEL message` |

Both show in your terminal, but each can be sent somewhere else on its own:

```bash
python read_kb.py > documents.txt    # the Documents go to the file; the log still shows on screen
python read_kb.py 2> /dev/null       # only the Documents (macOS, Linux, Codespaces; PowerShell: 2>$null)
```

Each Document has two parts:

```text
Document 1 of 10
Text (page_content):                           ← every column, as "column: value" lines
title: VPN Connection Timeout
...
tags: vpn;timeout;remote;connection

Where it came from (metadata):                 ← the file, and the row (0 = the first article)
{'source': 'sample_it_kb.csv', 'row': 0}
```

---

## 🎓 Key Concepts Demonstrated

### 1. A Document: Text + Metadata

```python
Document(page_content="title: VPN Connection Timeout\nproblem: ...", metadata={"source": "sample_it_kb.csv", "row": 0})
```

`page_content` is the text that later steps will cut up, embed and search; `metadata` travels with it, so an answer
can say where it came from.

### 2. Configure First, Load Later

```python
loader = KBLoader(KB_FILE)   # says what to do: which file. Nothing is read yet.
docs = loader.load()         # does it: this is the line that reads the file.
```

The same split as a RAG engine's constructor: the settings go in first, and the work happens when it's asked for.

### 3. `lazy_load()` and `load()`

`lazy_load()` hands out one Document at a time, so even a very large file never has to be in memory all at once.
`load()`, from LangChain's `BaseLoader`, just collects them into a list. Every LangChain loader works this way.

### 4. Logging for What Happened, `print()` for the Output

```python
logger = logging.getLogger(__name__)                       # one logger per module
logger.info("Read %d documents from %s", count, name)      # the values as arguments, not an f-string
```

Each log line has a level, so you choose how much to see without changing the code: `DEBUG` (every row), `INFO`
(the default: start and total), `WARNING` (a header with no rows), `ERROR` (the file can't be read). Logging is set
up once, in `main()`: a module that's only imported, as the tests import this one, leaves that to whoever imports it.

### 5. Fail Fast, With a Clear Message

The loader checks the file before reading it and raises an error that names the file. `main()` turns the errors it
expects into one log line and exit code 1, so a typo in a path doesn't end in a traceback. An error it doesn't expect
still shows its full traceback, because that's what you'd need to fix it.

### 6. A Path From the Script, Not From Where You Run It

```python
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"
```

`Path(__file__).resolve().parent` is the folder the script is in, so the file is found whichever folder you start
it from. A bare `"data/sample_it_kb.csv"` would be looked for in the current folder.

---

## 🛠️ Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'langchain_core'`
**Fix**: The venv isn't active, or the packages aren't installed in it. Activate it (Step 2), then
`pip install -r requirements-dev.txt` (Step 3).

**Issue**: `ERROR Knowledge base file not found: <the folder you're in>/data/it_kb.csv`
**Fix**: The message gives the full path the file was looked for at. A relative path given to `--data-path` is looked
for from the folder you're in, not from the script's folder. Check the path, or run without `--data-path` to read the
sample file.

**Issue**: `ERROR Knowledge base file is empty, with no header row: ...`
**Fix**: The file has no lines at all. Its first line must name the columns, like `title,problem,resolution,...`.

**Issue**: `ERROR Knowledge base file isn't utf-8 text (invalid start byte): ... Save it as UTF-8, or give KBLoader its encoding.`
**Fix**: The file was saved in another encoding, often UTF-16 by Windows PowerShell 5's `>`. Save it again as UTF-8
(in VS Code: the encoding in the status bar, then *Save with Encoding*), or read it with
`KBLoader(path, encoding="utf-16")`.

**Issue**: `WARNING ... has a header row but no articles`, then `0 documents`
**Fix**: The file has the column names but no rows under them. Add the articles, one per line.

**Issue**: `read_kb.py: error: argument --log-level: invalid choice: 'LOUD' (choose from DEBUG, INFO, WARNING, ERROR)`
**Fix**: Use one of the four levels it lists. Run `python read_kb.py --help` to see every option.

---

## 📚 Next Steps

**[Step 02: Documents and Metadata](../02-documents-and-metadata/README.md)**: this step put every column into a
Document's text. Step 02 splits each article into the text to search (title, problem, resolution, notes) and the
labels kept next to it (system, category, priority, tags), which later show with an answer as its source.

### Ideas to Try

- Run `python read_kb.py --log-level DEBUG` and find the log line for each row.
- Point `--data-path` at a CSV file of your own, with a header row, and see its rows become Documents.
- Copy the sample file and delete everything but its first line, then read it: 0 documents, and a warning in the log.
