# 03 · Chunking

## What it does

This step cuts each article into smaller pieces, called chunks. Later steps search chunks instead of whole articles,
so a search can find the part of an article that matches a question.

`chunking.py` uses LangChain's `RecursiveCharacterTextSplitter`:

- Each chunk is at most 512 characters long. The articles are 569 to 716 characters long, so each one becomes 2 or 3
  chunks: 28 in all.
- It cuts at the biggest break it can find: first the blank lines between Title, Problem, Resolution and Notes, then
  line breaks, then spaces.
- When it has to cut inside a section, up to 50 characters from the end of one chunk are repeated at the start of the
  next (the overlap), so a sentence cut at the edge can still be whole in one of them. With 512, every cut falls
  between sections, so nothing is repeated; with 200 (below), you can see it happen.
- Each chunk is a Document of its own, with its article's labels plus `start_index`: where in the article's text the
  chunk starts.

```text
10 Documents  ->  RecursiveCharacterTextSplitter  ->  28 chunks of at most 512 characters
```

No model and no API key.

## How to run it

You need Python 3.11 or newer.

```bash
cd "projects/RAG/IT Knowledge Base/03-chunking"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: LangChain's core and text splitters, and pytest, into .venv/
python chunking.py
```

Creating the venv and installing are once only; activate it again in every new terminal.

`python chunking.py` prints how many chunks each article made. Then it prints every article's chunks: a heading for
each article, then each chunk with a note saying where in the article it starts and how long it is. The start of what
it prints:

```text
10 articles -> 28 chunks of at most 512 characters
  2 from VPN Connection Timeout (569 characters)
  2 from MFA Setup Failure (653 characters)
  3 from Laptop Performance Degradation (668 characters)
  3 from SaaS Access Permission Denied (672 characters)
  3 from WiFi Connectivity Issues Office (668 characters)
  3 from Password Reset Failed (716 characters)
  3 from Printer Not Found (627 characters)
  3 from Email Attachment Size Limit (660 characters)
  3 from Database Connection Timeout (689 characters)
  3 from Microsoft Teams Audio Issues (699 characters)

Article 1 of 10: VPN Connection Timeout, cut into 2 chunks

Chunk 1 of 2, from character 0 (457 characters):
Title: VPN Connection Timeout

Problem: Users experience timeout errors when attempting to connect to the corporate VPN from remote locations

Resolution: 1. Verify internet connection stability. 2. Check firewall settings and ensure VPN ports (UDP 500 and 4500) are open. 3. Restart VPN client application. 4. Clear VPN cache in application settings. 5. If issue persists restart the VPN service on the server. 6. Contact network team if problem continues.

Chunk 2 of 2, from character 459 (110 characters):
Notes: Common issue during peak hours especially for users on home networks. May be related to ISP throttling.

Article 2 of 10: MFA Setup Failure, cut into 2 chunks
...
```

The `...` stands for the rest: your terminal shows all 10 articles and their 28 chunks.

Try other chunk sizes by giving one after the script's name:

```bash
python chunking.py 200               # 49 chunks
python chunking.py 1000              # 10 chunks: every article whole
```

To run the tests:

```bash
python -m pytest                     # 13 passed
```
