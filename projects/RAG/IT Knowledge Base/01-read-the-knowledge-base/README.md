# 01 · Read the Knowledge Base

Read the IT knowledge base, a CSV file of 10 IT support articles, into LangChain `Document`s: one per article, each
with its text and where it came from. Every row is checked first, sensitive data is redacted, duplicates are
removed, and a report says what happened to every row that wasn't read as it was. Built with **LangChain** and the
Python standard library (`csv`, `re`, `logging`, `argparse`).

> **Needs:** Python 3.11 or newer, and nothing else: this project only reads a local file.

---

## 🎯 What This Project Does

- **Loads** `data/sample_it_kb.csv` into 10 LangChain `Document`s, one per article
- **Keeps every column** as text: each `Document`'s `page_content` has one `column: value` line per column
- **Records where each one came from** in its `metadata`: the file's name and the row number
- **Checks the data**: the header must name `title`, `problem` and `resolution`, each once; a row with the wrong
  number of fields or a blank required value is skipped; invisible characters are removed; values are trimmed; a
  value outside the allowed ones (`priority`) is flagged
- **Redacts sensitive data** before it goes into a `Document`: personal data (PII), payment card numbers (PCI) and
  secrets (passwords, keys, tokens)
- **Removes duplicates**, including copies that differ only in upper and lower case or spacing, and flags a title
  used for two different articles
- **Never drops or changes a row silently**: a report lists every row skipped, removed, redacted or flagged, with
  its row, its line in the file, and why
- **Fails clearly**: a missing, empty, unreadable or non-UTF-8 file, or an unusable header, stops it with one log
  line and exit code 1, not a traceback

**Try it:** `python knowledge_base_loader.py --data-path data/sample_it_kb_messy.csv`, a file with a problem in
most rows, and read the report at the end.

---

## 🏗️ Architecture

```text
data/sample_it_kb.csv                 10 rows × 8 columns
          │
          ↓
┌──────────────────────────────┐
│     KBLoader(data_path)      │  ← configure: which file, how to read it, what to require; reads nothing
└──────────────┬───────────────┘
               │ load()
               ↓
┌──────────────────────────────┐
│         lazy_load()          │  ← checks the file, then reads it one row at a time:
│  ├─ _check_header()          │     column names: cleaned, none blank or twice, required ones there
│  ├─ _check_row()             │     each row: fields, invisible characters, required values,
│  │   └─ redact()             │       sensitive data (sensitive_data.py), allowed values, duplicates
│  └─ _to_document()           │     a good row → Document(page_content, metadata)
└──────────────┬───────────────┘
               │ Documents + loader.report
        ┌──────┴───────┐
        ↓              ↓
┌──────────────┐ ┌──────────────┐
│   print()    │ │   logging    │
│    stdout    │ │    stderr    │  ← the Documents and the report  /  what happened, in totals
└──────────────┘ └──────────────┘
```

### The Pipeline in This Project

1. **Configure** → `KBLoader(data_path)` stores the settings
2. **Check the file** → it must exist, be readable as CSV, and start with a header row (the column names)
3. **Check the header** → names cleaned; none blank or twice; `title`, `problem` and `resolution` there
4. **Check each row** → the right number of fields and no blank required value, or it's skipped; invisible
   characters removed; values trimmed
5. **Redact** → sensitive values replaced in the text, and reported only masked
6. **Check the values** → a value outside the allowed ones is flagged
7. **Deduplicate** → a copy of an earlier row is removed; a reused title is flagged
8. **Report** → the output shows every `Document`, then every row skipped, removed, redacted or flagged, and why

---

## 📋 Prerequisites

- **Python 3.11 or newer**
- Nothing else: once the packages are installed, it runs without a network

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
python knowledge_base_loader.py
```

First the log says what it read, then the output shows how many documents there are, each one's row and title,
every document in full, and last the data checks. The start and the end of what you'll see (your times will
differ, and `<this folder>` stands for the full path of this project's folder on your machine):

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

Data checks: 10 rows read, 10 kept (4 blank lines ignored)
Nothing skipped, removed, redacted or flagged.
```

The `...` lines stand for the parts left out here: your terminal shows all 10 documents in full. The sample file
is clean, so every check passes; the 4 blank lines are at its end. To see the checks at work, run the messy file:

```bash
python knowledge_base_loader.py --data-path data/sample_it_kb_messy.csv
```

---

## 📁 Project Structure

