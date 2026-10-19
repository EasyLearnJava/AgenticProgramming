# 02 · Documents and metadata

## What it does

Step 01 put every column of an article into its Document's text. This step splits each article into two parts,
because they're used in different ways:

- **Text (`page_content`)**: the title, problem, resolution and notes, each with its label, and a blank line between
  them. This is what will be searched, and what Gemini will read to write an answer.
- **Labels (`metadata`)**: `doc_id` (the article's number), title, system, category, priority and tags. They're kept
  next to the text and shown with an answer as its source.

The title is in both: it helps the search find the article, and it names the source.

`knowledge_base.py` does this with a LangChain document loader, then prints which columns went where and every
Document. All the later steps get their Documents from this file.

```text
data/sample_it_kb.csv  ->  KBLoader  ->  10 Documents: text to search + labels
```

No model and no API key: it only reads a file.

## How to run it

You need Python 3.11 or newer.

```bash
cd "projects/RAG/IT Knowledge Base/02-documents-and-metadata"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: langchain-core and pytest, into .venv/
python knowledge_base.py
```

Creating the venv and installing are once only; activate it again in every new terminal.

`python knowledge_base.py` prints how many documents it read, and which columns went into the text and which into the
metadata. Then it prints every document in full, with a blank line between them: a heading (`Document 1 of 10`), its
text, then its labels, each with a note saying what it is. The start and the end of what it prints:

```text
10 documents
text:     title, problem, resolution, notes
metadata: doc_id, title, system, category, priority, tags

Document 1 of 10
Text (page_content):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.

Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Labels (metadata):
{'doc_id': '0', 'title': 'VPN Connection Timeout', 'system': 'VPN', 'category': 'Remote Access', 'priority': 'High', 'tags': 'vpn;timeout;remote;connection'}

Document 2 of 10
Text (page_content):
Title: MFA Setup Failure
...

Document 10 of 10
Text (page_content):
Title: Microsoft Teams Audio Issues
...

Labels (metadata):
{'doc_id': '9', 'title': 'Microsoft Teams Audio Issues', 'system': 'Microsoft Teams', 'category': 'Collaboration', 'priority': 'Medium', 'tags': 'teams;audio;collaboration;windows'}
```

The `...` lines stand for the parts left out here: your terminal shows all 10 documents in full.

To run the tests:

```bash
python -m pytest                     # 5 passed
```
