# 12 · Tuning

## What it does

This step measures how well the search finds the right article, to help choose the settings. `tuning.py` has 10 test
questions, each with the article that should answer it. They use other words than the articles do ("sluggish", not
"slow"), so finding the article means the meaning matched, not the words.

- For three chunk sizes, 200, 512 and 1000 characters, it stores the chunks and searches with every question.
- It counts how many questions found their article among the closest 1, 3 and 5 chunks (k).
- With `--answers`, it also answers one question twice, from 1 chunk and from 5, to show what the number of chunks
  does to an answer.

```text
10 questions  x  3 chunk sizes  ->  how many found their article in the top 1, 3 and 5 chunks
```

Everything in `tuning.py` runs in memory: it doesn't need Docker, and it doesn't touch the chunks stored in the Qdrant
server. It makes 13 calls to Gemini: one for each question and one for each chunk size. `--answers` adds 5 more: 3
embeddings and 2 answers.

The rest of the project (the engine, the API and the chat page) is the same as step 11.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/12-tuning"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python tuning.py                     # the table
python tuning.py --answers           # the table, then one question answered from 1 chunk and from 5
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`python tuning.py` prints a table with one line per chunk size: how many chunks it made, and how many of the 10
questions found their article in the top 1, 3 and 5 chunks. Here `n` stands for those counts, which come from Gemini:

```text
10 questions, each with the article that answers it.

chunk size  chunks  found in top 1  found in top 3  found in top 5
       200      49   n of 10       n of 10       n of 10
       512      28   n of 10       n of 10       n of 10
      1000      10   n of 10       n of 10       n of 10
```

With `--answers`, the two answers follow the table. The parts in `< >` come from Gemini:

```text
--- 'My VPN keeps dropping when I work from home', answered from 1 chunk:
<Gemini's answer>

--- 'My VPN keeps dropping when I work from home', answered from 5 chunks:
<Gemini's answer>
```

To run the engine, the server or the chat page in this folder, start Qdrant first, as in step 11:
`docker compose up -d`.

To run the tests (they don't need Docker):

```bash
python -m pytest                     # 61 passed, 8 skipped
```

The 8 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