```text
01-read-the-knowledge-base/
├── knowledge_base_loader.py              # KBLoader, its LoadReport, print_documents(), print_report() and main()
├── sensitive_data.py                     # finds PII, PCI and secrets in a text, and redacts them
├── data/
│   ├── sample_it_kb.csv                  # the knowledge base: 10 IT support articles, all clean
│   └── sample_it_kb_messy.csv            # 14 rows with a problem in most: one for each check
├── tests/
│   ├── test_knowledge_base_loader.py     # the Documents, the loader, the checks and their report, the log, the script
│   └── test_sensitive_data.py            # each kind of sensitive value, and ordinary text left alone
├── requirements.txt                      # langchain-core, pinned to an exact version
├── requirements-dev.txt                  # requirements.txt plus pytest, for the tests
├── pytest.ini                            # lets the tests import knowledge_base_loader, and finds them in tests/
└── README.md                             # you are here
```

`knowledge_base_loader.py` is laid out in sections, each with a banner comment:

| Section | What's in it |
|---|---|
| Configuration | `KB_FILE`; `LOG_FORMAT`; `REQUIRED_COLUMNS`; `ALLOWED_VALUES`; `INVISIBLE`, the characters removed; `SHOW_LIMIT`, how much of a skipped row is shown |
| LoadReport | `Issue` (one finding: row, lines, message) and `LoadReport` (rows, kept, and the four lists: skipped, duplicates, redacted, flagged) |
| KBLoader Class | `__init__` (configure); `lazy_load()` (Steps 2a, 2b and 2h: the file, the header, the totals); `_check_header()`; `_check_row()` (Steps 2c to 2g: fields, invisible characters and required values, redaction, allowed values, duplicates); `_show()` and `_to_document()` |
| Output | `print_documents()` and `print_report()`: everything the script prints |
| Entry Point | `parse_args()` (the command-line options) and `main()` (Steps 3a to 3c: logging, load, print) |

`data/sample_it_kb_messy.csv` starts from the sample's articles, and each row tests one thing:

| Row | Line | What's wrong with it | What happens |
|---|---|---|---|
| 0 | 2 | nothing: the VPN article | kept |
| 1 | 3 | an exact copy of row 0 | removed as a duplicate |
| 2 | 4 | row 0 again, with its title in lower case and extra spaces | removed as a duplicate |
| 3 | 5 | row 0's title, with a different problem and fix | kept, flagged |
| 4 | 6 | a comma inside a value that isn't in quotes: 9 fields | skipped |
| 5 | 7 | only 3 fields | skipped |
| 6 | 8 | no `resolution` | skipped |
| | 9 | a blank line | ignored, and counted |
| 7 | 10 | an email address and a phone number | kept, both redacted |
| 8 | 11 | a payment card number | kept, redacted |
| 9 | 12 | a password inside a database URL, and a password in the notes | kept, both redacted |
| 10 | 13 | a Social Security number | kept, redacted |
| 11 | 14 | `priority` is `Urgent`, and the title has spaces around it | kept, flagged; spaces trimmed |
| 12 | 15 | an invisible zero-width space in the title | kept, flagged, the character removed |
| 13 | 16-18 | a quote that's never closed, so the 2 articles after it were read into it | skipped, and the 2 articles shown |

Every sensitive value in it is a made-up test value: an `example.com` address, a 555-01xx phone number, the standard
Visa test card `4111 1111 1111 1111`, and the placeholder Social Security number `123-45-6789`.

---

## 🔧 Configuration

### Command-Line Options

| Option | Default | What it does |
|---|---|---|
| `--data-path` | `data/sample_it_kb.csv`, next to the script | The CSV file to read. Any file whose first line names the columns, including `title`, `problem` and `resolution`, works. |
| `--log-level` | `INFO` | The least serious log messages to show: `DEBUG`, `INFO`, `WARNING` or `ERROR`. `DEBUG` adds one line per row, and one per issue. |

```bash
python knowledge_base_loader.py --data-path data/sample_it_kb_messy.csv   # one row for each check
python knowledge_base_loader.py --log-level DEBUG                         # one more log line per row
python knowledge_base_loader.py --help                                    # every option, with its default
```

### The Loader's Constructor

```python
KBLoader(
    data_path: str | Path,                                         # required: the CSV file to read
    encoding: str = "utf-8",                                       # the file's text encoding
    required_columns: tuple = ("title", "problem", "resolution"),  # the header must have them; every row fills them in
    allowed_values: dict | None = None,                            # None: {"priority": ("Low", "Medium", "High", "Critical")}
)
```

