# 07 · Grounded answer

## What it does

This step answers questions. It's RAG: retrieval first, then generation.

1. The retriever (step 06) finds the 5 chunks closest to the question.
2. The chunks and the question go into one prompt. Its rules tell Gemini to answer using only these articles, and to
   say so when they don't cover the question.
3. Gemini's chat model, `gemini-3.5-flash-lite`, writes the answer.

"Grounded" means the answer comes from the knowledge base, not from what the model learned in training. The chain
also keeps the chunks it found, so the script can show the answer's sources.

- `models.py` now makes the chat model too.
- `rag_chain.py` builds the chain and runs it.

```text
question ──┬──> retriever ───> 5 chunks ──┐
           └──> passed through ───────────┴──> prompt  ->  Gemini  ->  answer + sources
```

Each run makes 3 calls to Gemini: the chunks' embeddings, the question's embedding, and the answer.

## How to run it

You need Python 3.11 or newer, and a Gemini API key.

```bash
cd "projects/RAG/IT Knowledge Base/Basic/07-grounded-answer"   # from the repo root; the quotes are for the spaces
python -m venv .venv                 # once: a private folder for this project's packages
source .venv/bin/activate            # macOS, Linux and Codespaces
#   Windows PowerShell:      .venv\Scripts\Activate.ps1
#   Windows Command Prompt:  .venv\Scripts\activate
#   Windows Git Bash:        source .venv/Scripts/activate
pip install -r requirements-dev.txt  # once: the packages and pytest, into .venv/
cp .env.example .env                 # once (Windows PowerShell or Command Prompt: copy .env.example .env)
python rag_chain.py
```

Creating the venv, installing and making `.env` are once only; activate the venv again in every new terminal.

**Your key:** open `.env` in an editor and put your key after `GOOGLE_API_KEY=` (`tutorials/09-gemini-key` shows how
to make one). `.env` is in `.gitignore`, so your key never goes into git. Without a key, the script stops with:

```text
Can't build the models: GOOGLE_API_KEY is not set. Copy .env.example to .env and put your key after the =, or set GOOGLE_API_KEY as an environment variable (in Codespaces: a Codespaces secret).
```

`python rag_chain.py` prints the question, Gemini's answer, then the articles the chunks came from, each once. The
parts in `< >` come from Gemini:

```text
Question: How do I fix VPN connection timeouts?

Answer (Gemini's, from the chunks found):
<Gemini's answer>

Sources (the articles of the chunks found, closest first):
  <article title>
  ...
```

To ask your own question, put it after the script's name:

```bash
python rag_chain.py "my printer is missing"
```

To run the tests:

```bash
python -m pytest                     # 33 passed, 5 skipped
```

The 5 skipped tests are live tests: they call the real Gemini, so they run only when your key is set.
