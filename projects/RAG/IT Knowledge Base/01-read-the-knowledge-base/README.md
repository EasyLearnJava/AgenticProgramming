# 01 · Read the knowledge base

A RAG app (retrieval-augmented generation) answers questions from a knowledge base: it finds the parts that match a
question and gives them to a language model, which writes the answer from them. Before any of that, the app has to
read its knowledge base. This step reads one, a CSV file of 10 IT support articles, into a pandas table, and prints
what's in it. No AI and no API key yet. It's the first step of the [IT Knowledge Base](../README.md) app.

```text
data/sample_it_kb.csv  ->  pd.read_csv()  ->  kb, a table of 10 rows and 8 columns  ->  printed: its size and columns, its titles, one article
```

## What you'll build

- `read_kb.py`: reads `data/sample_it_kb.csv` into a pandas DataFrame, `kb`, and prints what's in it.
- `data/sample_it_kb.csv`: the knowledge base, 10 IT support articles such as "VPN Connection Timeout" and "Printer
  Not Found", one per line.
- `tests/test_read_kb.py`: 7 tests of the table and of what the script prints.
- `requirements.txt` and `requirements-dev.txt`: the packages, each pinned with `==`. `pytest.ini`: where pytest
  finds the code and the tests.
- What you see: `python read_kb.py` prints `10 articles`, the 8 column names, every article's title, system and
  category, then the first article, one column per line. No server, no page, no model, no API key.

## What you'll learn

- **What's in this knowledge base**: one article per row, and 8 columns: the problem, how to fix it, notes, and
  labels such as the system and the category.
- **`pd.read_csv()`**: reads a CSV file into a DataFrame, pandas' table: the file's first line gives the column names,
  and each line after it becomes a row.
- **Looking inside a DataFrame**: `len(kb)`, `kb.columns`, `kb[[...]]` to pick columns, `kb.iloc[0]` to pick a row,
  and `.items()` to go through a row column by column.
- **`Path(__file__).resolve().parent`**: finding a file next to the script, whichever folder you start it from.
- **`if __name__ == "__main__":`**: code that runs when you run the file, but not when the tests import it.
- **A virtual environment, pip and pytest**: `python -m venv .venv`, `pip install -r requirements-dev.txt` and
  `python -m pytest`.

## Before you start

- **Python 3.11 or newer** (3.13 is used here, and 3.11 was checked too): pandas 3.0.6 needs 3.11 or newer. Check with
  `python --version`; if that fails, install Python from python.org. If `python` isn't found on macOS or Linux, use
  `python3` for the `python -m venv .venv` step; inside the active venv, `python` works on every system.