The constructor only stores these settings; nothing is opened until `load()`. To read a different file, encoding
or kind of CSV, you change the arguments, not the code:

```python
docs = KBLoader("data/sample_it_kb.csv").load()
docs = KBLoader("export.csv", encoding="utf-16").load()           # a file saved as UTF-16
docs = KBLoader("assets.csv", required_columns=("name",), allowed_values={}).load()   # a CSV with other columns
```

After `load()`, `loader.report` holds what the checks found: `rows`, `kept`, `blank_lines`, and the lists
`skipped`, `duplicates`, `redacted` and `flagged`.

---

## 🧪 Testing

```bash
python -m pytest                     # 62 passed     (add -v for one line per test)
```

The tests need no network. They read the two data files and a few small CSV files they write themselves, and they
run the script as its own process:

- **The Documents**: 10 of them, every column as a line in order, the metadata, the first one is the VPN article
- **The loader**: the constructor reads nothing; `load()` and `lazy_load()` agree; a missing, empty, non-UTF-8 or
  unreadable file fails with a clear message; the encoding, the required columns and the allowed values can be
  changed
- **The header**: an Excel BOM and spaces are cleaned; a column with no name or named twice, or a missing required
  column, fails
- **The messy file**: 8 of 14 rows kept, and every other row accounted for; the exact skipped, removed, redacted
  and flagged lists; the rows a missing quote swallowed are shown; no sensitive value in any Document
- **The sensitive data**: 14 examples of 11 kinds of value found, replaced and masked; dates, ports, error codes, a
  number that fails the Luhn check and the sample's own text left alone; a finding never holds the value
- **The log**: the two INFO lines, the first with the file's full path; one DEBUG line per row; a warning for a
  header with no rows; one warning line counting what the checks found
- **The script**: the options' defaults; exit code 1 with no traceback for a missing file or a missing required
  column; a relative path reported as the full path it was looked for at; the exact printed output; the report for
  the messy file, with no sensitive value printed or logged; the same output whichever folder it's started from

---

## 📊 Understanding the Output

The script writes to two places, kept apart on purpose:

| Stream | What goes there | Written by |
|---|---|---|
| **stdout** | The output: the Documents, then the data checks | `print()` |
| **stderr** | The log: what the program did, and what went wrong, in totals | `logging`, as `time LEVEL message` |

Both show in your terminal, but each can be sent somewhere else on its own:

```bash
python knowledge_base_loader.py > documents.txt    # the output goes to the file; the log still shows on screen
python knowledge_base_loader.py 2> /dev/null       # only the output (macOS, Linux, Codespaces; PowerShell: 2>$null)
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

The data checks come last. For the messy file, they list every row that wasn't read as it was, in four groups:

```text
Data checks: 14 rows read, 8 kept (1 blank line ignored)

Skipped, not read: each can't be trusted as it is (4)
  row 4 (line 6): 9 fields, but the header has 8: usually a comma inside a value that isn't in quotes
      title: Printer Not Found | problem: Users cannot see the office printer | resolution: Check the printer is on | system: then re-add it in Settings | category: Printer | notes: Hardware | priority: Common after network changes. | tags: Low | extra 1: printer;network
  row 5 (line 7): 3 fields, but the header has 8
      title: MFA Setup Failure | problem: Users can't finish MFA setup | resolution: Re-register the device
  row 6 (line 8): no value for resolution
      title: Laptop Performance Degradation | problem: Laptop is slow after updates | resolution:  | system: Laptop | category: Hardware | notes: Check for runaway processes. | priority: Medium | tags: laptop;performance
  row 13 (lines 16-18): 2 fields, but the header has 8: a quote that's never closed made lines 16-18 into one row
      title: Password Reset Failed | problem: Users cannot reset their password,Check the account is not locked,Active Directory,Identity Management,Self-service portal.,High,password;reset\nPrinter Not Found,Printers do not show up,Re-add the printer,Printer,Hardware,After moves.,Low,printer\nMicrosoft Teams Audio Issues,No sound in calls,Pick the right speaker,Microsoft Teams,Collaboration,,Low,teams

Removed as duplicates: the first copy is kept (2)
  row 1 (line 3): the same as row 0: VPN Connection Timeout
  row 2 (line 4): the same as row 0 apart from upper and lower case or spacing: vpn connection timeout

