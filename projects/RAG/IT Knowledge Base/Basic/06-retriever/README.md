# 06 · Retriever

## What it does

This is where the user's question comes in: the query side of RAG. Steps 04 and 05 got the knowledge base ready;
now a question finds the chunks that answer it, in two steps:

1. **Embed the question.** `embed_query()` turns it into 768 numbers, with the same model as the chunks, so the two
   can be compared. It tells Gemini this text is a question looking for documents (`RETRIEVAL_QUERY`).
2. **Search.** Qdrant compares the question's vector with the 28 stored vectors and gives back the 5 closest chunks,
   each with a score: the cosine similarity, how closely the two vectors point the same way, from -1 to 1. The closer
   to 1, the closer the meaning.

Then comes the retriever, LangChain's standard way to say "give me the chunks for this question":
`make_retriever(store).invoke(question)` does both steps in one call. It's a Runnable, like the prompts and models in
the tutorials, so in step 07 it joins a chain with `|`. `format_docs()` joins chunks into one text, each with a number
and its article's title, ready to go into a prompt.

```text
a question  ->  Gemini: 768 numbers  ->  Qdrant: the 5 closest chunks, with scores  ->  format_docs  ->  text for a prompt
```

The script shows each step for one question, `How do I fix VPN connection timeouts?`, or for yours. Each run makes 3
calls to Gemini: one for the 28 chunks, then the question twice, once by hand and once through the retriever.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/Basic/06-retriever"   # from the repo root; the quotes are for the spaces
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

`python retriever.py` prints each step: the question's vector, the 5 closest chunks with their scores, the same 5
found by the retriever in one call, and the text a prompt would get. The parts in `< >` come from Gemini:

```text
Question: How do I fix VPN connection timeouts?
The question became 768 numbers: [<the first 5 numbers>, ...]

The 5 closest chunks, with their scores, closest first:
  <score>  <article title>, from character <start_index>
  ...

The retriever, embedding and searching in one call, found:
  <article title>, from character <start_index>
  ...

What a prompt gets, the 2 closest chunks as one text (format_docs):
[1] <article title>
<the chunk's text>

[2] <article title>
<the chunk's text>
```

The retriever finds the same 5 chunks as the search by hand: it does the same two steps.

To ask your own question, put it after the script's name:

```bash
python retriever.py "my email bounced"
```

To run the tests:

```bash
python -m pytest                     # 28 passed, 3 skipped
```

The 3 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