- Nothing else: no API key, and nothing from another folder. [Run it](#run-it) installs what this step needs.

## Files

| File | What it is |
|---|---|
| `read_kb.py` | Steps ① to ⑤: the file's path, reading the file into `kb`, then three prints. Runs with `python read_kb.py`; the tests import `KB_FILE` and `kb` from it |
| `data/sample_it_kb.csv` | The knowledge base: a first line with the 8 column names, then 10 articles, one per line, then 4 empty lines. Made-up IT support articles (no real people's details), copied unchanged from the course repo [Brianletort/KBs-For-RAGs](https://github.com/Brianletort/KBs-For-RAGs/tree/main/Clip1-v2/data) |
| `tests/test_read_kb.py` | The 7 tests: the path, the table's size and columns, empty cells, the titles, the first article, and what the script prints |
| `pytest.ini` | pytest's settings: `pythonpath = .` lets the tests `import read_kb` wherever pytest is started from; `testpaths = tests` makes it look for tests only in `tests/` |
| `requirements.txt` | The one package `read_kb.py` uses, pinned to one exact version with `==`: `pandas` |
| `requirements-dev.txt` | Everything in `requirements.txt` (its `-r` line) plus the test tool, `pytest` |
| `images/` | The two pictures on this page: `read_kb.py` running from top to bottom, and the commands that run it. They're SVG files: pictures written as text, which GitHub shows as images |
| `README.md` | This page |

`.venv/` appears when you set up, and `__pycache__/` and `.pytest_cache/` when you run the tests. The repo's
`.gitignore` keeps all three out of git.

## How it works

### `pip install -r requirements-dev.txt`, then `python read_kb.py`

`requirements.txt` lists the one package the script needs:

```text
pandas==3.0.6
```

and `requirements-dev.txt` adds the one the tests need:

```text
# Extra packages for running the tests. `pip install -r requirements-dev.txt` installs these and requirements.txt.
-r requirements.txt
pytest==9.1.1          # runs the tests in tests/
```

- **`pandas`**: Python's best-known library for tables. `read_kb.py` uses it to read the CSV file and to pick rows and
  columns. pip also installs the packages pandas needs, such as `numpy`.
- **`pytest`**: runs the tests in `tests/`.
- **`==`** pins each package to one version. Only these two are pinned: pip installs the packages they need at their
  newest allowed versions, which can be newer than the ones used here (`numpy` 2.5.4, on Python 3.13).
- **`-r requirements.txt`**, in `requirements-dev.txt`, installs everything in `requirements.txt`; the line after it
  adds `pytest`.
- **`.venv/`**: `python -m venv .venv` makes it, a folder for this step's packages. Activating it makes `python` and
  `pip` use that folder, and `pip install -r requirements-dev.txt` fills it.

### `read_kb.py`, from top to bottom

`python read_kb.py` runs the file's statements one after the other, from the top:

![read_kb.py from top to bottom. The imports take Path from Python's pathlib, and the package pandas, named pd. ① makes KB_FILE, the full path of data/sample_it_kb.csv in the script's folder: nothing is read yet. ② kb = pd.read_csv(KB_FILE) reads the file: its first line gives the 8 column names, title, problem, resolution, system, category, notes, priority and tags, and each article's line becomes a row, numbered from 0, so kb is a DataFrame of 10 rows and 8 columns. if __name__ == "__main__": checks how the file was started: run directly with python read_kb.py, the lines below it run; imported by the tests, they're skipped. ③ prints 10 articles and the column names. ④ prints the title, system and category of rows 0 to 9. ⑤ picks the first row and prints it one column per line, from title: VPN Connection Timeout to tags: vpn;timeout;remote;connection.](images/read-kb-py.svg)

① only makes a path. ② is where the work happens: `pd.read_csv()` opens the file and reads all of it into `kb`.
③ to ⑤ only print parts of `kb`, and only when the file is run directly. The sections below go through the code in
order, with its comments left out.

### The imports

```python
from pathlib import Path

import pandas as pd
```

- `Path` comes with Python, in its `pathlib` module: it holds a file's or a folder's path, and builds one piece by
  piece.
- `pandas` is the package from `requirements.txt`. `as pd` gives it the short name that pandas code usually uses.

### ① The file's path

```python
KB_FILE = Path(__file__).resolve().parent / "data" / "sample_it_kb.csv"
```

- `__file__` is the path of this script's own file. `.resolve()` makes sure it's a full path, with any `..` worked
  out, and `.parent` is the folder the script is in.
- `/` on a `Path` adds a name to it, so `KB_FILE` is the full path of `data/sample_it_kb.csv` in this folder, ending in
  `...\01-read-the-knowledge-base\data\sample_it_kb.csv` (with `/` on macOS and Linux).
- Nothing is read yet: `KB_FILE` only says where the file is. A bare `"data/sample_it_kb.csv"` would be looked for in
  the folder you started the script from, so the script would work only from this folder. One of the tests in
  [Test it](#test-it) starts it from another folder.

### ② Reading the file

```python
kb = pd.read_csv(KB_FILE)
```

This is the line that does the work. The file is plain text, and it starts like this (the second line is cut short
here):

```text
title,problem,resolution,system,category,notes,priority,tags
VPN Connection Timeout,Users experience timeout errors when attempting to connect to the corporate VPN from remote locations,"1. Verify ...
```

- The first line holds the 8 column names, separated by commas.
- Each line after it is one article, with its 8 values in the same order. Each resolution is wrapped in double
  quotes: in a CSV file, quotes keep a value that has a comma inside it in one piece. These resolutions have no
  commas, so here the quotes change nothing, and `read_csv()` takes them off.
- The file ends with 4 empty lines, which `read_csv()` skips.
- `read_csv()` reads all of it into `kb`, a **DataFrame**: pandas' table, here 10 rows and 8 columns. Each row gets a
  number, its **index**, from 0 to 9, which you'll see on the left in ④.

### ③ to ⑤: only when the file is run directly

```python
if __name__ == "__main__":
```

- Python sets `__name__` to `"__main__"` in the file you run (`python read_kb.py`), and to the file's module name,
  `"read_kb"`, when another file imports it.
- The tests do `from read_kb import KB_FILE, kb`: that runs ① and ②, so they get the table, and skips the prints.

### ③ How many articles, and the columns

```python
    print(f"{len(kb)} articles")
    print("columns:", kb.columns.tolist())
    print()
```

- `len(kb)` is the number of rows: 10. The `f` before the quotes lets `{len(kb)}` put it into the text.
- `kb.columns` holds the column names, and `.tolist()` turns them into a plain Python list, which prints with brackets
  and quotes.
- `print()` prints an empty line, to keep the parts apart.

```text
10 articles
columns: ['title', 'problem', 'resolution', 'system', 'category', 'notes', 'priority', 'tags']
```

### ④ Every title, system and category

```python
    print(kb[["title", "system", "category"]].to_string())
    print()
```

- `kb[[...]]`, with a list of column names inside the brackets, gives a smaller DataFrame with only those columns, in
  that order. `kb` itself doesn't change.
- `.to_string()` turns the whole table into text, every row and every column, with nothing cut out. For these three
  columns a plain `print()` of the table would show the same; with a fourth, as in [Things to try](#things-to-try) 2,
  the table gets too wide, and `print()` alone would leave the middle columns out and show `...` instead.
- The numbers on the left are the index from ②.

```text
                             title            system             category
0           VPN Connection Timeout               VPN        Remote Access
1                MFA Setup Failure               MFA             Security
2   Laptop Performance Degradation            Laptop             Hardware
3    SaaS Access Permission Denied        Salesforce          SaaS Access
4  WiFi Connectivity Issues Office              WiFi              Network
5            Password Reset Failed  Active Directory  Identity Management
6                Printer Not Found           Printer             Hardware
7      Email Attachment Size Limit             Email        Communication
8      Database Connection Timeout          Database       Infrastructure
9     Microsoft Teams Audio Issues   Microsoft Teams        Collaboration
```

### ⑤ The first article, column by column

```python
    first = kb.iloc[0]
    for column, value in first.items():
        print(f"{column:>10}: {value}")
```

- `kb.iloc[0]` picks a row by its position: 0 is the first. It gives back one row, its values labelled with the column
  names (pandas calls that a Series).
- `first.items()` gives each column's name and value in turn, and the loop prints one pair per line.
- `:>10` pads the name on the left to 10 characters, the length of the longest name, `resolution`, so the colons line
  up.

```text
     title: VPN Connection Timeout
   problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations
resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.
    system: VPN
  category: Remote Access
     notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.
  priority: High
      tags: vpn;timeout;remote;connection
```

## Run it

```bash
cd "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base"   # from the repo root; keep the quotes
python -m venv .venv                 # once: a private folder for this step's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages, into .venv/
```

The folder name `IT Knowledge Base` has spaces in it, so the quotes around the path are needed: they keep it in one
piece in bash, PowerShell and Command Prompt alike. Creating the venv and installing are once only; activate it again
in every new terminal. Then:

```bash
python read_kb.py
```

![A terminal, in Git Bash. cd "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base" goes into the step's folder. python -m venv .venv, once, makes .venv/. source .venv/Scripts/activate, in each new terminal, makes the prompt start with (.venv). pip install -r requirements-dev.txt, once, prints a few lines per package, then Successfully installed and the packages, then a notice that a new pip is available, information only. python read_kb.py, each time, prints 10 articles and the 8 column names, then every row's title, system and category with its number, then the first article, one column per line. Then the prompt comes back: the script has ended. Long lines are cut in the picture.](images/run-it.svg)

`pip install` prints a few lines for each package it gets, then a `Successfully installed ...` line that lists every
package it put in `.venv/`: `pandas` and `pytest`, and the packages they need, such as `numpy`. A `[notice]` after it,
saying a new pip is available, is information only.

`python read_kb.py` prints:

```text
10 articles
columns: ['title', 'problem', 'resolution', 'system', 'category', 'notes', 'priority', 'tags']

                             title            system             category
0           VPN Connection Timeout               VPN        Remote Access
1                MFA Setup Failure               MFA             Security
2   Laptop Performance Degradation            Laptop             Hardware
3    SaaS Access Permission Denied        Salesforce          SaaS Access
4  WiFi Connectivity Issues Office              WiFi              Network
5            Password Reset Failed  Active Directory  Identity Management
6                Printer Not Found           Printer             Hardware
7      Email Attachment Size Limit             Email        Communication
8      Database Connection Timeout          Database       Infrastructure
9     Microsoft Teams Audio Issues   Microsoft Teams        Collaboration

     title: VPN Connection Timeout
   problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations
resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.
    system: VPN
  category: Remote Access
     notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.
  priority: High
      tags: vpn;timeout;remote;connection
```

- The first two lines are ③: how many articles, and the column names.
- The table is ④: three columns of every row, with its row number on the left.
- The last 8 lines are ⑤: the first article, one column per line. A long value stays on one line, so your terminal
  wraps it to fit its width.

There's no server, page or port in this step: everything appears in the same terminal, and the script ends.

## Test it

There are 7 tests, all plain: no key, no network and no server. They only read the CSV file and run the script.

| Test | What it checks |
|---|---|
| `test_the_path_points_at_the_csv_next_to_the_script` | `KB_FILE` is `data/sample_it_kb.csv` in this folder, and the file is there |
| `test_there_are_10_articles_with_the_8_columns_in_order` | `kb` has 10 rows, and the 8 columns in the file's order |
| `test_no_article_has_an_empty_cell` | Every article has a value in every column |
| `test_every_title_is_different` | No two articles have the same title |
| `test_the_first_article_is_the_vpn_timeout` | Row 0 is "VPN Connection Timeout", system "VPN", category "Remote Access" |
| `test_running_the_script_prints_the_summary_then_the_first_article` | `python read_kb.py`, run as a separate process, starts with the count and the columns, prints row 9 of the table, and ends with the first article's last two lines |
| `test_the_script_finds_the_csv_from_any_folder` | Started from an empty folder, the script prints exactly what it prints from this one: ①'s full path at work |

The two script tests run `read_kb.py` with `sys.executable`, the Python that is running the tests (your venv's), and
read what it prints. The last one starts it in `tmp_path`, an empty folder pytest makes for that test. pytest can
`import read_kb` because of `pytest.ini` (see [Files](#files)).

```bash
python -m pytest          # all the tests; the last line says "7 passed"
python -m pytest -v       # the same tests, one line each, with its name
```

## When things go wrong

An error can print many lines. The "What you see" column quotes the part that says what went wrong.

| What happens | What you see | What to do |
|---|---|---|
| The path typed without quotes | bash: `cd: too many arguments`; PowerShell: `A positional parameter cannot be found that accepts argument 'Knowledge'.` | Put the path in double quotes: `cd "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base"` |
| PowerShell won't run the activate script | `...Activate.ps1 cannot be loaded because running scripts is disabled on this system` | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, then activate again (or use Git Bash or Command Prompt) |
| The venv isn't active, or the packages aren't installed | `ModuleNotFoundError: No module named 'pandas'` (from `python read_kb.py`), or `No module named pytest` (from `python -m pytest`) | Activate the venv; if that isn't enough, run `pip install -r requirements-dev.txt` |
| A command run outside the step's folder, such as the repo root | python: `can't open file '...read_kb.py': [Errno 2] No such file or directory`; pip: `ERROR: Could not open requirements file: [Errno 2] No such file or directory: 'requirements-dev.txt'` | `cd` into the step's folder (with the quotes), then run the command again |
| The CSV file is missing, renamed or moved | `FileNotFoundError: [Errno 2] No such file or directory: '...sample_it_kb.csv'` | Put the file back in `data/`, named `sample_it_kb.csv`. In a git clone, `git restore data/sample_it_kb.csv` brings back the original |
| A column name spelled differently in ④, such as `"Title"` | `KeyError: "['Title'] not in index"` | Column names must match exactly, capitals included: use the names ③ prints |

## Things to try

1. **Print the last article.** In ⑤, change `kb.iloc[0]` to `kb.iloc[-1]`: `-1` counts from the end. The last part of
   the output is now the tenth article, from `     title: Microsoft Teams Audio Issues` to
   `      tags: teams;audio;collaboration;windows`.
2. **Pick another column.** In ④, add `"priority"` to the list: `kb[["title", "system", "category", "priority"]]`. The
   table gets a fourth column, starting `High`, `High`, `Medium`.
3. **Count the articles per category.** Replace ④'s first line with `print(kb["category"].value_counts())`. With one
   name in single brackets, `kb["category"]` is one column, and `value_counts()` counts each of its values:

   ```text
   category
   Hardware               2
   Remote Access          1
   Security               1
   SaaS Access            1
   Network                1
   Identity Management    1
   Communication          1
   Infrastructure         1
   Collaboration          1
   Name: count, dtype: int64
   ```

   Two articles, the laptop and the printer, are about hardware; every other category has one.
4. **Add an article.** Add a line at the end of `data/sample_it_kb.csv` (after the empty lines is fine: they're
   skipped), with 8 values in the column order, for example:

   ```text
   Monitor Flickering,External monitor flickers when connected through a USB-C dock,1. Reseat the cable. 2. Update the dock firmware.,Monitor,Hardware,Common after driver updates.,Low,monitor;dock;display
   ```

   `python read_kb.py` now starts with `11 articles`, and the table ends with row `10`, `Monitor Flickering`.
   `python -m pytest` says `2 failed, 5 passed`: two tests expect the 10 articles that come with this step. Take the
   line out again (or `git restore data/sample_it_kb.csv`).

## Next

**Step 02 · Turn rows into Documents** (coming next): each row of `kb` becomes a LlamaIndex `Document`, the text to
search plus labels that say which article it came from. See [the steps](../README.md#the-steps).