Sensitive values redacted: replaced in the text, never shown in full (6)
  row 7 (line 10): problem: email address j***@example.com (PII)
  row 7 (line 10): problem: phone number ***-***-0142 (PII)
  row 8 (line 11): notes: card number **** 1111 (PCI)
  row 9 (line 12): resolution: password in a URL (hidden, 11 characters) (secret: change it, it's been exposed)
  row 9 (line 12): notes: password or key (hidden, 11 characters) (secret: change it, it's been exposed)
  row 10 (line 13): notes: Social Security number ***-**-6789 (PII)

Flagged, kept: a person should look at these (3)
  row 3 (line 5): the same title as row 0, with different content: VPN Connection Timeout
  row 11 (line 14): priority is "Urgent", not one of Low, Medium, High, Critical
  row 12 (line 15): 1 invisible character removed from title
```

A skipped row is shown with its fields (`\n` where it ran onto the next line), so you can see what wasn't read;
row 13 shows the two articles a missing quote swallowed. A redacted value is replaced in the Document's text:

```text
resolution: 1. Check the pool settings in postgres://kb_app:[REDACTED:PASSWORD]@db01:5432/kb. 2. Restart the service.
notes: Temporary admin password: [REDACTED:SECRET] (set by the on-call engineer)
```

The log gives the totals in one line: `WARNING Data checks on sample_it_kb_messy.csv: 4 skipped, 2 duplicates
removed, 6 sensitive values redacted, 3 flagged (the report lists each one)`.

---

## 🎓 Key Concepts Demonstrated

### 1. A Document: Text + Metadata

```python
Document(page_content="title: VPN Connection Timeout\nproblem: ...", metadata={"source": "sample_it_kb.csv", "row": 0})
```

`page_content` is the article's text; `metadata` travels with it and says where that text came from: the file, and
the row.

### 2. Configure First, Load Later

```python
loader = KBLoader(KB_FILE)   # says what to do: which file. Nothing is read yet.
docs = loader.load()         # does it: this is the line that reads the file.
```

The settings go in first, and the work happens only when it's asked for: a loader made for a file that doesn't exist
is no error until `load()`.

### 3. `lazy_load()` and `load()`

`lazy_load()` hands out one Document at a time, so even a very large file never has to be in memory all at once.
`load()`, from LangChain's `BaseLoader`, just collects them into a list.

### 4. Logging for What Happened, `print()` for the Output

```python
logger = logging.getLogger(__name__)                       # one logger per module
logger.info("Read %d documents from %s", count, name)      # the values as arguments, not an f-string
```

Each log line has a level, so you choose how much to see without changing the code: `DEBUG` (every row and every
issue), `INFO` (the default: start and total), `WARNING` (the checks found something, a header with no rows),
`ERROR` (the file can't be read). Logging is set up once, in `main()`: a module that's only imported, as the tests
import this one, leaves that to whoever imports it.

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

### 7. Check the Data: Stop on a Bad File or Header, Skip a Bad Row, Flag a Doubtful One

| Problem | What happens | Why |
|---|---|---|
| A field too big, or other broken CSV | stop | the reader's place in the file can't be trusted after it |
| A required column is missing | stop | without `title`, `problem` and `resolution` a row isn't an article |
| A column has no name, or is named twice | stop | its values can't be put under the right name |
| A BOM or spaces in the column names | cleaned | Excel's "CSV UTF-8" adds an invisible BOM; `title, problem` has spaces |
| A row has more or fewer fields than the header | skip | the values may be under the wrong columns: a comma not in quotes, or a quote never closed |
| A required value is blank | skip | an article with no fix can't help anyone |
| An invisible character in a value | removed, flagged | it can't be seen, but a title with a zero-width space in it doesn't match the same title without one |
| Spaces around a value | trimmed | `" VPN "` and `"VPN"` are the same value |
| A value outside the allowed ones | flagged, kept | `Urgent` may be a new priority or a mistake: a person decides |

A bad file or header stops the run, because no row could be read right. A bad row is skipped, because it affects
only itself. A doubtful row is kept and flagged, because skipping it would lose a good article over a small question.

### 8. Duplicates: Remove the Copy, Show What It Copied

Two rows whose text is the same, ignoring upper and lower case and spacing, are the same article: the first is kept,
and each copy is removed and listed with the row it copies. Two rows with the same title but different content are
both kept and flagged: they may be two versions of one article, and only a person can say which is right. Skipped
and removed rows don't renumber the others: each Document's `row` is still its place in the file.

### 9. Sensitive Data: Find It Where It Comes In, and Never Pass It On

A knowledge base is written from support tickets, so personal data, card numbers and passwords get pasted into it.
Once a value is read, everything after this point could print it, log it or keep it. So it's handled here, at the
point the data comes in:

| Kind | Examples | What's done | How it's shown in the report |
|---|---|---|---|
| **PII**: personal data | email addresses, phone numbers, Social Security numbers | replaced in the text | partly masked: `j***@example.com`, `***-***-0142` |
| **PCI**: payment card data | card numbers, confirmed with the Luhn check | replaced in the text | the last 4 digits only, as card rules allow: `**** 1111` |
| **Secrets** | `password: ...`, a password in a URL, AWS and Google keys, GitHub tokens, JSON web tokens, private keys | replaced in the text | never shown, not even in part: `(hidden, 11 characters)`, and "change it" |

The rules behind it:

- **Find it at the start.** The earlier it's found, the fewer places it can leak to.
- **Keep only what the text needs.** An article's fix doesn't need a user's phone number, so it's removed, not kept
  "just in case".
- **Never log or print a raw value.** The report says where (row, line, column), what kind, and a masked form.
- **A secret that's been written down is exposed.** Removing it from the text doesn't make it safe again: the report
  says to change it.
- **Fix it at the source.** The report tells whoever owns the file which rows to clean, so the next export is clean.

Pattern matching can miss a value written in an unusual way, and can catch a number that only looks like one: a
finding is a strong hint, and the file's owner has the last word.

### 10. Never Drop or Change Anything Silently

Every row read ends up in exactly one place: kept, skipped or removed, and the totals add up. Every change to a kept
row (a redaction, a removed invisible character) and every doubt about one (a reused title, an unexpected value) is
in the report, with its row and line. Blank lines are counted too.

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
**Fix**: The file was saved in another encoding, often UTF-16 by Windows PowerShell 5's `>`. Save it again as UTF-8,
or read it with `KBLoader(path, encoding="utf-16")`.

**Issue**: `ERROR Knowledge base file can't be read as CSV at line 3 (field larger than field limit (131072)): ...`
**Fix**: One value at that line is over 131,072 characters, usually a log or a file pasted into a cell. Shorten it.

**Issue**: `ERROR Knowledge base file is missing required columns (resolution): ...`
**Fix**: Add the column to the first line of the file. For a CSV that isn't made of articles, give `KBLoader` its own
`required_columns`.

**Issue**: `ERROR Knowledge base file has a column more than once (title): ...` or `... has a column with no name (column 9): ...`
**Fix**: Rename or remove the column in the first line. A name that's missing is often a comma at the end of it.

**Issue**: `WARNING Data checks on ...: 4 skipped, 2 duplicates removed, 6 sensitive values redacted, 3 flagged (the report lists each one)`
**Fix**: The report at the end of the output lists each one, with its row, line and why. Fix the rows in the file;
the meaning of each message is under Understanding the Output.

**Issue**: A row in the report says `a quote that's never closed made lines 16-18 into one row`
**Fix**: Add the missing `"` on the row's first line. The rows after it, shown in the report, are read again once
it's fixed.

**Issue**: `WARNING ... has a header row but no articles`, then `0 documents`
**Fix**: The file has the column names but no rows under them. Add the articles, one per line.

**Issue**: `knowledge_base_loader.py: error: argument --log-level: invalid choice: 'LOUD' (choose from DEBUG, INFO, WARNING, ERROR)`
**Fix**: Use one of the four levels it lists. Run `python knowledge_base_loader.py --help` to see every option.

---

## 📚 Next Steps

**[02 · Documents and Metadata](../02-documents-and-metadata/README.md)**: this project put every column into a
Document's text. 02 splits each article into its text (title, problem, resolution, notes) and the labels kept next
to it (system, category, priority, tags).

### Ideas to Try

- Run the messy file and match each line of the report to its row in `data/sample_it_kb_messy.csv`.
- In a copy of the messy file, put the missing `"` after `Users cannot reset their password` on line 16, then read
  it again: 3 more articles are kept (row 13 and the 2 it swallowed), and the last is flagged, because row 11 has
  its title.
- Add a row with your own made-up email address and phone number, and see them redacted in the Document.
- Run `python knowledge_base_loader.py --log-level DEBUG` and find the log line for each row and each issue.
