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
cd "projects/RAG/IT Knowledge Base/Basic/03-chunking"   # from the repo root; the quotes are for the spaces
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

## Why a chunk can be shorter than 512 characters

512 is a maximum, not a target. The splitter never makes a chunk longer than 512 characters, but it makes a shorter
one rather than cut through the middle of a section. The MFA article shows it:

```text
Article 2 of 10: MFA Setup Failure, cut into 2 chunks

Chunk 1 of 2, from character 0 (144 characters):
Title: MFA Setup Failure

Problem: Employee cannot complete Multi-Factor Authentication setup on mobile device using Microsoft Authenticator app

Chunk 2 of 2, from character 146 (507 characters):
Resolution: 1. Ensure device time is synchronized (Settings > Date & Time > Automatic). 2. Clear cache and data for Microsoft Authenticator app. 3. Uninstall and reinstall the authenticator app. 4. Re-scan the QR code from the MFA setup page. 5. If QR code fails use manual entry method. 6. Verify company app is not blocking authenticator app. 7. Contact security team for account reset if needed.

Notes: Time synchronization is the most common root cause. iOS users should check Screen Time restrictions.
```

First the splitter breaks the article at its blank lines (`\n\n`), into its 4 sections:

| Section | Characters |
|---|---|
| Title | 24 |
| Problem | 118 |
| Resolution | 398 |
| Notes | 107 |

Then it joins them back together in order, adding the next section only while the chunk stays at 512 or under. Each
join puts back the blank line between them, which is 2 characters (`\n\n`):

| Step | Sum | Result |
|---|---|---|
| Title | 24 | fits |
| + Problem | 24 + 2 + 118 = **144** | fits |
| + Resolution | 144 + 2 + 398 = 544 | over 512, so chunk 1 ends at 144 |
| Resolution, starting chunk 2 | 398 | fits |
| + Notes | 398 + 2 + 107 = **507** | fits, so chunk 2 is 507 |

Chunk 2 starts at character 146: characters 144 and 145 are the blank line at the cut, which goes in neither chunk.

**Why it doesn't fill chunk 1 up to 512:** it could cut the Resolution partway, but that would split the fix's steps
across two chunks. The splitter only cuts inside a section (at a line break, then at a space) when the section alone
is over 512, and the Resolution is 398. So the chunks come out uneven, but each one is whole sections: chunk 1 is
what's wrong, and chunk 2 is how to fix it.

**Why nothing is repeated:** the overlap repeats at most 50 characters of whole pieces, and the piece before the cut,
the Problem, is 118 characters. With `python chunking.py 200`, the sections themselves get cut at spaces, and then
the overlap shows.

The VPN article works the same way. Its Title, Problem and Resolution make 29 + 2 + 110 + 2 + 314 = **457**. Adding
the Notes would make 457 + 2 + 110 = 569, over 512, so the Notes (110 characters) become chunk 2, from character 459.
