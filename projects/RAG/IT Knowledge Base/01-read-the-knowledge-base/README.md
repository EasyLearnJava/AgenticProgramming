# 01 · Read the knowledge base

## What it does

The knowledge base is a CSV file, `data/sample_it_kb.csv`: 10 IT support articles, one per row, each with 8 columns
(title, problem, resolution, system, category, notes, priority, tags).

`read_kb.py` reads that file into LangChain `Document`s, one per article, and prints what it read. A `Document` is
how LangChain holds a piece of text, and every later step starts from these 10. Each one has two parts:

- `page_content`: the article's text, one `column: value` line per column.
- `metadata`: where the text came from, for example `{'source': 'sample_it_kb.csv', 'row': 0}`.

```text
data/sample_it_kb.csv  ->  KBLoader  ->  10 Documents
```

No model and no API key: it only reads a file.

## How to run it

You need Python 3.11 or newer.

```bash
cd "projects/RAG/IT Knowledge Base/01-read-the-knowledge-base"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: langchain-core and pytest, into .venv/
python read_kb.py
```

Creating the venv and installing are once only; activate it again in every new terminal.

`python read_kb.py` prints how many documents it read, each article's row number and title, then the first document
in full: its text, then its metadata.

```text
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

title: VPN Connection Timeout
problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations
resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.
system: VPN
category: Remote Access
notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.
priority: High
tags: vpn;timeout;remote;connection

{'source': 'sample_it_kb.csv', 'row': 0}
```

To run the tests:

```bash
python -m pytest                     # 9 passed
```
