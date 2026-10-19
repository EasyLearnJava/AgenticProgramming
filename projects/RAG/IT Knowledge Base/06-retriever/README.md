# 06 · Retriever

## What it does

A retriever is LangChain's standard way to say "give me the chunks for this question". `retriever.py` turns step 05's
vector store into one:

- `invoke(question)` gives back the 5 chunks closest to the question, closest first.
- `batch(questions)` does the same for several questions at once.
- It's a Runnable, like the prompts and models in the tutorials, so in step 07 it joins a chain with `|`.

`format_docs()` joins chunks into one text, each with a number and its article's title, ready to go into a prompt.

```text
a question  ->  retriever  ->  the 5 closest chunks  ->  format_docs  ->  one text for a prompt
```

The script asks the course app's three sample questions. Each run makes 4 calls to Gemini: one for the 28 chunks,
then one for each question.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/06-retriever"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python retriever.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`python retriever.py` prints each question with the 5 chunks found for it. Then it prints what a prompt would get for
the first question: its 2 closest chunks, as one text. The parts in `< >` come from Gemini's search:

```text
Question: How do I fix VPN connection timeouts?
The 5 chunks found, closest first:
  <article title>, from character <start_index>
  ...

Question: I can't set up MFA on my mobile device
The 5 chunks found, closest first:
  ...

Question: My laptop is running very slow
The 5 chunks found, closest first:
  ...

What a prompt gets for the first question, its 2 closest chunks as one text (format_docs):
[1] <article title>
<the chunk's text>

[2] <article title>
<the chunk's text>
```

To ask your own question, put it after the script's name:

```bash
python retriever.py "my email bounced"
```

To run the tests:

```bash
python -m pytest                     # 24 passed, 3 skipped
```

The 3 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
