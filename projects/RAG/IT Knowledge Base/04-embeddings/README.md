# 04 · Embeddings

## What it does

An embedding model turns a text into a vector: a list of numbers. Texts with close meanings get vectors that point in
close directions, so comparing vectors compares meanings.

`similarity.py` sends the 10 articles and a question to Gemini's embedding model, `gemini-embedding-001`, which gives
back 768 numbers for each text. Then it ranks the articles by cosine similarity: how close each article's vector points
to the question's, from -1 to 1, where closer to 1 means closer in meaning. This finds articles by what they mean,
not by the words they share.

- `config.py` checks your Gemini API key first, the same way as in the tutorials.
- `models.py` makes the embedding model.
- `similarity.py` embeds the texts, compares them and prints the ranking.

```text
10 articles + a question  ->  Gemini: 768 numbers each  ->  cosine similarity  ->  the articles, closest first
```

This is the first step that needs a Gemini API key. Each run makes 2 calls to Gemini: one for the 10 articles, one
for the question.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/04-embeddings"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python similarity.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

If `.env` still says `your-key-here`, it stops with `GOOGLE_API_KEY is still the placeholder from .env.example: put
your real key in .env.` instead.

`python similarity.py` prints the size of each vector, then the 10 articles with their scores, closest to the question
first. The parts in `< >` come from Gemini:

```text
Each text became 768 numbers (gemini-embedding-001).
The articles, closest to "My VPN won't connect" first:
  <score>  <the closest article's title>
  <score>  <the next one>
  ...
```

To ask your own question, put it after the script's name:

```bash
python similarity.py "my laptop is so slow"
```

To run the tests:

```bash
python -m pytest                     # 20 passed, 2 skipped
```

The 2 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
